/* config.h - runtime configuration (file + environment). */
#ifndef HYBRID_CONFIG_H
#define HYBRID_CONFIG_H

#include <stddef.h>

typedef struct {
    /* local backend */
    char local_api[16];   /* "managed", "ollama" or "openai" */
    char local_url[512];  /* http://host:port (ollama / openai) */
    char local_model[512]; /* managed: file/folder name or substring; else model id */
    char models_dir[1024]; /* managed: where GGUF files / MLX folders live */
    char llama_cmd[1024];  /* managed: command for GGUF models */
    char mlx_cmd[1024];    /* managed: command for MLX folders */
    int engine_port;       /* managed: port the engine listens on */
    int engine_ctx;        /* managed: context size passed as {ctx} */
    int engine_load_timeout; /* seconds to wait for the engine to load */
    int engine_keep_alive; /* 1 = leave the engine running for other sessions */
    char local_api_key[512];
    int local_timeout;    /* seconds */
    double local_temperature; /* < 0 = backend default */
    int local_num_ctx;    /* 0 = backend default (ollama only) */
    int strip_think;      /* remove <think> blocks from local output */

    /* cloud CLIs */
    char default_cloud[16]; /* cloud for CLI/HTTP requests */
    char mcp_cloud[16];     /* cloud for MCP requests; "host" = the calling CLI */
    char claude_cmd[1024];
    char codex_cmd[1024];
    char gemini_cmd[1024];
    int cloud_timeout;      /* seconds */
    int max_depth;          /* nested cloud calls allowed (recursion guard) */

    /* strategies */
    char default_strategy[32];
    int cascade_threshold;  /* 0..100 */
    size_t compress_threshold; /* chars of context before auto -> compress */
    size_t chunk_chars;
    size_t max_output;      /* bytes captured from a subprocess */

    /* http server */
    char listen_addr[128];
    int port;
    char token[256];
    size_t max_body;
    int max_conns;

    char loaded_from[1024];
} config;

void config_defaults(config *c);
/* Load from path (or the default location when NULL), then apply env overrides.
 * A missing default file is not an error. Returns 0 on success. */
int config_load(config *c, const char *path, char *err, size_t errlen);
/* Set one key; returns 0 on success, -1 for unknown key / bad value. */
int config_set(config *c, const char *key, const char *val);
void config_print(const config *c);

#endif
