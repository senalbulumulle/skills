/* local.h - talk to the local language model. */
#ifndef HYBRID_LOCAL_H
#define HYBRID_LOCAL_H

#include <stddef.h>

#include "config.h"
#include "json.h"
#include "util.h"

/* messages: JSON array of {"role": "...", "content": "..."}.
 * model: override (NULL = config). Writes the reply text and the model actually
 * used (model_used may be NULL). */
int local_chat(const config *c, const json *messages, const char *model, sbuf *out, char *model_used, size_t mucap,
               char *err, size_t errlen);
int local_simple(const config *c, const char *system, const char *prompt, const char *model, sbuf *out,
                 char *model_used, size_t mucap, char *err, size_t errlen);
/* Status object: backend, reachable, models. */
json *local_status_json(const config *c);
/* JSON array of available local model names. */
json *local_models_json(const config *c, char *err, size_t errlen);

#endif
