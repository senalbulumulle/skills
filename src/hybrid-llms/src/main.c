/* main.c - hybrid-llms command line entry point. */
#define _POSIX_C_SOURCE 200809L
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "cloud.h"
#include "config.h"
#include "engine.h"
#include "hybrid.h"
#include "json.h"
#include "local.h"
#include "mcp.h"
#include "server.h"
#include "util.h"

static void usage(FILE *f)
{
    fprintf(f,
            "hybrid-llms %s - hybrid local + cloud language model server\n"
            "\n"
            "Usage: hybrid-llms [--config FILE] [-v|-q] <command> [options]\n"
            "\n"
            "Commands:\n"
            "  serve [--port N] [--listen ADDR]   run the HTTP daemon (OpenAI-compatible API + /v1/hybrid)\n"
            "  mcp                                run the MCP stdio server (used by Claude Code, Codex, Gemini)\n"
            "  ask [options] [PROMPT...]          run one hybrid request (prompt from stdin if omitted or '-')\n"
            "      -s, --strategy S   auto|local|cloud|cascade|draft-review|plan-execute|compress\n"
            "      -c, --cloud C      claude|codex|gemini|none\n"
            "      -m, --model M      local model (file/folder name or part of one)\n"
            "      -f, --context-file FILE   long context for the request ('-' = stdin)\n"
            "      --system TEXT      extra instructions\n"
            "      --threshold N      cascade confidence threshold (0-100)\n"
            "      --json             print the full JSON result (trace, usage)\n"
            "  local [-m M] [--system T] [PROMPT...]   ask the local model only\n"
            "  cloud <claude|codex|gemini> [PROMPT...] ask a cloud CLI only\n"
            "  models                             list local models\n"
            "  engine start [MODEL] | stop | status   manage the local inference engine\n"
            "  status                             show backends and installed CLIs (JSON)\n"
            "  config                             print the effective configuration\n"
            "  version | help\n"
            "\n"
            "Config: $HYBRID_LLMS_CONFIG or ~/.config/hybrid-llms/config (key = value). Local models are\n"
            "discovered in models_dir (default ~/Documents/Models): *.gguf files run with llama-server, MLX\n"
            "folders run with mlx_lm.server.\n",
            HYBRID_VERSION);
}

static char *read_stream(FILE *f)
{
    sbuf b;
    sb_init(&b);
    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) sb_append(&b, buf, n);
    return sb_take(&b);
}

static char *read_path(const char *path, char *err, size_t errlen)
{
    if (strcmp(path, "-") == 0) return read_stream(stdin);
    FILE *f = fopen(path, "rb");
    if (!f) {
        snprintf(err, errlen, "cannot open %s", path);
        return NULL;
    }
    char *s = read_stream(f);
    fclose(f);
    return s;
}

/* Join remaining args as the prompt, or read stdin when there are none / "-". */
static char *prompt_from(int argc, char **argv, int i, int stdin_taken)
{
    if (i >= argc || (i == argc - 1 && strcmp(argv[i], "-") == 0)) {
        if (stdin_taken) return xstrdup("");
        if (isatty(STDIN_FILENO)) fprintf(stderr, "(reading prompt from stdin; end with Ctrl-D)\n");
        char *s = read_stream(stdin);
        return str_trim(s);
    }
    sbuf b;
    sb_init(&b);
    for (; i < argc; i++) {
        if (b.len) sb_putc(&b, ' ');
        sb_puts(&b, argv[i]);
    }
    return sb_take(&b);
}

static int need_arg(int argc, char **argv, int i)
{
    if (i + 1 >= argc) {
        fprintf(stderr, "hybrid-llms: %s needs a value\n", argv[i]);
        return 0;
    }
    return 1;
}

