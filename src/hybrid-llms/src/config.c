/* config.c - runtime configuration (file + environment). */
#define _POSIX_C_SOURCE 200809L
#include "config.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "util.h"

#define CPY(dst, src) snprintf((dst), sizeof(dst), "%s", (src))

void config_defaults(config *c)
{
    memset(c, 0, sizeof *c);
    CPY(c->local_api, "managed");
    CPY(c->local_url, "http://127.0.0.1:11434");
    CPY(c->local_model, "");
    CPY(c->models_dir, "~/Documents/Models");
    CPY(c->llama_cmd, "llama-server -m {model} --host 127.0.0.1 --port {port} -c {ctx} --jinja");
    CPY(c->mlx_cmd, "mlx_lm.server --model {model} --host 127.0.0.1 --port {port}");
    c->engine_port = 8790;
    c->engine_ctx = 8192;
    c->engine_load_timeout = 300;
    c->engine_keep_alive = 1;
    c->local_timeout = 300;
    c->local_temperature = -1;
    c->local_num_ctx = 0;
    c->strip_think = 1;

    CPY(c->default_cloud, "claude");
    CPY(c->mcp_cloud, "host");
    CPY(c->claude_cmd, "claude -p --output-format text --strict-mcp-config");
    CPY(c->codex_cmd,
        "codex exec --skip-git-repo-check --ephemeral --sandbox read-only --color never "
        "--output-last-message {out} -");
    CPY(c->gemini_cmd, "gemini");
    c->cloud_timeout = 600;
    c->max_depth = 1;

    CPY(c->default_strategy, "auto");
    c->cascade_threshold = 70;
    c->compress_threshold = 12000;
    c->chunk_chars = 12000;
    c->max_output = 4u * 1024 * 1024;

    CPY(c->listen_addr, "127.0.0.1");
    c->port = 8787;
    c->max_body = 8u * 1024 * 1024;
    c->max_conns = 64;
}

static int parse_int(const char *v, long lo, long hi, long *out)
{
    char *end;
    errno = 0;
    long n = strtol(v, &end, 10);
    if (errno || end == v || *end != '\0' || n < lo || n > hi) return -1;
    *out = n;
    return 0;
}

static int set_str(char *dst, size_t cap, const char *v)
{
    if (strlen(v) >= cap) return -1;
    memcpy(dst, v, strlen(v) + 1);
    return 0;
}

