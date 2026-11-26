/* server.c - HTTP daemon with an OpenAI-compatible API plus /v1/hybrid.
 *
 *   GET  /health                 liveness (no auth)
 *   GET  /v1/models              virtual models: hybrid..., local..., cloud...
 *   GET  /v1/status              backend status
 *   POST /v1/chat/completions    OpenAI chat completions (stream supported as one chunk)
 *   POST /v1/hybrid              {prompt, strategy, cloud, context, system, local_model, threshold}
 *
 * Model names for chat completions:
 *   hybrid | hybrid/<strategy> | hybrid/<strategy>/<cloud>
 *   local  | local/<model>
 *   claude | codex | gemini | cloud/<cloud>
 */
#define _POSIX_C_SOURCE 200809L
#include "server.h"

#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "cloud.h"
#include "engine.h"
#include "http.h"
#include "hybrid.h"
#include "json.h"
#include "local.h"

static const config *g_cfg;
static volatile sig_atomic_t g_stop = 0;
static pthread_mutex_t conn_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t conn_cv = PTHREAD_COND_INITIALIZER;
static int active_conns = 0;
static unsigned long long req_counter = 0;

static void on_signal(int sig)
{
    (void)sig;
    g_stop = g_stop + 1; /* a second signal stops waiting for in-flight requests */
}

static void send_json(int fd, int status, json *body)
{
    char *s = json_dump(body);
    http_send(fd, status, "application/json", s, strlen(s));
    free(s);
}

static void send_error_json(int fd, int status, const char *type, const char *message)
{
    json *o = json_new_obj();
    json *e = json_new_obj();
    json_set_str(e, "message", message);
    json_set_str(e, "type", type);
    json_set(o, "error", e);
    send_json(fd, status, o);
    json_free(o);
}

static int token_ok(const http_req *r)
{
    const char *tok = g_cfg->token;
    if (!tok[0]) return 1;
    const char *a = r->authorization;
    if (strncmp(a, "Bearer ", 7) != 0) return 0;
    a += 7;
    size_t la = strlen(a), lt = strlen(tok);
    unsigned char diff = (unsigned char)(la != lt);
    for (size_t i = 0; i < lt; i++) diff |= (unsigned char)(tok[i] ^ (i < la ? a[i] : 0));
    return diff == 0;
}

/* Text of an OpenAI message content: string or array of {type:"text", text}. */
static void content_text(const json *content, sbuf *out)
{
    if (!content) return;
    if (content->t == J_STR) {
        sb_append(out, content->s, content->slen);
        return;
    }
    if (content->t != J_ARR) return;
    for (size_t i = 0; i < content->len; i++) {
        const json *part = content->items[i];
        const char *type = json_get_str(part, "type");
        const char *text = json_get_str(part, "text");
        if (text && (!type || strcmp(type, "text") == 0)) {
            if (out->len) sb_puts(out, "\n");
            sb_puts(out, text);
        }
    }
}

/* Normalized [{role, content:string}] copy of the request messages. */
static json *normalize_messages(const json *msgs)
{
    json *arr = json_new_arr();
    for (size_t i = 0; i < msgs->len; i++) {
        const json *m = msgs->items[i];
        const char *role = json_get_str(m, "role");
        if (!role) continue;
        if (strcmp(role, "developer") == 0) role = "system";
        if (strcmp(role, "system") && strcmp(role, "user") && strcmp(role, "assistant")) continue;
        sbuf t;
        sb_init(&t);
        content_text(json_get(m, "content"), &t);
        json *n = json_new_obj();
        json_set_str(n, "role", role);
        json_set(n, "content", json_new_strn(t.s ? t.s : "", t.len));
        json_push(arr, n);
        sb_free(&t);
    }
    return arr;
}

/* Fold messages into (system, prompt). Multi-turn history becomes a transcript. */
static void flatten(const json *msgs, sbuf *system, sbuf *prompt)
{
    size_t last_user = (size_t)-1, convo = 0;
    for (size_t i = 0; i < msgs->len; i++) {
        const char *role = json_get_str(msgs->items[i], "role");
        if (strcmp(role, "system") == 0) {
            if (system->len) sb_puts(system, "\n\n");
            sb_puts(system, json_get_str(msgs->items[i], "content"));
        } else {
            convo++;
            if (strcmp(role, "user") == 0) last_user = i;
        }
    }
    if (convo == 1 && last_user != (size_t)-1) {
        sb_puts(prompt, json_get_str(msgs->items[last_user], "content"));
        return;
    }
    sb_puts(prompt, "Continue this conversation by replying to the last user message.\n\n");
    for (size_t i = 0; i < msgs->len; i++) {
        const char *role = json_get_str(msgs->items[i], "role");
        if (strcmp(role, "system") == 0) continue;
        sb_printf(prompt, "%s: %s\n\n", strcmp(role, "user") == 0 ? "User" : "Assistant",
                  json_get_str(msgs->items[i], "content"));
    }
}

