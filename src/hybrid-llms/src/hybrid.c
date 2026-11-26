/* hybrid.c - strategies that combine the local model with a cloud model. */
#define _POSIX_C_SOURCE 200809L
#include "hybrid.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "local.h"

#define MAX_CHUNKS 200

static const char *SYS_CONFIDENCE =
    "Answer the user's request accurately and completely. After the answer, write one final line of exactly the "
    "form `CONFIDENCE: N`, where N is a number from 0 to 100 giving your honest estimate that the answer is correct "
    "and complete. Use a low number when the request needs up-to-date facts, tools, files you have not seen, or "
    "expertise you are unsure about.";

static const char *SYS_DRAFT = "Answer the user's request accurately and completely. Be concise.";

static const char *SYS_CONDENSE =
    "You condense context for another model. Keep everything relevant to the request: code, identifiers, file "
    "paths, numbers, error messages, and quotes stay verbatim. Remove everything irrelevant. Output only the "
    "condensed context, with no commentary.";

static const char *SYS_EXECUTE =
    "Carry out the plan step by step to produce the final answer to the request. Output only the final answer.";

static const char *CLOUD_PREAMBLE =
    "You are being called non-interactively by hybrid-llms as one step of a local+cloud workflow. Reply with the "
    "requested text only. Do not call hybrid-llms tools.\n\n";

int strategy_parse(const char *s, strategy *out)
{
    static const struct {
        const char *n;
        strategy s;
    } t[] = {{"auto", S_AUTO},
             {"local", S_LOCAL},
             {"cloud", S_CLOUD},
             {"cascade", S_CASCADE},
             {"draft-review", S_DRAFT_REVIEW},
             {"draft_review", S_DRAFT_REVIEW},
             {"plan-execute", S_PLAN_EXECUTE},
             {"plan_execute", S_PLAN_EXECUTE},
             {"compress", S_COMPRESS}};
    if (!s) return -1;
    for (size_t i = 0; i < sizeof t / sizeof *t; i++)
        if (str_ieq(s, t[i].n)) {
            *out = t[i].s;
            return 0;
        }
    return -1;
}

const char *strategy_name(strategy s)
{
    switch (s) {
    case S_AUTO: return "auto";
    case S_LOCAL: return "local";
    case S_CLOUD: return "cloud";
    case S_CASCADE: return "cascade";
    case S_DRAFT_REVIEW: return "draft-review";
    case S_PLAN_EXECUTE: return "plan-execute";
    case S_COMPRESS: return "compress";
    }
    return "auto";
}

typedef struct {
    const config *c;
    const hybrid_req *req;
    hybrid_res *res;
    char local_model[512];
} run_ctx;

static int cloud_runnable(cloud_id id)
{
    return id == CLOUD_CLAUDE || id == CLOUD_CODEX || id == CLOUD_GEMINI;
}

static void trace_step(run_ctx *x, const char *step, const char *backend, const char *model, long long ms, size_t in,
                       size_t out, const char *error)
{
    json *s = json_new_obj();
    json_set_str(s, "step", step);
    json_set_str(s, "backend", backend);
    if (model && *model) json_set_str(s, "model", model);
    json_set_num(s, "ms", (double)ms);
    json_set_num(s, "chars_in", (double)in);
    json_set_num(s, "chars_out", (double)out);
    json_set_bool(s, "ok", error == NULL);
    if (error) json_set_str(s, "error", error);
    json_push(x->res->trace, s);
}

static int do_local(run_ctx *x, const char *step, const char *system, const char *prompt, sbuf *out, char *err,
                    size_t errlen)
{
    long long t0 = now_ms();
    sb_reset(out);
    char used[512] = "";
    int rc = local_simple(x->c, system, prompt, x->req->local_model, out, used, sizeof used, err, errlen);
    if (used[0]) snprintf(x->local_model, sizeof x->local_model, "%s", used);
    size_t in = strlen(prompt) + (system ? strlen(system) : 0);
    x->res->local_chars += in + (rc == 0 ? out->len : 0);
    trace_step(x, step, "local", x->local_model, now_ms() - t0, in, rc == 0 ? out->len : 0, rc == 0 ? NULL : err);
    if (rc == 0 && out->len == 0) {
        snprintf(err, errlen, "local model returned an empty answer");
        return -1;
    }
    return rc;
}

