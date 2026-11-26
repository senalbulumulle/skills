/* test_units.c - unit and in-process integration tests for hybrid-llms.
 * Run with `make test`. Uses a fake OpenAI-compatible server thread for the
 * local model and `cat` as a fake cloud CLI, so no model or network is needed. */
#define _POSIX_C_SOURCE 200809L
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include "cloud.h"
#include "config.h"
#include "engine.h"
#include "http.h"
#include "hybrid.h"
#include "json.h"
#include "local.h"
#include "proc.h"
#include "util.h"

static int failures = 0, checks = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        checks++;                                                            \
        if (!(cond)) {                                                       \
            failures++;                                                      \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);  \
        }                                                                    \
    } while (0)

static void test_json(void)
{
    const char *src = "{\"a\":[1,2.5,-3e2,true,false,null],\"s\":\"x\\n\\u00e9\\ud83d\\ude00\\\"\",\"o\":{}}";
    char err[128];
    json *j = json_parse(src, strlen(src), err, sizeof err);
    CHECK(j != NULL);
    if (!j) return;
    json *a = json_get(j, "a");
    CHECK(a && a->t == J_ARR && a->len == 6);
    CHECK(a->items[1]->n == 2.5);
    CHECK(a->items[2]->n == -300);
    CHECK(strcmp(json_get_str(j, "s"), "x\n\xc3\xa9\xf0\x9f\x98\x80\"") == 0);
    char *out = json_dump(j);
    json *j2 = json_parse(out, strlen(out), err, sizeof err);
    CHECK(j2 != NULL);
    char *out2 = j2 ? json_dump(j2) : NULL;
    CHECK(out2 && strcmp(out, out2) == 0);
    free(out);
    free(out2);
    json_free(j);
    json_free(j2);

    CHECK(json_parse("{\"a\":}", 6, err, sizeof err) == NULL);
    CHECK(json_parse("[1,]", 4, err, sizeof err) == NULL);
    CHECK(json_parse("\"abc", 4, err, sizeof err) == NULL);
    CHECK(json_parse("1 2", 3, err, sizeof err) == NULL);
    CHECK(json_parse("01", 2, err, sizeof err) == NULL);

    /* invalid UTF-8 is replaced on output */
    json *s = json_new_str("ok\xff\xfe");
    char *d = json_dump(s);
    CHECK(strcmp(d, "\"ok\\ufffd\\ufffd\"") == 0);
    free(d);
    json_free(s);

    json *n = json_new_num(42);
    d = json_dump(n);
    CHECK(strcmp(d, "42") == 0);
    free(d);
    json_free(n);
}

static void test_argv(void)
{
    argvec av;
    char err[128];
    CHECK(argv_split("codex exec --flag 'a b' \"c \\\"d\\\"\" e\\ f {out}", &av, err, sizeof err) == 0);
    CHECK(av.argc == 6);
    if (av.argc == 6) {
        CHECK(strcmp(av.argv[3], "a b") == 0);
        CHECK(strcmp(av.argv[4], "c \"d\"") == 0);
        CHECK(strcmp(av.argv[5], "e f") == 0);
    }
    argv_free(&av);
    CHECK(argv_split("x --o={out}.txt", &av, err, sizeof err) == 0);
    argv_subst(&av, "out", "/tmp/f");
    CHECK(strcmp(av.argv[1], "--o=/tmp/f.txt") == 0);
    argv_free(&av);
    CHECK(argv_split("bad 'quote", &av, err, sizeof err) != 0);
    CHECK(argv_split("   ", &av, err, sizeof err) != 0);
}

static void test_strings(void)
{
    char a[] = "  \x1b[1mhello\x1b[0m  ";
    str_strip_ansi(a);
    str_trim(a);
    CHECK(strcmp(a, "hello") == 0);
    char b[] = "<think>secret</think>Answer";
    str_strip_think(b);
    CHECK(strcmp(b, "Answer") == 0);
    strategy s;
    CHECK(strategy_parse("draft-review", &s) == 0 && s == S_DRAFT_REVIEW);
    CHECK(strategy_parse("nope", &s) != 0);
    cloud_id c;
    CHECK(cloud_parse("Gemini", &c) == 0 && c == CLOUD_GEMINI);
}

static void test_config(void)
{
    config c;
    config_defaults(&c);
    CHECK(strcmp(c.local_api, "managed") == 0);
    CHECK(strcmp(c.models_dir, "~/Documents/Models") == 0);
    CHECK(config_set(&c, "port", "9000") == 0 && c.port == 9000);
    CHECK(config_set(&c, "port", "99999") != 0);
    CHECK(config_set(&c, "local_api", "OpenAI") == 0 && strcmp(c.local_api, "openai") == 0);
    CHECK(config_set(&c, "local_url", "https://x") != 0);
    CHECK(config_set(&c, "local_url", "http://h:1/") == 0 && strcmp(c.local_url, "http://h:1") == 0);
    CHECK(config_set(&c, "nope", "1") != 0);
    CHECK(config_set(&c, "mcp_cloud", "codex") == 0);
    CHECK(config_set(&c, "default_cloud", "bard") != 0);
}