typedef struct {
    int kind; /* 0 hybrid, 1 local, 2 cloud */
    strategy strat;
    cloud_id cloud;
    char local_model[512];
} route;

static int parse_model(const char *model, route *r, char *err, size_t errlen)
{
    memset(r, 0, sizeof r[0]);
    if (strategy_parse(g_cfg->default_strategy, &r->strat) != 0) r->strat = S_AUTO;
    if (cloud_parse(g_cfg->default_cloud, &r->cloud) != 0) r->cloud = CLOUD_CLAUDE;
    if (!model || !*model || strcmp(model, "hybrid") == 0) return 0;
    if (strncmp(model, "hybrid/", 7) == 0) {
        char buf[256];
        snprintf(buf, sizeof buf, "%s", model + 7);
        char *slash = strchr(buf, '/');
        if (slash) *slash++ = '\0';
        if (strategy_parse(buf, &r->strat) != 0) {
            snprintf(err, errlen, "unknown strategy '%s' in model name", buf);
            return -1;
        }
        if (slash && cloud_parse(slash, &r->cloud) != 0) {
            snprintf(err, errlen, "unknown cloud '%s' in model name", slash);
            return -1;
        }
        return 0;
    }
    if (strcmp(model, "local") == 0 || strncmp(model, "local/", 6) == 0) {
        r->kind = 1;
        if (model[5] == '/') snprintf(r->local_model, sizeof r->local_model, "%s", model + 6);
        return 0;
    }
    const char *cn = strncmp(model, "cloud/", 6) == 0 ? model + 6 : model;
    if (cloud_parse(cn, &r->cloud) == 0 && r->cloud != CLOUD_HOST && r->cloud != CLOUD_NONE) {
        r->kind = 2;
        return 0;
    }
    snprintf(err, errlen, "unknown model '%s' (see GET /v1/models)", model);
    return -1;
}

static void send_sse_completion(int fd, const char *id, const char *model, long created, const char *content)
{
    const char *hdr = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n"
                      "Connection: close\r\n\r\n";
    if (write_all(fd, hdr, strlen(hdr)) != 0) return;
    for (int phase = 0; phase < 2; phase++) {
        json *chunk = json_new_obj();
        json_set_str(chunk, "id", id);
        json_set_str(chunk, "object", "chat.completion.chunk");
        json_set_num(chunk, "created", (double)created);
        json_set_str(chunk, "model", model);
        json *choices = json_new_arr();
        json *ch = json_new_obj();
        json_set_num(ch, "index", 0);
        json *delta = json_new_obj();
        if (phase == 0) {
            json_set_str(delta, "role", "assistant");
            json_set_str(delta, "content", content);
            json_set(ch, "finish_reason", json_new_null());
        } else {
            json_set_str(ch, "finish_reason", "stop");
        }
        json_set(ch, "delta", delta);
        json_push(choices, ch);
        json_set(chunk, "choices", choices);
        char *s = json_dump(chunk);
        json_free(chunk);
        sbuf b;
        sb_init(&b);
        sb_printf(&b, "data: %s\n\n", s);
        free(s);
        int rc = write_all(fd, b.s, b.len);
        sb_free(&b);
        if (rc != 0) return;
    }
    write_all(fd, "data: [DONE]\n\n", 14);
}