/* Replace "@hybrid" so a cloud CLI does not route back into hybrid-llms. */
static char *defuse_mentions(const char *s)
{
    sbuf b;
    sb_init(&b);
    sb_append(&b, "", 0);
    const char *p = s;
    const char *hit;
    while ((hit = strstr(p, "@hybrid"))) {
        sb_append(&b, p, (size_t)(hit - p));
        sb_puts(&b, "hybrid");
        p = hit + 7;
    }
    sb_puts(&b, p);
    return sb_take(&b);
}

static int do_cloud(run_ctx *x, const char *step, const char *prompt, sbuf *out, char *err, size_t errlen)
{
    long long t0 = now_ms();
    sb_reset(out);
    sbuf full;
    sb_init(&full);
    sb_puts(&full, CLOUD_PREAMBLE);
    char *safe = defuse_mentions(prompt);
    sb_puts(&full, safe);
    free(safe);
    int rc = cloud_ask(x->c, x->req->cloud, full.s, out, err, errlen);
    x->res->cloud_chars += full.len + (rc == 0 ? out->len : 0);
    trace_step(x, step, cloud_name(x->req->cloud), NULL, now_ms() - t0, full.len, rc == 0 ? out->len : 0,
               rc == 0 ? NULL : err);
    sb_free(&full);
    return rc;
}