static int cmd_ask(const config *c, int argc, char **argv)
{
    hybrid_req req;
    memset(&req, 0, sizeof req);
    req.threshold = -1;
    if (strategy_parse(c->default_strategy, &req.strat) != 0) req.strat = S_AUTO;
    if (cloud_parse(c->default_cloud, &req.cloud) != 0) req.cloud = CLOUD_CLAUDE;
    int as_json = 0;
    char *context = NULL;
    int stdin_taken = 0;
    char err[2048] = "";
    int i = 0;
    for (; i < argc; i++) {
        const char *a = argv[i];
        if (strcmp(a, "--") == 0) {
            i++;
            break;
        }
        if (a[0] != '-' || strcmp(a, "-") == 0) break;
        if (!strcmp(a, "-s") || !strcmp(a, "--strategy")) {
            if (!need_arg(argc, argv, i)) return 2;
            if (strategy_parse(argv[++i], &req.strat) != 0) {
                fprintf(stderr, "hybrid-llms: unknown strategy '%s'\n", argv[i]);
                return 2;
            }
        } else if (!strcmp(a, "-c") || !strcmp(a, "--cloud")) {
            if (!need_arg(argc, argv, i)) return 2;
            if (cloud_parse(argv[++i], &req.cloud) != 0 || req.cloud == CLOUD_HOST) {
                fprintf(stderr, "hybrid-llms: cloud must be claude, codex, gemini or none\n");
                return 2;
            }
        } else if (!strcmp(a, "-m") || !strcmp(a, "--model")) {
            if (!need_arg(argc, argv, i)) return 2;
            req.local_model = argv[++i];
        } else if (!strcmp(a, "-f") || !strcmp(a, "--context-file")) {
            if (!need_arg(argc, argv, i)) return 2;
            free(context);
            if (strcmp(argv[i + 1], "-") == 0) stdin_taken = 1;
            context = read_path(argv[++i], err, sizeof err);
            if (!context) {
                fprintf(stderr, "hybrid-llms: %s\n", err);
                return 1;
            }
        } else if (!strcmp(a, "--system")) {
            if (!need_arg(argc, argv, i)) return 2;
            req.system = argv[++i];
        } else if (!strcmp(a, "--threshold")) {
            if (!need_arg(argc, argv, i)) return 2;
            req.threshold = atoi(argv[++i]);
            if (req.threshold < 0 || req.threshold > 100) {
                fprintf(stderr, "hybrid-llms: threshold must be 0-100\n");
                return 2;
            }
        } else if (!strcmp(a, "--json")) {
            as_json = 1;
        } else {
            fprintf(stderr, "hybrid-llms: unknown option '%s'\n", a);
            return 2;
        }
    }
    char *prompt = prompt_from(argc, argv, i, stdin_taken);
    if (!prompt[0]) {
        fprintf(stderr, "hybrid-llms: empty prompt\n");
        free(prompt);
        free(context);
        return 2;
    }
    req.prompt = prompt;
    req.context = context;
    hybrid_res res;
    int rc = hybrid_run(c, &req, &res, err, sizeof err);
    if (rc != 0) {
        fprintf(stderr, "hybrid-llms: %s\n", err);
    } else if (as_json) {
        json *o = hybrid_res_json(&res, &req);
        char *s = json_dump(o);
        puts(s);
        free(s);
        json_free(o);
    } else {
        puts(res.answer);
        char *sum = hybrid_res_summary(&res, &req);
        fprintf(stderr, "%s\n", sum);
        free(sum);
    }
    hybrid_res_free(&res);
    free(prompt);
    free(context);
    return rc == 0 ? 0 : 1;
}

static int cmd_local(const config *c, int argc, char **argv)
{
    const char *model = NULL, *system = NULL;
    int i = 0;
    for (; i < argc; i++) {
        if (!strcmp(argv[i], "--")) {
            i++;
            break;
        }
        if (!strcmp(argv[i], "-m") || !strcmp(argv[i], "--model")) {
            if (!need_arg(argc, argv, i)) return 2;
            model = argv[++i];
        } else if (!strcmp(argv[i], "--system")) {
            if (!need_arg(argc, argv, i)) return 2;
            system = argv[++i];
        } else if (argv[i][0] == '-' && argv[i][1]) {
            fprintf(stderr, "hybrid-llms: unknown option '%s'\n", argv[i]);
            return 2;
        } else {
            break;
        }
    }
    char *prompt = prompt_from(argc, argv, i, 0);
    if (!prompt[0]) {
        fprintf(stderr, "hybrid-llms: empty prompt\n");
        free(prompt);
        return 2;
    }
    char err[2048] = "", used[512] = "";
    sbuf out;
    sb_init(&out);
    int rc = local_simple(c, system, prompt, model, &out, used, sizeof used, err, sizeof err);
    if (rc == 0) {
        puts(out.s ? out.s : "");
        fprintf(stderr, "[hybrid] local_model=%s\n", used);
    } else {
        fprintf(stderr, "hybrid-llms: %s\n", err);
    }
    sb_free(&out);
    free(prompt);
    return rc == 0 ? 0 : 1;
}