static void handle_chat(int fd, const json *body)
{
    char err[2048] = "";
    const json *msgs = json_get(body, "messages");
    if (!msgs || msgs->t != J_ARR || msgs->len == 0) {
        send_error_json(fd, 400, "invalid_request_error", "'messages' must be a non-empty array");
        return;
    }
    const char *model = json_get_str(body, "model");
    route r;
    if (parse_model(model, &r, err, sizeof err) != 0) {
        send_error_json(fd, 400, "invalid_request_error", err);
        return;
    }
    json *norm = normalize_messages(msgs);
    if (norm->len == 0) {
        json_free(norm);
        send_error_json(fd, 400, "invalid_request_error", "no system/user/assistant messages");
        return;
    }
    /* Optional extension: "hybrid": {"strategy", "cloud", "context", "threshold", "local_model"} */
    const json *ext = json_get(body, "hybrid");
    if (ext && ext->t == J_OBJ) {
        const char *s = json_get_str(ext, "strategy");
        const char *cl = json_get_str(ext, "cloud");
        const char *lm = json_get_str(ext, "local_model");
        if (s && strategy_parse(s, &r.strat) != 0) {
            json_free(norm);
            send_error_json(fd, 400, "invalid_request_error", "unknown hybrid.strategy");
            return;
        }
        if (cl && cloud_parse(cl, &r.cloud) != 0) {
            json_free(norm);
            send_error_json(fd, 400, "invalid_request_error", "unknown hybrid.cloud");
            return;
        }
        if (lm) snprintf(r.local_model, sizeof r.local_model, "%s", lm);
    }

    sbuf answer;
    sb_init(&answer);
    json *hinfo = NULL;
    size_t in_chars = 0;
    int rc = 0;
    for (size_t i = 0; i < norm->len; i++) in_chars += strlen(json_get_str(norm->items[i], "content"));

    if (r.kind == 1) {
        char used[512];
        rc = local_chat(g_cfg, norm, r.local_model[0] ? r.local_model : NULL, &answer, used, sizeof used, err,
                        sizeof err);
    } else {
        sbuf sys, prompt;
        sb_init(&sys);
        sb_init(&prompt);
        flatten(norm, &sys, &prompt);
        hybrid_req hr;
        memset(&hr, 0, sizeof hr);
        hr.prompt = prompt.s ? prompt.s : "";
        hr.system = sys.s;
        hr.strat = r.kind == 2 ? S_CLOUD : r.strat;
        hr.cloud = r.cloud;
        hr.local_model = r.local_model[0] ? r.local_model : NULL;
        hr.threshold = -1;
        if (ext && ext->t == J_OBJ) {
            hr.context = json_get_str(ext, "context");
            hr.threshold = (int)json_get_num(ext, "threshold", -1);
        }
        hybrid_res res;
        rc = hybrid_run(g_cfg, &hr, &res, err, sizeof err);
        if (rc == 0) {
            sb_puts(&answer, res.answer);
            hinfo = hybrid_res_json(&res, &hr);
            json_set(hinfo, "answer", json_new_null());
        }
        hybrid_res_free(&res);
        sb_free(&sys);
        sb_free(&prompt);
    }
    json_free(norm);
    if (rc != 0) {
        json_free(hinfo);
        sb_free(&answer);
        send_error_json(fd, 502, "backend_error", err);
        return;
    }

    char id[64];
    pthread_mutex_lock(&conn_mu);
    unsigned long long n = ++req_counter;
    pthread_mutex_unlock(&conn_mu);
    snprintf(id, sizeof id, "chatcmpl-hybrid-%lld-%llu", (long long)time(NULL), n);
    long created = (long)time(NULL);
    const char *model_out = model && *model ? model : "hybrid";

    if (json_get_bool(body, "stream", 0)) {
        send_sse_completion(fd, id, model_out, created, answer.s ? answer.s : "");
        json_free(hinfo);
        sb_free(&answer);
        return;
    }
    json *o = json_new_obj();
    json_set_str(o, "id", id);
    json_set_str(o, "object", "chat.completion");
    json_set_num(o, "created", (double)created);
    json_set_str(o, "model", model_out);
    json *choices = json_new_arr();
    json *ch = json_new_obj();
    json_set_num(ch, "index", 0);
    json *msg = json_new_obj();
    json_set_str(msg, "role", "assistant");
    json_set(msg, "content", json_new_strn(answer.s ? answer.s : "", answer.len));
    json_set(ch, "message", msg);
    json_set_str(ch, "finish_reason", "stop");
    json_push(choices, ch);
    json_set(o, "choices", choices);
    json *usage = json_new_obj();
    json_set_num(usage, "prompt_tokens", (double)est_tokens(in_chars));
    json_set_num(usage, "completion_tokens", (double)est_tokens(answer.len));
    json_set_num(usage, "total_tokens", (double)(est_tokens(in_chars) + est_tokens(answer.len)));
    json_set(o, "usage", usage);
    if (hinfo) json_set(o, "hybrid", hinfo);
    send_json(fd, 200, o);
    json_free(o);
    sb_free(&answer);
}