static void add_note(hybrid_res *r, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void add_note(hybrid_res *r, const char *fmt, ...)
{
    sbuf b;
    sb_init(&b);
    if (r->note) {
        sb_puts(&b, r->note);
        sb_puts(&b, " ");
        free(r->note);
    }
    va_list ap;
    va_start(ap, fmt);
    char tmp[1024];
    vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    sb_puts(&b, tmp);
    r->note = sb_take(&b);
}

/* The request as one text block (prompt + optional context). */
static char *user_text(const char *prompt, const char *context)
{
    sbuf b;
    sb_init(&b);
    sb_puts(&b, prompt);
    if (context && *context) {
        sb_puts(&b, "\n\n<context>\n");
        sb_puts(&b, context);
        sb_puts(&b, "\n</context>");
    }
    return sb_take(&b);
}

/* The request for a cloud CLI, with the system text folded in. */
static char *cloud_text(const hybrid_req *r, const char *context)
{
    sbuf b;
    sb_init(&b);
    if (r->system && *r->system) {
        sb_puts(&b, "<instructions>\n");
        sb_puts(&b, r->system);
        sb_puts(&b, "\n</instructions>\n\n");
    }
    sb_puts(&b, "<request>\n");
    sb_puts(&b, r->prompt);
    sb_puts(&b, "\n</request>");
    if (context && *context) {
        sb_puts(&b, "\n\n<context>\n");
        sb_puts(&b, context);
        sb_puts(&b, "\n</context>");
    }
    return sb_take(&b);
}

static char *join_system(const char *base, const char *user_sys)
{
    sbuf b;
    sb_init(&b);
    if (user_sys && *user_sys) {
        sb_puts(&b, user_sys);
        sb_puts(&b, "\n\n");
    }
    sb_puts(&b, base);
    return sb_take(&b);
}

/* Remove a trailing "CONFIDENCE: N" line; return N (0..100) or -1. */
static int split_confidence(char *text)
{
    char *found = NULL;
    for (char *p = text; *p; p++)
        if (strncasecmp(p, "confidence", 10) == 0) found = p;
    if (!found) return -1;
    char *q = found + 10;
    while (*q == '*' || *q == ' ' || *q == '_') q++;
    if (*q != ':') return -1;
    q++;
    while (*q == ' ' || *q == '*' || *q == '_' || *q == '\t') q++;
    if (!isdigit((unsigned char)*q)) return -1;
    long v = strtol(q, &q, 10);
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    /* only accept it when nothing but punctuation follows on that line and after */
    for (char *t = q; *t; t++)
        if (isalnum((unsigned char)*t) && *t != '%') return -1;
    char *line = found;
    while (line > text && line[-1] != '\n') line--;
    *line = '\0';
    str_trim(text);
    return (int)v;
}

/* Split at <= chunk bytes, preferring a newline, never inside a UTF-8 sequence. */
static size_t chunk_len(const char *s, size_t n, size_t chunk)
{
    if (n <= chunk) return n;
    size_t cut = chunk;
    for (size_t i = chunk; i > chunk * 4 / 5; i--)
        if (s[i - 1] == '\n') {
            cut = i;
            break;
        }
    while (cut > 1 && ((unsigned char)s[cut] & 0xC0) == 0x80) cut--;
    return cut;
}

static int condense(run_ctx *x, const char *text, const char *request, sbuf *out, char *err, size_t errlen)
{
    size_t n = strlen(text);
    size_t chunk = x->c->chunk_chars;
    size_t total = (n + chunk - 1) / chunk;
    if (total > MAX_CHUNKS) {
        snprintf(err, errlen, "context too large to condense (%zu chars; limit %zu)", n, chunk * MAX_CHUNKS);
        return -1;
    }
    sb_reset(out);
    size_t off = 0;
    int idx = 0;
    sbuf part;
    sb_init(&part);
    while (off < n) {
        size_t L = chunk_len(text + off, n - off, chunk);
        sbuf p;
        sb_init(&p);
        sb_printf(&p, "Request:\n%s\n\nContext part %d:\n", request, ++idx);
        sb_append(&p, text + off, L);
        char step[48];
        snprintf(step, sizeof step, "condense-%d", idx);
        int rc = do_local(x, step, SYS_CONDENSE, p.s, &part, err, errlen);
        sb_free(&p);
        if (rc != 0) {
            sb_free(&part);
            return -1;
        }
        if (out->len) sb_puts(out, "\n\n");
        sb_append(out, part.s, part.len);
        off += L;
    }
    sb_free(&part);
    return 0;
}

/* ---------- strategies ---------- */

static int run_local(run_ctx *x, char *err, size_t errlen)
{
    sbuf out;
    sb_init(&out);
    char *u = user_text(x->req->prompt, x->req->context);
    int rc = do_local(x, "answer", x->req->system, u, &out, err, errlen);
    free(u);
    if (rc == 0) x->res->answer = sb_take(&out);
    sb_free(&out);
    return rc;
}

static int run_cloud(run_ctx *x, char *err, size_t errlen)
{
    if (!cloud_runnable(x->req->cloud)) {
        snprintf(err, errlen,
                 "strategy 'cloud' needs cloud = claude, codex or gemini (cloud = %s means the calling model "
                 "answers itself)",
                 cloud_name(x->req->cloud));
        return -1;
    }
    sbuf out;
    sb_init(&out);
    char *t = cloud_text(x->req, x->req->context);
    int rc = do_cloud(x, "answer", t, &out, err, errlen);
    free(t);
    if (rc == 0) x->res->answer = sb_take(&out);
    sb_free(&out);
    return rc;
}

static int run_cascade(run_ctx *x, char *err, size_t errlen)
{
    int threshold = x->req->threshold >= 0 ? x->req->threshold : x->c->cascade_threshold;
    sbuf out;
    sb_init(&out);
    char *sys = join_system(SYS_CONFIDENCE, x->req->system);
    char *u = user_text(x->req->prompt, x->req->context);
    int rc = do_local(x, "local-attempt", sys, u, &out, err, errlen);
    free(sys);
    free(u);
    if (rc != 0) {
        sb_free(&out);
        if (!cloud_runnable(x->req->cloud)) return -1;
        add_note(x->res, "Local model failed (%s); answered by %s.", err, cloud_name(x->req->cloud));
        x->res->escalated = 1;
        return run_cloud(x, err, errlen);
    }
    char *draft = sb_take(&out);
    int conf = split_confidence(draft);
    x->res->confidence = conf;
    if (conf >= threshold && draft[0]) {
        x->res->answer = draft;
        return 0;
    }
    if (!cloud_runnable(x->req->cloud)) {
        x->res->answer = draft;
        x->res->needs_host = 1;
        if (conf < 0)
            add_note(x->res, "The local model gave no confidence score; verify this answer before relying on it.");
        else
            add_note(x->res,
                     "Local confidence %d%% is below the %d%% threshold; verify or improve this answer before "
                     "relying on it.",
                     conf, threshold);
        return 0;
    }
    x->res->escalated = 1;
    sbuf p;
    sb_init(&p);
    char *t = cloud_text(x->req, x->req->context);
    sb_puts(&p,
            "A smaller local model drafted an answer to the request below but was not confident. Give the correct, "
            "complete final answer. Keep what is right in the draft and fix what is wrong. Reply with the final "
            "answer only.\n\n");
    sb_puts(&p, t);
    free(t);
    sb_puts(&p, "\n\n<local_draft>\n");
    sb_puts(&p, draft);
    sb_puts(&p, "\n</local_draft>");
    sbuf fin;
    sb_init(&fin);
    rc = do_cloud(x, "cloud-escalation", p.s, &fin, err, errlen);
    sb_free(&p);
    if (rc != 0) {
        add_note(x->res, "Cloud escalation failed (%s); returning the low-confidence local answer.", err);
        x->res->needs_host = 1;
        x->res->answer = draft;
        sb_free(&fin);
        return 0;
    }
    free(draft);
    x->res->answer = sb_take(&fin);
    return 0;
}

static int run_draft_review(run_ctx *x, char *err, size_t errlen)
{
    sbuf out;
    sb_init(&out);
    char *sys = join_system(SYS_DRAFT, x->req->system);
    char *u = user_text(x->req->prompt, x->req->context);
    int rc = do_local(x, "local-draft", sys, u, &out, err, errlen);
    free(sys);
    free(u);
    if (rc != 0) {
        sb_free(&out);
        if (!cloud_runnable(x->req->cloud)) return -1;
        add_note(x->res, "Local draft failed (%s); answered by %s alone.", err, cloud_name(x->req->cloud));
        return run_cloud(x, err, errlen);
    }
    char *draft = sb_take(&out);
    if (!cloud_runnable(x->req->cloud)) {
        x->res->answer = draft;
        x->res->needs_host = 1;
        add_note(x->res, "This is a local draft: review it, fix any errors, and give the final answer.");
        return 0;
    }
    sbuf p;
    sb_init(&p);
    char *t = cloud_text(x->req, x->req->context);
    sb_puts(&p,
            "Review the draft answer that a smaller local model wrote for the request below. Fix errors, fill gaps, "
            "and tighten it. Reply with the improved final answer only.\n\n");
    sb_puts(&p, t);
    free(t);
    sb_puts(&p, "\n\n<draft>\n");
    sb_puts(&p, draft);
    sb_puts(&p, "\n</draft>");
    sbuf fin;
    sb_init(&fin);
    rc = do_cloud(x, "cloud-review", p.s, &fin, err, errlen);
    sb_free(&p);
    if (rc != 0) {
        add_note(x->res, "Cloud review failed (%s); returning the unreviewed local draft.", err);
        x->res->needs_host = 1;
        x->res->answer = draft;
        sb_free(&fin);
        return 0;
    }
    free(draft);
    x->res->answer = sb_take(&fin);
    return 0;
}

static int run_plan_execute(run_ctx *x, char *err, size_t errlen)
{
    char *plan = NULL;
    if (cloud_runnable(x->req->cloud)) {
        sbuf p;
        sb_init(&p);
        char *t = cloud_text(x->req, x->req->context);
        sb_puts(&p,
                "Write a short numbered plan (at most 8 steps) that a smaller local model can follow to complete the "
                "request below. Include key facts, decisions, and pitfalls it would not know. Output the plan only, "
                "not the final answer.\n\n");
        sb_puts(&p, t);
        free(t);
        sbuf out;
        sb_init(&out);
        int rc = do_cloud(x, "cloud-plan", p.s, &out, err, errlen);
        sb_free(&p);
        if (rc == 0) plan = sb_take(&out);
        else add_note(x->res, "Cloud planning failed (%s); the local model answered without a plan.", err);
        sb_free(&out);
    } else {
        add_note(x->res,
                 "No cloud CLI was used (cloud = %s): put your plan in the prompt; the local model carried out the "
                 "request as given.",
                 cloud_name(x->req->cloud));
        x->res->needs_host = 1;
    }
    sbuf u;
    sb_init(&u);
    char *ut = user_text(x->req->prompt, x->req->context);
    sb_printf(&u, "<request>\n%s\n</request>", ut);
    free(ut);
    if (plan) sb_printf(&u, "\n\n<plan>\n%s\n</plan>", plan);
    free(plan);
    char *sys = join_system(SYS_EXECUTE, x->req->system);
    sbuf out;
    sb_init(&out);
    int rc = do_local(x, "local-execute", sys, u.s, &out, err, errlen);
    free(sys);
    sb_free(&u);
    if (rc != 0) {
        sb_free(&out);
        if (!cloud_runnable(x->req->cloud)) return -1;
        add_note(x->res, "Local execution failed (%s); answered by %s alone.", err, cloud_name(x->req->cloud));
        return run_cloud(x, err, errlen);
    }
    x->res->answer = sb_take(&out);
    return 0;
}

static int run_compress(run_ctx *x, char *err, size_t errlen)
{
    const char *ctx = x->req->context;
    int prompt_only = !(ctx && *ctx);
    const char *material = prompt_only ? x->req->prompt : ctx;
    if (strlen(material) <= x->c->compress_threshold) {
        /* Nothing worth condensing. */
        if (cloud_runnable(x->req->cloud)) return run_cloud(x, err, errlen);
        add_note(x->res, "Input is short (%zu chars); nothing to condense, so the local model answered directly.",
                 strlen(material));
        x->res->needs_host = 1;
        return run_local(x, err, errlen);
    }
    sbuf condensed;
    sb_init(&condensed);
    int rc = condense(x, material, prompt_only ? "(the request is inside the text; keep every requirement)"
                                               : x->req->prompt,
                      &condensed, err, errlen);
    if (rc != 0) {
        sb_free(&condensed);
        if (!cloud_runnable(x->req->cloud)) return -1;
        add_note(x->res, "Local condensing failed (%s); sent the full input to %s.", err, cloud_name(x->req->cloud));
        return run_cloud(x, err, errlen);
    }
    if (!cloud_runnable(x->req->cloud)) {
        x->res->answer = sb_take(&condensed);
        x->res->needs_host = 1;
        add_note(x->res,
                 "This is the local model's condensed version of the input (%zu -> %zu chars). Answer from it "
                 "instead of the full text.",
                 strlen(material), strlen(x->res->answer));
        return 0;
    }
    sbuf out;
    sb_init(&out);
    char *t;
    if (prompt_only) {
        hybrid_req r2 = *x->req;
        r2.prompt = condensed.s;
        t = cloud_text(&r2, NULL);
    } else {
        t = cloud_text(x->req, condensed.s);
    }
    rc = do_cloud(x, "cloud-answer", t, &out, err, errlen);
    free(t);
    if (rc != 0) {
        add_note(x->res, "Cloud answer failed (%s); the local model answered from the condensed input.", err);
        x->res->needs_host = 1;
        hybrid_req r2 = *x->req;
        if (prompt_only) r2.prompt = condensed.s;
        else r2.context = condensed.s;
        run_ctx x2 = *x;
        x2.req = &r2;
        rc = run_local(&x2, err, errlen);
        sb_free(&condensed);
        sb_free(&out);
        return rc;
    }
    sb_free(&condensed);
    x->res->answer = sb_take(&out);
    return 0;
}

int hybrid_run(const config *c, const hybrid_req *req, hybrid_res *res, char *err, size_t errlen)
{
    memset(res, 0, sizeof *res);
    res->confidence = -1;
    res->trace = json_new_arr();
    if (!req->prompt || !*req->prompt) {
        snprintf(err, errlen, "prompt is required");
        return -1;
    }
    run_ctx x = {c, req, res, ""};
    strategy s = req->strat;
    if (s == S_AUTO) {
        size_t n = strlen(req->prompt) + (req->context ? strlen(req->context) : 0);
        s = n > c->compress_threshold ? S_COMPRESS : S_CASCADE;
    }
    res->used = s;
    switch (s) {
    case S_LOCAL: return run_local(&x, err, errlen);
    case S_CLOUD: return run_cloud(&x, err, errlen);
    case S_CASCADE: return run_cascade(&x, err, errlen);
    case S_DRAFT_REVIEW: return run_draft_review(&x, err, errlen);
    case S_PLAN_EXECUTE: return run_plan_execute(&x, err, errlen);
    case S_COMPRESS: return run_compress(&x, err, errlen);
    case S_AUTO: break;
    }
    snprintf(err, errlen, "unknown strategy");
    return -1;
}

void hybrid_res_free(hybrid_res *res)
{
    free(res->answer);
    free(res->note);
    json_free(res->trace);
    memset(res, 0, sizeof *res);
}

static const char *local_model_of(const hybrid_res *res)
{
    if (!res->trace) return NULL;
    for (size_t i = 0; i < res->trace->len; i++) {
        json *s = res->trace->items[i];
        const char *b = json_get_str(s, "backend");
        if (b && strcmp(b, "local") == 0) {
            const char *m = json_get_str(s, "model");
            if (m) return m;
        }
    }
    return NULL;
}

json *hybrid_res_json(const hybrid_res *res, const hybrid_req *req)
{
    json *o = json_new_obj();
    json_set_str(o, "answer", res->answer ? res->answer : "");
    json_set_str(o, "strategy", strategy_name(res->used));
    json_set_str(o, "requested_strategy", strategy_name(req->strat));
    json_set_str(o, "cloud", cloud_name(req->cloud));
    const char *lm = local_model_of(res);
    if (lm) json_set_str(o, "local_model", lm);
    if (res->confidence >= 0) json_set_num(o, "local_confidence", res->confidence);
    json_set_bool(o, "escalated", res->escalated);
    json_set_bool(o, "needs_host_review", res->needs_host);
    if (res->note) json_set_str(o, "note", res->note);
    json *u = json_new_obj();
    json_set_num(u, "local_tokens_est", (double)est_tokens(res->local_chars));
    json_set_num(u, "cloud_tokens_est", (double)est_tokens(res->cloud_chars));
    json_set(o, "usage", u);
    json_set(o, "trace", json_clone(res->trace));
    return o;
}

char *hybrid_res_summary(const hybrid_res *res, const hybrid_req *req)
{
    sbuf b;
    sb_init(&b);
    const char *lm = local_model_of(res);
    sb_printf(&b, "[hybrid] strategy=%s cloud=%s", strategy_name(res->used), cloud_name(req->cloud));
    if (lm) sb_printf(&b, " local_model=%s", lm);
    if (res->confidence >= 0) sb_printf(&b, " confidence=%d", res->confidence);
    sb_printf(&b, " escalated=%s local_tokens~%zu cloud_tokens~%zu", res->escalated ? "yes" : "no",
              est_tokens(res->local_chars), est_tokens(res->cloud_chars));
    if (res->note) sb_printf(&b, "\nNote: %s", res->note);
    return sb_take(&b);
}
