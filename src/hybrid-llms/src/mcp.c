/* mcp.c - Model Context Protocol server over stdio (JSON-RPC 2.0, one message per line).
 *
 * stdout carries protocol messages only; all logging goes to stderr. */
#define _POSIX_C_SOURCE 200809L
#include "mcp.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cloud.h"
#include "engine.h"
#include "hybrid.h"
#include "json.h"
#include "local.h"

static const config *g_cfg;
static pthread_mutex_t out_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t active_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t active_cv = PTHREAD_COND_INITIALIZER;
static int active_calls = 0;
static char client_name[128] = "unknown";

static const char *SUPPORTED_VERSIONS[] = {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"};

static const char *INSTRUCTIONS =
    "hybrid-llms runs a local language model (from ~/Documents/Models or a local server) and combines it with "
    "cloud models. When the user writes @hybrid (or asks for the hybrid / local model), call the `hybrid` tool "
    "with their request instead of answering it yourself. You are the cloud model by default (cloud = host): if "
    "the result says needs_host_review, check and improve the local answer before replying. Pass long files or logs "
    "in `context` with strategy `compress` to save your own tokens.";

static void send_msg(json *msg)
{
    char *s = json_dump(msg);
    pthread_mutex_lock(&out_mu);
    fputs(s, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    pthread_mutex_unlock(&out_mu);
    free(s);
}

static void send_result(const json *id, json *result)
{
    json *m = json_new_obj();
    json_set_str(m, "jsonrpc", "2.0");
    json_set(m, "id", json_clone(id));
    json_set(m, "result", result);
    send_msg(m);
    json_free(m);
}

static void send_error(const json *id, int code, const char *message)
{
    json *m = json_new_obj();
    json_set_str(m, "jsonrpc", "2.0");
    json_set(m, "id", id ? json_clone(id) : json_new_null());
    json *e = json_new_obj();
    json_set_num(e, "code", code);
    json_set_str(e, "message", message);
    json_set(m, "error", e);
    send_msg(m);
    json_free(m);
}

/* ---------- tool definitions ---------- */

static json *prop(const char *type, const char *desc)
{
    json *p = json_new_obj();
    json_set_str(p, "type", type);
    json_set_str(p, "description", desc);
    return p;
}

static json *enum_prop(const char *desc, const char *const *vals, size_t n)
{
    json *p = prop("string", desc);
    json *e = json_new_arr();
    for (size_t i = 0; i < n; i++) json_push(e, json_new_str(vals[i]));
    json_set(p, "enum", e);
    return p;
}

static json *schema(json *props, const char *const *required, size_t nreq)
{
    json *s = json_new_obj();
    json_set_str(s, "type", "object");
    json_set(s, "properties", props);
    json *r = json_new_arr();
    for (size_t i = 0; i < nreq; i++) json_push(r, json_new_str(required[i]));
    json_set(s, "required", r);
    json_set_bool(s, "additionalProperties", 0);
    return s;
}

static json *tool(const char *name, const char *title, const char *desc, json *input_schema, int read_only)
{
    json *t = json_new_obj();
    json_set_str(t, "name", name);
    json_set_str(t, "title", title);
    json_set_str(t, "description", desc);
    json_set(t, "inputSchema", input_schema);
    json *ann = json_new_obj();
    json_set_bool(ann, "readOnlyHint", read_only);
    json_set_bool(ann, "openWorldHint", !read_only);
    json_set(t, "annotations", ann);
    return t;
}

static json *tools_list(void)
{
    static const char *strategies[] = {"auto", "local", "cloud", "cascade", "draft-review", "plan-execute", "compress"};
    static const char *clouds[] = {"host", "claude", "codex", "gemini"};
    static const char *run_clouds[] = {"claude", "codex", "gemini"};
    json *arr = json_new_arr();

    json *p = json_new_obj();
    json_set(p, "prompt", prop("string", "The user's request, verbatim (without the @hybrid mention)."));
    json_set(p, "strategy",
             enum_prop("How local and cloud models work together. auto (default): compress if the input is long, "
                       "else cascade. cascade: local answers and scores its confidence; low confidence escalates to "
                       "the cloud. draft-review: local drafts, cloud reviews. plan-execute: cloud plans, local "
                       "executes. compress: local condenses `context`, cloud answers from it. local / cloud: one side "
                       "only.",
                       strategies, sizeof strategies / sizeof *strategies));
    json_set(p, "cloud",
             enum_prop("Cloud model for the cloud steps. host (default): you, the calling model, take the cloud role "
                       "and the cloud steps come back to you. claude, codex, gemini: run that CLI headlessly.",
                       clouds, sizeof clouds / sizeof *clouds));
    json_set(p, "context", prop("string", "Optional long material (file contents, logs, docs) the request is about."));
    json_set(p, "system", prop("string", "Optional extra instructions for the models."));
    json_set(p, "local_model",
             prop("string", "Optional local model: a file or folder name (or part of one) in the models directory."));
    json_set(p, "threshold", prop("integer", "Optional cascade confidence threshold, 0-100."));
    static const char *req_prompt[] = {"prompt"};
    json_push(arr, tool("hybrid", "Hybrid local + cloud LLM",
                        "Use when the user writes @hybrid or asks to use the hybrid or local model. Runs the request "
                        "on the local language model and combines it with a cloud model (you by default) using a "
                        "strategy that saves cloud tokens. Returns the answer and a summary line; when "
                        "needs_host_review is reported, verify and improve the answer before replying.",
                        schema(p, req_prompt, 1), 0));

    p = json_new_obj();
    json_set(p, "prompt", prop("string", "Prompt for the local model."));
    json_set(p, "system", prop("string", "Optional system prompt."));
    json_set(p, "model", prop("string", "Optional local model name (or part of one)."));
    json_push(arr, tool("local_generate", "Local model",
                        "Send a prompt straight to the local language model and return its reply. Good for cheap "
                        "subtasks: summaries, boilerplate, drafts, classification, rewriting.",
                        schema(p, req_prompt, 1), 1));

    p = json_new_obj();
    json_set(p, "prompt", prop("string", "Prompt for the cloud model."));
    json_set(p, "cloud", enum_prop("Which cloud CLI to run.", run_clouds, 3));
    static const char *req_cloud[] = {"prompt", "cloud"};
    json_push(arr, tool("cloud_ask", "Ask another cloud model",
                        "Ask a cloud model CLI (claude, codex, or gemini) headlessly and return its reply, for a "
                        "second opinion from a different model.",
                        schema(p, req_cloud, 2), 0));

    json_push(arr, tool("local_models", "List local models",
                        "List the local models hybrid-llms can use (GGUF files and MLX folders in the models "
                        "directory, or the models of the configured local server).",
                        schema(json_new_obj(), NULL, 0), 1));

    json_push(arr, tool("hybrid_status", "Hybrid status",
                        "Show the hybrid-llms configuration: local backend, running engine, available models, and "
                        "which cloud CLIs are installed.",
                        schema(json_new_obj(), NULL, 0), 1));
    return arr;
}

/* ---------- tool calls ---------- */

static json *text_result(const char *text, const char *extra, int is_error)
{
    json *r = json_new_obj();
    json *content = json_new_arr();
    json *t = json_new_obj();
    json_set_str(t, "type", "text");
    json_set_str(t, "text", text);
    json_push(content, t);
    if (extra) {
        json *t2 = json_new_obj();
        json_set_str(t2, "type", "text");
        json_set_str(t2, "text", extra);
        json_push(content, t2);
    }
    json_set(r, "content", content);
    json_set_bool(r, "isError", is_error);
    return r;
}

static json *call_hybrid(const json *args)
{
    char err[2048] = "";
    hybrid_req req;
    memset(&req, 0, sizeof req);
    req.prompt = json_get_str(args, "prompt");
    req.system = json_get_str(args, "system");
    req.context = json_get_str(args, "context");
    req.local_model = json_get_str(args, "local_model");
    req.threshold = (int)json_get_num(args, "threshold", -1);
    if (req.threshold > 100) req.threshold = 100;
    const char *s = json_get_str(args, "strategy");
    if (strategy_parse(s ? s : g_cfg->default_strategy, &req.strat) != 0) return text_result("unknown strategy", NULL, 1);
    const char *cl = json_get_str(args, "cloud");
    if (cloud_parse(cl ? cl : g_cfg->mcp_cloud, &req.cloud) != 0) return text_result("unknown cloud", NULL, 1);
    if (!req.prompt || !*req.prompt) return text_result("prompt is required", NULL, 1);

    hybrid_res res;
    int rc = hybrid_run(g_cfg, &req, &res, err, sizeof err);
    json *out;
    if (rc != 0) {
        char msg[2200];
        snprintf(msg, sizeof msg, "hybrid-llms failed: %s", err);
        out = text_result(msg, NULL, 1);
    } else {
        char *summary = hybrid_res_summary(&res, &req);
        out = text_result(res.answer, summary, 0);
        free(summary);
    }
    hybrid_res_free(&res);
    return out;
}

static json *call_local(const json *args)
{
    const char *prompt = json_get_str(args, "prompt");
    if (!prompt || !*prompt) return text_result("prompt is required", NULL, 1);
    char err[2048] = "", used[512] = "";
    sbuf out;
    sb_init(&out);
    int rc = local_simple(g_cfg, json_get_str(args, "system"), prompt, json_get_str(args, "model"), &out, used,
                          sizeof used, err, sizeof err);
    json *r;
    if (rc != 0) {
        r = text_result(err, NULL, 1);
    } else {
        char meta[700];
        snprintf(meta, sizeof meta, "[hybrid] local_model=%s", used);
        r = text_result(out.s ? out.s : "", meta, 0);
    }
    sb_free(&out);
    return r;
}

static json *call_cloud(const json *args)
{
    const char *prompt = json_get_str(args, "prompt");
    const char *cl = json_get_str(args, "cloud");
    cloud_id id;
    if (!prompt || !*prompt) return text_result("prompt is required", NULL, 1);
    if (!cl || cloud_parse(cl, &id) != 0 || id == CLOUD_HOST || id == CLOUD_NONE)
        return text_result("cloud must be claude, codex, or gemini", NULL, 1);
    char err[2048] = "";
    sbuf out;
    sb_init(&out);
    int rc = cloud_ask(g_cfg, id, prompt, &out, err, sizeof err);
    json *r = rc == 0 ? text_result(out.s ? out.s : "", NULL, 0) : text_result(err, NULL, 1);
    sb_free(&out);
    return r;
}

static json *call_models(void)
{
    char err[1024] = "";
    json *m = local_models_json(g_cfg, err, sizeof err);
    if (!m) return text_result(err, NULL, 1);
    char *s = json_dump(m);
    json_free(m);
    json *r = text_result(s, NULL, 0);
    free(s);
    return r;
}

static json *call_status(void)
{
    json *o = json_new_obj();
    json_set_str(o, "version", HYBRID_VERSION);
    json_set_str(o, "client", client_name);
    json_set(o, "local", local_status_json(g_cfg));
    json_set(o, "cloud", cloud_status_json(g_cfg));
    json_set_str(o, "mcp_cloud_default", g_cfg->mcp_cloud);
    json_set_str(o, "default_strategy", g_cfg->default_strategy);
    char *s = json_dump(o);
    json_free(o);
    json *r = text_result(s, NULL, 0);
    free(s);
    return r;
}

typedef struct {
    json *id;
    char *name;
    json *args;
} call_job;

static void *call_thread(void *arg)
{
    call_job *job = arg;
    json *empty = json_new_obj();
    const json *a = (job->args && job->args->t == J_OBJ) ? job->args : empty;
    json *result;
    if (strcmp(job->name, "hybrid") == 0) result = call_hybrid(a);
    else if (strcmp(job->name, "local_generate") == 0) result = call_local(a);
    else if (strcmp(job->name, "cloud_ask") == 0) result = call_cloud(a);
    else if (strcmp(job->name, "local_models") == 0) result = call_models();
    else if (strcmp(job->name, "hybrid_status") == 0) result = call_status();
    else result = NULL;
    if (result) {
        send_result(job->id, result);
    } else {
        char msg[300];
        snprintf(msg, sizeof msg, "Unknown tool: %.200s", job->name);
        send_error(job->id, -32602, msg);
    }
    json_free(empty);
    json_free(job->id);
    json_free(job->args);
    free(job->name);
    free(job);
    pthread_mutex_lock(&active_mu);
    active_calls--;
    pthread_cond_broadcast(&active_cv);
    pthread_mutex_unlock(&active_mu);
    return NULL;
}

/* ---------- prompts ---------- */

static json *prompts_list(void)
{
    json *arr = json_new_arr();
    json *p = json_new_obj();
    json_set_str(p, "name", "hybrid");
    json_set_str(p, "title", "Ask hybrid-llms");
    json_set_str(p, "description", "Send a request through hybrid-llms (local model + cloud model).");
    json *args = json_new_arr();
    json *a = json_new_obj();
    json_set_str(a, "name", "request");
    json_set_str(a, "description", "What to ask");
    json_set_bool(a, "required", 1);
    json_push(args, a);
    json_set(p, "arguments", args);
    json_push(arr, p);
    return arr;
}

static json *prompt_get(const json *params, char *err, size_t errlen)
{
    const char *name = json_get_str(params, "name");
    if (!name || strcmp(name, "hybrid") != 0) {
        snprintf(err, errlen, "Unknown prompt: %.200s", name ? name : "(none)");
        return NULL;
    }
    const char *request = json_get_str(json_get(params, "arguments"), "request");
    sbuf b;
    sb_init(&b);
    sb_printf(&b,
              "Call the `hybrid` tool from the hybrid MCP server with this request as `prompt` (choose a strategy "
              "that fits; default auto). Then give me the answer, and if it reports needs_host_review, check and "
              "improve it first.\n\nRequest: %s",
              request ? request : "");
    json *r = json_new_obj();
    json_set_str(r, "description", "hybrid-llms request");
    json *msgs = json_new_arr();
    json *m = json_new_obj();
    json_set_str(m, "role", "user");
    json *content = json_new_obj();
    json_set_str(content, "type", "text");
    json_set(content, "text", json_new_strn(b.s ? b.s : "", b.len));
    json_set(m, "content", content);
    json_push(msgs, m);
    json_set(r, "messages", msgs);
    sb_free(&b);
    return r;
}

/* ---------- dispatch ---------- */

static void handle(json *msg)
{
    if (msg->t != J_OBJ) {
        send_error(NULL, -32600, "Invalid Request");
        return;
    }
    const json *id = json_get(msg, "id");
    const char *method = json_get_str(msg, "method");
    json *params = json_get(msg, "params");
    if (!method) {
        /* A response to a request we never send, or garbage: ignore responses, reject the rest. */
        if (id && !json_get(msg, "result") && !json_get(msg, "error")) send_error(id, -32600, "Invalid Request");
        return;
    }
    if (!id) {
        /* Notifications (initialized, cancelled, ...) need no reply. */
        return;
    }
    if (strcmp(method, "initialize") == 0) {
        const char *want = json_get_str(params, "protocolVersion");
        const char *ver = SUPPORTED_VERSIONS[1];
        for (size_t i = 0; want && i < sizeof SUPPORTED_VERSIONS / sizeof *SUPPORTED_VERSIONS; i++)
            if (strcmp(want, SUPPORTED_VERSIONS[i]) == 0) ver = SUPPORTED_VERSIONS[i];
        const char *cn = json_get_str(json_get(params, "clientInfo"), "name");
        if (cn) snprintf(client_name, sizeof client_name, "%s", cn);
        log_msg(LOG_INFO, "MCP client '%s' connected (protocol %s)", client_name, ver);
        json *r = json_new_obj();
        json_set_str(r, "protocolVersion", ver);
        json *caps = json_new_obj();
        json *tc = json_new_obj();
        json_set_bool(tc, "listChanged", 0);
        json_set(caps, "tools", tc);
        json *pc = json_new_obj();
        json_set_bool(pc, "listChanged", 0);
        json_set(caps, "prompts", pc);
        json_set(r, "capabilities", caps);
        json *si = json_new_obj();
        json_set_str(si, "name", "hybrid-llms");
        json_set_str(si, "title", "Hybrid LLMs");
        json_set_str(si, "version", HYBRID_VERSION);
        json_set(r, "serverInfo", si);
        json_set_str(r, "instructions", INSTRUCTIONS);
        send_result(id, r);
    } else if (strcmp(method, "ping") == 0) {
        send_result(id, json_new_obj());
    } else if (strcmp(method, "tools/list") == 0) {
        json *r = json_new_obj();
        json_set(r, "tools", tools_list());
        send_result(id, r);
    } else if (strcmp(method, "tools/call") == 0) {
        const char *name = json_get_str(params, "name");
        if (!name) {
            send_error(id, -32602, "Missing tool name");
            return;
        }
        call_job *job = xcalloc(1, sizeof *job);
        job->id = json_clone(id);
        job->name = xstrdup(name);
        job->args = json_clone(json_get(params, "arguments"));
        pthread_mutex_lock(&active_mu);
        active_calls++;
        pthread_mutex_unlock(&active_mu);
        pthread_t th;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        pthread_attr_setstacksize(&attr, 1024 * 1024);
        if (pthread_create(&th, &attr, call_thread, job) != 0) {
            pthread_attr_destroy(&attr);
            call_thread(job); /* run inline; it decrements active_calls */
            return;
        }
        pthread_attr_destroy(&attr);
    } else if (strcmp(method, "prompts/list") == 0) {
        json *r = json_new_obj();
        json_set(r, "prompts", prompts_list());
        send_result(id, r);
    } else if (strcmp(method, "prompts/get") == 0) {
        char err[300];
        json *r = prompt_get(params, err, sizeof err);
        if (r) send_result(id, r);
        else send_error(id, -32602, err);
    } else if (strcmp(method, "resources/list") == 0) {
        json *r = json_new_obj();
        json_set(r, "resources", json_new_arr());
        send_result(id, r);
    } else if (strcmp(method, "resources/templates/list") == 0) {
        json *r = json_new_obj();
        json_set(r, "resourceTemplates", json_new_arr());
        send_result(id, r);
    } else {
        send_error(id, -32601, "Method not found");
    }
}

int mcp_main(const config *c)
{
    g_cfg = c;
    char *line = NULL;
    size_t cap = 0;
    ssize_t n;
    while ((n = getline(&line, &cap, stdin)) >= 0) {
        while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = '\0';
        if (n == 0) continue;
        char perr[128];
        json *msg = json_parse(line, (size_t)n, perr, sizeof perr);
        if (!msg) {
            send_error(NULL, -32700, "Parse error");
            continue;
        }
        /* Batches are not part of current MCP versions; reject them as invalid. */
        if (msg->t == J_ARR) send_error(NULL, -32600, "Invalid Request: batches are not supported");
        else handle(msg);
        json_free(msg);
    }
    free(line);
    pthread_mutex_lock(&active_mu);
    while (active_calls > 0) pthread_cond_wait(&active_cv, &active_mu);
    pthread_mutex_unlock(&active_mu);
    engine_shutdown_owned(c);
    return 0;
}