static int cmd_cloud(const config *c, int argc, char **argv)
{
    cloud_id id;
    if (argc < 1 || cloud_parse(argv[0], &id) != 0 || id == CLOUD_HOST || id == CLOUD_NONE) {
        fprintf(stderr, "usage: hybrid-llms cloud <claude|codex|gemini> [PROMPT...]\n");
        return 2;
    }
    char *prompt = prompt_from(argc, argv, 1, 0);
    if (!prompt[0]) {
        fprintf(stderr, "hybrid-llms: empty prompt\n");
        free(prompt);
        return 2;
    }
    char err[2048] = "";
    sbuf out;
    sb_init(&out);
    int rc = cloud_ask(c, id, prompt, &out, err, sizeof err);
    if (rc == 0) puts(out.s ? out.s : "");
    else fprintf(stderr, "hybrid-llms: %s\n", err);
    sb_free(&out);
    free(prompt);
    return rc == 0 ? 0 : 1;
}

static int cmd_models(const config *c)
{
    char err[1024] = "";
    json *m = local_models_json(c, err, sizeof err);
    if (!m) {
        fprintf(stderr, "hybrid-llms: %s\n", err);
        return 1;
    }
    if (m->len == 0) printf("(no models found)\n");
    for (size_t i = 0; i < m->len; i++) {
        const char *name = json_get_str(m->items[i], "name");
        const char *kind = json_get_str(m->items[i], "kind");
        double gb = json_get_num(m->items[i], "size_gb", -1);
        if (kind) printf("%-6s %8.2f GB  %s\n", kind, gb, name);
        else printf("%s\n", name);
    }
    json_free(m);
    return 0;
}

static int cmd_engine(const config *c, int argc, char **argv)
{
    char err[2048] = "";
    if (strcmp(c->local_api, "managed") != 0) {
        fprintf(stderr, "hybrid-llms: the engine is only used with local_api = managed (current: %s)\n", c->local_api);
        return 1;
    }
    if (argc >= 1 && strcmp(argv[0], "start") == 0) {
        model_info mi;
        if (models_resolve(c, argc >= 2 ? argv[1] : c->local_model, &mi, err, sizeof err) != 0) {
            fprintf(stderr, "hybrid-llms: %s\n", err);
            return 1;
        }
        char base[128], field[4200];
        int rc = engine_ensure(c, &mi, base, sizeof base, field, sizeof field, err, sizeof err);
        if (rc == 0) printf("engine ready: %s (%s) at %s\n", mi.name, model_kind_name(mi.kind), base);
        else fprintf(stderr, "hybrid-llms: %s\n", err);
        model_info_free(&mi);
        return rc == 0 ? 0 : 1;
    }
    if (argc >= 1 && strcmp(argv[0], "stop") == 0) {
        if (engine_stop(c, err, sizeof err) != 0) {
            fprintf(stderr, "hybrid-llms: %s\n", err);
            return 1;
        }
        printf("engine stopped\n");
        return 0;
    }
    if (argc >= 1 && strcmp(argv[0], "status") == 0) {
        json *o = engine_status_json(c);
        char *s = json_dump(o);
        puts(s);
        free(s);
        json_free(o);
        return 0;
    }
    fprintf(stderr, "usage: hybrid-llms engine start [MODEL] | stop | status\n");
    return 2;
}