static void touch(const char *path, size_t size)
{
    FILE *f = fopen(path, "wb");
    if (!f) return;
    for (size_t i = 0; i < size; i++) fputc(0, f);
    fclose(f);
}

static void test_models(const char *root)
{
    char p[1024];
    snprintf(p, sizeof p, "%s/models", root);
    mkdir(p, 0700);
    snprintf(p, sizeof p, "%s/models/qwen2.5-coder-7b-q4_k_m.gguf", root);
    touch(p, 10);
    snprintf(p, sizeof p, "%s/models/mmproj-vision.gguf", root);
    touch(p, 1);
    snprintf(p, sizeof p, "%s/models/big", root);
    mkdir(p, 0700);
    snprintf(p, sizeof p, "%s/models/big/llama-70b-00001-of-00002.gguf", root);
    touch(p, 5);
    snprintf(p, sizeof p, "%s/models/big/llama-70b-00002-of-00002.gguf", root);
    touch(p, 5);
    snprintf(p, sizeof p, "%s/models/Qwen3-mlx", root);
    mkdir(p, 0700);
    snprintf(p, sizeof p, "%s/models/Qwen3-mlx/config.json", root);
    touch(p, 2);
    snprintf(p, sizeof p, "%s/models/Qwen3-mlx/model.safetensors", root);
    touch(p, 20);

    config c;
    config_defaults(&c);
    snprintf(c.models_dir, sizeof c.models_dir, "%s/models", root);
    model_list l;
    char err[512];
    CHECK(models_scan(&c, &l, err, sizeof err) == 0);
    CHECK(l.n == 3); /* qwen gguf, llama shard 1, mlx folder */
    int saw_mlx = 0;
    for (size_t i = 0; i < l.n; i++) {
        CHECK(strstr(l.v[i].name, "mmproj") == NULL);
        CHECK(strstr(l.v[i].name, "00002-of") == NULL);
        if (l.v[i].kind == MODEL_MLX) saw_mlx = 1;
    }
    CHECK(saw_mlx);
    models_free(&l);

    model_info m;
    CHECK(models_resolve(&c, "qwen2.5-coder-7b-q4_k_m", &m, err, sizeof err) == 0 && m.kind == MODEL_GGUF);
    model_info_free(&m);
    CHECK(models_resolve(&c, "qwen3", &m, err, sizeof err) == 0 && m.kind == MODEL_MLX);
    model_info_free(&m);
    CHECK(models_resolve(&c, "does-not-exist", &m, err, sizeof err) != 0);
    CHECK(models_resolve(&c, "", &m, err, sizeof err) == 0);
    model_info_free(&m);
}

/* ---------- fake local server ---------- */

static int fake_fd = -1;
static int fake_port = 0;
static const char *fake_reply = "hello";

static void *fake_server(void *arg)
{
    (void)arg;
    for (;;) {
        int fd = accept(fake_fd, NULL, NULL);
        if (fd < 0) return NULL;
        http_req req;
        if (http_read_request(fd, 1 << 20, 5, &req) == 0) {
            json *o = json_new_obj();
            json *choices = json_new_arr();
            json *ch = json_new_obj();
            json *msg = json_new_obj();
            json_set_str(msg, "role", "assistant");
            json_set_str(msg, "content", fake_reply);
            json_set(ch, "message", msg);
            json_push(choices, ch);
            json_set(o, "choices", choices);
            char *s = json_dump(o);
            http_send(fd, 200, "application/json", s, strlen(s));
            free(s);
            json_free(o);
            http_req_free(&req);
        }
        close(fd);
    }
}

static void start_fake(void)
{
    fake_fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    a.sin_port = 0;
    bind(fake_fd, (struct sockaddr *)&a, sizeof a);
    listen(fake_fd, 16);
    socklen_t sl = sizeof a;
    getsockname(fake_fd, (struct sockaddr *)&a, &sl);
    fake_port = ntohs(a.sin_port);
    pthread_t th;
    pthread_create(&th, NULL, fake_server, NULL);
    pthread_detach(th);
}