#define S(name) \
    if (strcmp(key, #name) == 0) return set_str(c->name, sizeof c->name, val)
#define I(name, lo, hi)                                    \
    if (strcmp(key, #name) == 0) {                         \
        if (parse_int(val, (lo), (hi), &n) != 0) return -1; \
        c->name = (int)n;                                  \
        return 0;                                          \
    }
#define Z(name, lo, hi)                                    \
    if (strcmp(key, #name) == 0) {                         \
        if (parse_int(val, (lo), (hi), &n) != 0) return -1; \
        c->name = (size_t)n;                               \
        return 0;                                          \
    }

int config_set(config *c, const char *key, const char *val)
{
    long n;
    if (strcmp(key, "local_api") == 0) {
        if (!str_ieq(val, "managed") && !str_ieq(val, "ollama") && !str_ieq(val, "openai")) return -1;
        set_str(c->local_api, sizeof c->local_api, val);
        for (char *p = c->local_api; *p; p++)
            if (*p >= 'A' && *p <= 'Z') *p = (char)(*p - 'A' + 'a');
        return 0;
    }
    if (strcmp(key, "local_url") == 0) {
        if (strncmp(val, "http://", 7) != 0) return -1;
        int r = set_str(c->local_url, sizeof c->local_url, val);
        size_t L = strlen(c->local_url);
        while (L > 7 && c->local_url[L - 1] == '/') c->local_url[--L] = '\0';
        return r;
    }
    if (strcmp(key, "local_temperature") == 0) {
        char *end;
        errno = 0;
        double d = strtod(val, &end);
        if (errno || end == val || *end != '\0' || d > 2.0) return -1;
        c->local_temperature = d;
        return 0;
    }
    if (strcmp(key, "default_cloud") == 0 || strcmp(key, "mcp_cloud") == 0) {
        static const char *ok[] = {"host", "claude", "codex", "gemini", "none"};
        int valid = 0;
        for (size_t i = 0; i < sizeof ok / sizeof *ok; i++)
            if (strcmp(val, ok[i]) == 0) valid = 1;
        if (!valid) return -1;
        if (key[0] == 'd') return set_str(c->default_cloud, sizeof c->default_cloud, val);
        return set_str(c->mcp_cloud, sizeof c->mcp_cloud, val);
    }
    if (strcmp(key, "default_strategy") == 0) {
        static const char *ok[] = {"auto", "local", "cloud", "cascade", "draft-review", "plan-execute", "compress"};
        for (size_t i = 0; i < sizeof ok / sizeof *ok; i++)
            if (strcmp(val, ok[i]) == 0) return set_str(c->default_strategy, sizeof c->default_strategy, val);
        return -1;
    }
    S(local_model);
    S(models_dir);
    S(llama_cmd);
    S(mlx_cmd);
    I(engine_port, 1, 65535);
    I(engine_ctx, 256, 10000000);
    I(engine_load_timeout, 1, 86400);
    I(engine_keep_alive, 0, 1);
    S(local_api_key);
    S(claude_cmd);
    S(codex_cmd);
    S(gemini_cmd);
    S(listen_addr);
    S(token);
    I(local_timeout, 1, 86400);
    I(local_num_ctx, 0, 10000000);
    I(strip_think, 0, 1);
    I(cloud_timeout, 1, 86400);
    I(max_depth, 0, 8);
    I(cascade_threshold, 0, 100);
    I(port, 1, 65535);
    I(max_conns, 1, 4096);
    Z(compress_threshold, 0, 1L << 30);
    Z(chunk_chars, 1000, 1L << 26);
    Z(max_output, 4096, 1L << 30);
    Z(max_body, 1024, 1L << 30);
    return -1;
}

/* $XDG_CONFIG_HOME/hybrid-llms/config when it exists, else ~/.config/hybrid-llms/config.
 * (Codex starts MCP servers with a reduced environment, so ~/.config is the stable place.) */
static void default_path(char *out, size_t cap)
{
    const char *xdg = getenv("XDG_CONFIG_HOME");
    const char *home = getenv("HOME");
    out[0] = '\0';
    if (xdg && *xdg) {
        snprintf(out, cap, "%s/hybrid-llms/config", xdg);
        if (access(out, F_OK) == 0) return;
        out[0] = '\0';
    }
    if (home && *home) snprintf(out, cap, "%s/.config/hybrid-llms/config", home);
}

static int load_file(config *c, const char *path, int required, char *err, size_t errlen)
{
    FILE *f = fopen(path, "r");
    if (!f) {
        if (!required && errno == ENOENT) return 0;
        snprintf(err, errlen, "cannot open config %s: %s", path, strerror(errno));
        return -1;
    }
    char *line = NULL;
    size_t cap = 0;
    int lineno = 0;
    int rc = 0;
    while (getline(&line, &cap, f) >= 0) {
        lineno++;
        str_trim(line);
        if (line[0] == '\0' || line[0] == '#' || line[0] == ';') continue;
        char *eq = strchr(line, '=');
        if (!eq) {
            snprintf(err, errlen, "%s:%d: expected key = value", path, lineno);
            rc = -1;
            break;
        }
        *eq = '\0';
        char *key = str_trim(line);
        char *val = str_trim(eq + 1);
        size_t vl = strlen(val);
        if (vl >= 2 && ((val[0] == '"' && val[vl - 1] == '"') || (val[0] == '\'' && val[vl - 1] == '\''))) {
            val[vl - 1] = '\0';
            val++;
        }
        if (config_set(c, key, val) != 0) {
            snprintf(err, errlen, "%s:%d: unknown key or invalid value for '%s'", path, lineno, key);
            rc = -1;
            break;
        }
    }
    free(line);
    fclose(f);
    if (rc == 0) snprintf(c->loaded_from, sizeof c->loaded_from, "%s", path);
    return rc;
}

static const struct {
    const char *env;
    const char *key;
} env_map[] = {
    {"HYBRID_LLMS_LOCAL_API", "local_api"},
    {"HYBRID_LLMS_LOCAL_URL", "local_url"},
    {"HYBRID_LLMS_LOCAL_MODEL", "local_model"},
    {"HYBRID_LLMS_LOCAL_API_KEY", "local_api_key"},
    {"HYBRID_LLMS_MODELS_DIR", "models_dir"},
    {"HYBRID_LLMS_ENGINE_PORT", "engine_port"},
    {"HYBRID_LLMS_DEFAULT_CLOUD", "default_cloud"},
    {"HYBRID_LLMS_MCP_CLOUD", "mcp_cloud"},
    {"HYBRID_LLMS_CLAUDE_CMD", "claude_cmd"},
    {"HYBRID_LLMS_CODEX_CMD", "codex_cmd"},
    {"HYBRID_LLMS_GEMINI_CMD", "gemini_cmd"},
    {"HYBRID_LLMS_STRATEGY", "default_strategy"},
    {"HYBRID_LLMS_PORT", "port"},
    {"HYBRID_LLMS_LISTEN", "listen_addr"},
    {"HYBRID_LLMS_TOKEN", "token"},
};

int config_load(config *c, const char *path, char *err, size_t errlen)
{
    char p[1024];
    int required = 1;
    if (!path) {
        const char *envp = getenv("HYBRID_LLMS_CONFIG");
        if (envp && *envp) {
            path = envp;
        } else {
            default_path(p, sizeof p);
            path = p[0] ? p : NULL;
            required = 0;
        }
    }
    if (path && load_file(c, path, required, err, errlen) != 0) return -1;
    for (size_t i = 0; i < sizeof env_map / sizeof *env_map; i++) {
        const char *v = getenv(env_map[i].env);
        if (v && *v && config_set(c, env_map[i].key, v) != 0) {
            snprintf(err, errlen, "invalid value in %s", env_map[i].env);
            return -1;
        }
    }
    return 0;
}

void config_print(const config *c)
{
    if (c->loaded_from[0]) printf("# effective configuration (file: %s)\n", c->loaded_from);
    else printf("# effective configuration (no config file; defaults + environment)\n");
    printf("local_api = %s\nlocal_url = %s\nlocal_model = %s\n", c->local_api, c->local_url, c->local_model);
    printf("local_api_key = %s\n", c->local_api_key[0] ? "(set)" : "");
    printf("models_dir = %s\nllama_cmd = %s\nmlx_cmd = %s\n", c->models_dir, c->llama_cmd, c->mlx_cmd);
    printf("engine_port = %d\nengine_ctx = %d\nengine_load_timeout = %d\nengine_keep_alive = %d\n", c->engine_port,
           c->engine_ctx, c->engine_load_timeout, c->engine_keep_alive);
    printf("local_timeout = %d\n", c->local_timeout);
    if (c->local_temperature >= 0) printf("local_temperature = %g\n", c->local_temperature);
    printf("local_num_ctx = %d\nstrip_think = %d\n", c->local_num_ctx, c->strip_think);
    printf("default_cloud = %s\nmcp_cloud = %s\n", c->default_cloud, c->mcp_cloud);
    printf("claude_cmd = %s\ncodex_cmd = %s\ngemini_cmd = %s\n", c->claude_cmd, c->codex_cmd, c->gemini_cmd);
    printf("cloud_timeout = %d\nmax_depth = %d\n", c->cloud_timeout, c->max_depth);
    printf("default_strategy = %s\ncascade_threshold = %d\n", c->default_strategy, c->cascade_threshold);
    printf("compress_threshold = %zu\nchunk_chars = %zu\nmax_output = %zu\n", c->compress_threshold, c->chunk_chars,
           c->max_output);
    printf("listen_addr = %s\nport = %d\ntoken = %s\nmax_body = %zu\nmax_conns = %d\n", c->listen_addr, c->port,
           c->token[0] ? "(set)" : "", c->max_body, c->max_conns);
}