static int cmd_status(const config *c)
{
    json *o = json_new_obj();
    json_set_str(o, "version", HYBRID_VERSION);
    json_set(o, "local", local_status_json(c));
    json_set(o, "cloud", cloud_status_json(c));
    json_set_str(o, "default_cloud", c->default_cloud);
    json_set_str(o, "mcp_cloud", c->mcp_cloud);
    json_set_str(o, "default_strategy", c->default_strategy);
    char *s = json_dump(o);
    puts(s);
    free(s);
    json_free(o);
    return 0;
}

int main(int argc, char **argv)
{
    signal(SIGPIPE, SIG_IGN);
    const char *config_path = NULL;
    int i = 1;
    int verbosity = 0;
    for (; i < argc; i++) {
        if (!strcmp(argv[i], "--config")) {
            if (!need_arg(argc, argv, i)) return 2;
            config_path = argv[++i];
        } else if (!strcmp(argv[i], "-v") || !strcmp(argv[i], "--verbose")) {
            verbosity = 1;
        } else if (!strcmp(argv[i], "-q") || !strcmp(argv[i], "--quiet")) {
            verbosity = -1;
        } else {
            break;
        }
    }
    if (i >= argc || !strcmp(argv[i], "help") || !strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
        usage(i >= argc ? stderr : stdout);
        return i >= argc ? 2 : 0;
    }
    const char *cmd = argv[i++];
    if (!strcmp(cmd, "version") || !strcmp(cmd, "--version")) {
        printf("hybrid-llms %s\n", HYBRID_VERSION);
        return 0;
    }

    config cfg;
    config_defaults(&cfg);
    char err[1200] = "";
    if (config_load(&cfg, config_path, err, sizeof err) != 0) {
        fprintf(stderr, "hybrid-llms: %s\n", err);
        return 1;
    }
    /* CLI commands stay quiet unless -v; daemons log at info. */
    int daemon = !strcmp(cmd, "serve") || !strcmp(cmd, "mcp");
    g_log_level = daemon ? LOG_INFO : LOG_WARN;
    if (verbosity > 0) g_log_level = LOG_DEBUG;
    if (verbosity < 0) g_log_level = LOG_ERROR;

    int rc;
    if (!strcmp(cmd, "serve")) {
        for (; i < argc; i++) {
            if (!strcmp(argv[i], "--port") && need_arg(argc, argv, i)) {
                if (config_set(&cfg, "port", argv[++i]) != 0) {
                    fprintf(stderr, "hybrid-llms: invalid port\n");
                    return 2;
                }
            } else if (!strcmp(argv[i], "--listen") && need_arg(argc, argv, i)) {
                if (config_set(&cfg, "listen_addr", argv[++i]) != 0) {
                    fprintf(stderr, "hybrid-llms: invalid listen address\n");
                    return 2;
                }
            } else {
                fprintf(stderr, "hybrid-llms: unknown serve option '%s'\n", argv[i]);
                return 2;
            }
        }
        rc = server_main(&cfg);
    } else if (!strcmp(cmd, "mcp")) {
        rc = mcp_main(&cfg);
    } else if (!strcmp(cmd, "ask")) {
        rc = cmd_ask(&cfg, argc - i, argv + i);
    } else if (!strcmp(cmd, "local")) {
        rc = cmd_local(&cfg, argc - i, argv + i);
    } else if (!strcmp(cmd, "cloud")) {
        rc = cmd_cloud(&cfg, argc - i, argv + i);
    } else if (!strcmp(cmd, "models")) {
        rc = cmd_models(&cfg);
    } else if (!strcmp(cmd, "engine")) {
        rc = cmd_engine(&cfg, argc - i, argv + i);
    } else if (!strcmp(cmd, "status")) {
        rc = cmd_status(&cfg);
    } else if (!strcmp(cmd, "config")) {
        config_print(&cfg);
        rc = 0;
    } else {
        fprintf(stderr, "hybrid-llms: unknown command '%s'\n\n", cmd);
        usage(stderr);
        return 2;
    }
    if (!daemon) engine_shutdown_owned(&cfg);
    return rc;
}