static void handle_hybrid(int fd, const json *body)
{
    char err[2048] = "";
    hybrid_req hr;
    memset(&hr, 0, sizeof hr);
    hr.prompt = json_get_str(body, "prompt");
    hr.system = json_get_str(body, "system");
    hr.context = json_get_str(body, "context");
    hr.local_model = json_get_str(body, "local_model");
    hr.threshold = (int)json_get_num(body, "threshold", -1);
    const char *s = json_get_str(body, "strategy");
    const char *cl = json_get_str(body, "cloud");
    if (strategy_parse(s ? s : g_cfg->default_strategy, &hr.strat) != 0) {
        send_error_json(fd, 400, "invalid_request_error", "unknown strategy");
        return;
    }
    if (cloud_parse(cl ? cl : g_cfg->default_cloud, &hr.cloud) != 0) {
        send_error_json(fd, 400, "invalid_request_error", "unknown cloud");
        return;
    }
    if (!hr.prompt || !*hr.prompt) {
        send_error_json(fd, 400, "invalid_request_error", "'prompt' is required");
        return;
    }
    hybrid_res res;
    if (hybrid_run(g_cfg, &hr, &res, err, sizeof err) != 0) {
        hybrid_res_free(&res);
        send_error_json(fd, 502, "backend_error", err);
        return;
    }
    json *o = hybrid_res_json(&res, &hr);
    hybrid_res_free(&res);
    send_json(fd, 200, o);
    json_free(o);
}

static void handle_models(int fd)
{
    json *o = json_new_obj();
    json_set_str(o, "object", "list");
    json *data = json_new_arr();
    const char *fixed[] = {"hybrid",       "hybrid/auto",     "hybrid/cascade", "hybrid/draft-review",
                           "hybrid/plan-execute", "hybrid/compress", "local",          "cloud/claude",
                           "cloud/codex",  "cloud/gemini"};
    long created = (long)time(NULL);
    for (size_t i = 0; i < sizeof fixed / sizeof *fixed; i++) {
        json *m = json_new_obj();
        json_set_str(m, "id", fixed[i]);
        json_set_str(m, "object", "model");
        json_set_num(m, "created", (double)created);
        json_set_str(m, "owned_by", "hybrid-llms");
        json_push(data, m);
    }
    char err[512];
    json *locals = local_models_json(g_cfg, err, sizeof err);
    if (locals) {
        for (size_t i = 0; i < locals->len; i++) {
            const char *n = json_get_str(locals->items[i], "name");
            if (!n) continue;
            char id[1100];
            snprintf(id, sizeof id, "local/%s", n);
            json *m = json_new_obj();
            json_set_str(m, "id", id);
            json_set_str(m, "object", "model");
            json_set_num(m, "created", (double)created);
            json_set_str(m, "owned_by", "local");
            json_push(data, m);
        }
        json_free(locals);
    }
    json_set(o, "data", data);
    send_json(fd, 200, o);
    json_free(o);
}

static void handle_status(int fd)
{
    json *o = json_new_obj();
    json_set_str(o, "version", HYBRID_VERSION);
    json_set(o, "local", local_status_json(g_cfg));
    json_set(o, "cloud", cloud_status_json(g_cfg));
    json_set_str(o, "default_cloud", g_cfg->default_cloud);
    json_set_str(o, "default_strategy", g_cfg->default_strategy);
    send_json(fd, 200, o);
    json_free(o);
}

static void serve_conn(int fd)
{
    http_req req;
    int st = http_read_request(fd, g_cfg->max_body, 30, &req);
    if (st != 0) {
        if (st > 0) send_error_json(fd, st, "invalid_request_error", http_reason(st));
        return;
    }
    char path[2048];
    snprintf(path, sizeof path, "%s", req.path);
    char *q = strchr(path, '?');
    if (q) *q = '\0';
    log_msg(LOG_DEBUG, "%s %s", req.method, path);

    if (strcmp(path, "/health") == 0) {
        json *o = json_new_obj();
        json_set_str(o, "status", "ok");
        json_set_str(o, "version", HYBRID_VERSION);
        send_json(fd, 200, o);
        json_free(o);
        goto done;
    }
    if (!token_ok(&req)) {
        send_error_json(fd, 401, "authentication_error", "missing or invalid bearer token");
        goto done;
    }
    int is_get = strcmp(req.method, "GET") == 0;
    int is_post = strcmp(req.method, "POST") == 0;
    if (strcmp(path, "/v1/models") == 0 || strcmp(path, "/models") == 0) {
        if (!is_get) goto bad_method;
        handle_models(fd);
    } else if (strcmp(path, "/v1/status") == 0) {
        if (!is_get) goto bad_method;
        handle_status(fd);
    } else if (strcmp(path, "/v1/chat/completions") == 0 || strcmp(path, "/chat/completions") == 0 ||
               strcmp(path, "/v1/hybrid") == 0) {
        if (!is_post) goto bad_method;
        char perr[160];
        json *body = req.body_len ? json_parse(req.body, req.body_len, perr, sizeof perr) : NULL;
        if (!body || body->t != J_OBJ) {
            char m[220];
            snprintf(m, sizeof m, "request body must be a JSON object%s%s", body ? "" : ": ", body ? "" : perr);
            if (!req.body_len) snprintf(m, sizeof m, "request body is empty");
            json_free(body);
            send_error_json(fd, 400, "invalid_request_error", m);
            goto done;
        }
        if (strcmp(path, "/v1/hybrid") == 0) handle_hybrid(fd, body);
        else handle_chat(fd, body);
        json_free(body);
    } else {
        send_error_json(fd, 404, "not_found", "unknown endpoint");
    }
    goto done;
bad_method:
    send_error_json(fd, 405, "invalid_request_error", "method not allowed");
done:
    http_req_free(&req);
}

