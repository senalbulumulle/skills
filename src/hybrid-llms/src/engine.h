/* engine.h - local model discovery (models_dir) and the managed inference engine.
 *
 * GGUF files are served with llama.cpp's llama-server; MLX model folders
 * (config.json + *.safetensors) with mlx_lm.server. Both expose an
 * OpenAI-compatible API on 127.0.0.1:<engine_port>. One engine runs per port and
 * is shared by every hybrid-llms process (CLI, daemon, MCP servers) through a
 * lock file and a state file in the cache directory. */
#ifndef HYBRID_ENGINE_H
#define HYBRID_ENGINE_H

#include <stddef.h>

#include "config.h"
#include "json.h"

enum { MODEL_GGUF = 1, MODEL_MLX = 2 };

typedef struct {
    char *path; /* absolute path */
    char *name; /* path relative to models_dir */
    int kind;
    long long size; /* bytes (GGUF file or sum of MLX weights) */
} model_info;

typedef struct {
    model_info *v;
    size_t n;
} model_list;

/* Expand a leading "~/" using $HOME. */
void expand_home(const char *in, char *out, size_t cap);

int models_scan(const config *c, model_list *out, char *err, size_t errlen);
void models_free(model_list *l);
/* Pick a model: absolute path, exact relative name, basename (with or without
 * .gguf), then case-insensitive substring. Empty want = first model found.
 * out must be released with model_info_free. */
int models_resolve(const config *c, const char *want, model_info *out, char *err, size_t errlen);
void model_info_free(model_info *m);
const char *model_kind_name(int kind);

/* Make sure an engine serving m is running and ready. Fills base_url
 * ("http://127.0.0.1:PORT") and the "model" value to send in requests. */
int engine_ensure(const config *c, const model_info *m, char *base_url, size_t bcap, char *model_field, size_t mcap,
                  char *err, size_t errlen);
/* Stop the engine on c->engine_port if hybrid-llms started it. 0 = stopped or
 * not running. */
int engine_stop(const config *c, char *err, size_t errlen);
/* Stop an engine this process started when engine_keep_alive = 0. */
void engine_shutdown_owned(const config *c);
json *engine_status_json(const config *c);

#endif