static void test_hybrid(void)
{
    start_fake();
    config c;
    config_defaults(&c);
    config_set(&c, "local_api", "openai");
    char url[64];
    snprintf(url, sizeof url, "http://127.0.0.1:%d/v1", fake_port);
    CHECK(config_set(&c, "local_url", url) == 0);
    config_set(&c, "local_model", "fake");
    config_set(&c, "claude_cmd", "cat"); /* the "cloud" echoes its prompt */
    char err[2048];

    sbuf out;
    sb_init(&out);
    CHECK(local_simple(&c, NULL, "hi", NULL, &out, NULL, 0, err, sizeof err) == 0);
    CHECK(out.s && strcmp(out.s, "hello") == 0);
    sb_free(&out);

    hybrid_req r;
    memset(&r, 0, sizeof r);
    r.prompt = "What is 2+2?";
    r.cloud = CLOUD_CLAUDE;
    r.threshold = -1;
    hybrid_res res;

    /* confident local answer: no escalation */
    fake_reply = "4\nCONFIDENCE: 95";
    r.strat = S_CASCADE;
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.answer && strcmp(res.answer, "4") == 0);
    CHECK(res.confidence == 95 && !res.escalated && res.cloud_chars == 0);
    hybrid_res_free(&res);

    /* unsure local answer: escalates to the cloud (cat echoes the prompt) */
    fake_reply = "5?\nConfidence: 20%";
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.escalated && res.confidence == 20);
    CHECK(res.answer && strstr(res.answer, "<local_draft>\n5?\n</local_draft>") != NULL);
    hybrid_res_free(&res);

    /* host mode: low confidence is handed back to the caller */
    r.cloud = CLOUD_HOST;
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(!res.escalated && res.needs_host && res.note != NULL);
    hybrid_res_free(&res);

    /* draft-review: cloud sees the draft */
    r.cloud = CLOUD_CLAUDE;
    r.strat = S_DRAFT_REVIEW;
    fake_reply = "draft text";
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.answer && strstr(res.answer, "<draft>\ndraft text\n</draft>") != NULL);
    hybrid_res_free(&res);

    /* plan-execute: local gets the cloud plan, returns its own text */
    r.strat = S_PLAN_EXECUTE;
    fake_reply = "final";
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.answer && strcmp(res.answer, "final") == 0 && res.trace->len == 2);
    hybrid_res_free(&res);

    /* compress: long context is condensed locally before the cloud call */
    char *big = xmalloc(30001);
    memset(big, 'x', 30000);
    big[30000] = '\0';
    r.strat = S_AUTO;
    r.context = big;
    fake_reply = "condensed";
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.used == S_COMPRESS);
    CHECK(res.answer && strstr(res.answer, "<context>\ncondensed") != NULL && strstr(res.answer, "xxxx") == NULL);
    hybrid_res_free(&res);
    free(big);
    r.context = NULL;

    /* @hybrid mentions never reach the cloud CLI */
    r.strat = S_CLOUD;
    r.prompt = "@hybrid say hi";
    CHECK(hybrid_run(&c, &r, &res, err, sizeof err) == 0);
    CHECK(res.answer && strstr(res.answer, "@hybrid") == NULL);
    hybrid_res_free(&res);

    /* recursion guard */
    setenv("HYBRID_LLMS_DEPTH", "1", 1);
    sb_init(&out);
    CHECK(cloud_ask(&c, CLOUD_CLAUDE, "x", &out, err, sizeof err) != 0);
    sb_free(&out);
    unsetenv("HYBRID_LLMS_DEPTH");

    /* missing CLI is reported, not crashed on */
    config_set(&c, "gemini_cmd", "definitely-not-a-real-cli-xyz");
    sb_init(&out);
    CHECK(cloud_ask(&c, CLOUD_GEMINI, "x", &out, err, sizeof err) != 0 && strstr(err, "not found") != NULL);
    sb_free(&out);
}

static void test_proc_timeout(void)
{
    char *argv[] = {"sleep", "5", NULL};
    sbuf o, e;
    sb_init(&o);
    sb_init(&e);
    int code, to;
    char err[128];
    long long t0 = now_ms();
    CHECK(proc_run(argv, NULL, NULL, 0, 1, 1024, &o, &e, &code, &to, err, sizeof err) == 0);
    CHECK(to == 1 && now_ms() - t0 < 4500);
    sb_free(&o);
    sb_free(&e);
}

int main(void)
{
    signal(SIGPIPE, SIG_IGN);
    g_log_level = LOG_ERROR;
    char root[] = "/tmp/hybrid-llms-test-XXXXXX";
    if (!mkdtemp(root)) {
        perror("mkdtemp");
        return 1;
    }
    test_json();
    test_argv();
    test_strings();
    test_config();
    test_models(root);
    test_hybrid();
    test_proc_timeout();
    char cmd[256];
    snprintf(cmd, sizeof cmd, "rm -rf '%s'", root);
    if (system(cmd) != 0) fprintf(stderr, "warning: could not remove %s\n", root);
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