static void *conn_thread(void *arg)
{
    int fd = (int)(intptr_t)arg;
    serve_conn(fd);
    shutdown(fd, SHUT_WR);
    close(fd);
    pthread_mutex_lock(&conn_mu);
    active_conns--;
    pthread_cond_broadcast(&conn_cv);
    pthread_mutex_unlock(&conn_mu);
    return NULL;
}

static int open_listener(const config *c, char *err, size_t errlen)
{
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;
    char port[16];
    snprintf(port, sizeof port, "%d", c->port);
    int gai = getaddrinfo(c->listen_addr[0] ? c->listen_addr : NULL, port, &hints, &res);
    if (gai != 0) {
        snprintf(err, errlen, "listen address %s: %s", c->listen_addr, gai_strerror(gai));
        return -1;
    }
    int fd = -1, last = 0;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0) {
            last = errno;
            continue;
        }
        int one = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
        fcntl(fd, F_SETFD, FD_CLOEXEC);
        if (bind(fd, ai->ai_addr, ai->ai_addrlen) == 0 && listen(fd, 128) == 0) break;
        last = errno;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) snprintf(err, errlen, "cannot listen on %s:%d: %s", c->listen_addr, c->port, strerror(last));
    return fd;
}

int server_main(const config *c)
{
    g_cfg = c;
    char err[512];
    int lfd = open_listener(c, err, sizeof err);
    if (lfd < 0) {
        log_msg(LOG_ERROR, "%s", err);
        return 1;
    }
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0; /* no SA_RESTART: accept() must return EINTR */
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    log_msg(LOG_INFO, "hybrid-llms %s listening on http://%s:%d (local=%s, default cloud=%s)%s", HYBRID_VERSION,
            c->listen_addr, c->port, c->local_api, c->default_cloud, c->token[0] ? " [token required]" : "");
    if (!c->token[0] && strcmp(c->listen_addr, "127.0.0.1") != 0 && strcmp(c->listen_addr, "::1") != 0 &&
        strcmp(c->listen_addr, "localhost") != 0)
        log_msg(LOG_WARN, "listening on a non-loopback address without a token; set token in the config");

    while (!g_stop) {
        int cfd = accept(lfd, NULL, NULL);
        if (cfd < 0) {
            if (errno == EINTR || errno == ECONNABORTED) continue;
            log_msg(LOG_ERROR, "accept: %s", strerror(errno));
            struct timespec ts = {0, 100 * 1000000L};
            nanosleep(&ts, NULL);
            continue;
        }
        fcntl(cfd, F_SETFD, FD_CLOEXEC);
#ifdef SO_NOSIGPIPE
        int one = 1;
        setsockopt(cfd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#endif
        pthread_mutex_lock(&conn_mu);
        int busy = active_conns >= c->max_conns;
        if (!busy) active_conns++;
        pthread_mutex_unlock(&conn_mu);
        if (busy) {
            send_error_json(cfd, 503, "server_busy", "too many concurrent requests");
            close(cfd);
            continue;
        }
        pthread_t th;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        if (pthread_create(&th, &attr, conn_thread, (void *)(intptr_t)cfd) != 0) {
            pthread_mutex_lock(&conn_mu);
            active_conns--;
            pthread_mutex_unlock(&conn_mu);
            send_error_json(cfd, 503, "server_busy", "cannot start worker");
            close(cfd);
        }
        pthread_attr_destroy(&attr);
    }
    close(lfd);
    log_msg(LOG_INFO, "shutting down; waiting for %d request(s)", active_conns);
    pthread_mutex_lock(&conn_mu);
    while (active_conns > 0) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 1;
        pthread_cond_timedwait(&conn_cv, &conn_mu, &ts);
        if (g_stop > 1) break;
    }
    pthread_mutex_unlock(&conn_mu);
    engine_shutdown_owned(c);
    return 0;
}
