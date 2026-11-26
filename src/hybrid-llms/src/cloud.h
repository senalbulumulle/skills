/* cloud.h - run cloud model CLIs (claude, codex, gemini) headlessly. */
#ifndef HYBRID_CLOUD_H
#define HYBRID_CLOUD_H

#include <stddef.h>

#include "config.h"
#include "json.h"
#include "util.h"

typedef enum { CLOUD_NONE = 0, CLOUD_HOST, CLOUD_CLAUDE, CLOUD_CODEX, CLOUD_GEMINI } cloud_id;

/* "host", "claude", "codex", "gemini", "none". Returns 0 on success. */
int cloud_parse(const char *s, cloud_id *out);
const char *cloud_name(cloud_id id);
/* Current nesting depth from HYBRID_LLMS_DEPTH. */
int cloud_depth(void);

/* Ask a cloud CLI. prompt goes to stdin unless the command uses {prompt}.
 * CLOUD_HOST / CLOUD_NONE are not runnable here and return -1. */
int cloud_ask(const config *c, cloud_id id, const char *prompt, sbuf *out, char *err, size_t errlen);
json *cloud_status_json(const config *c);

#endif
