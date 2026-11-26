/* hybrid.h - strategies that combine the local model with a cloud model.
 *
 *  local         local model only
 *  cloud         cloud model only
 *  cascade       local answers with a confidence score; escalate to cloud when low
 *  draft-review  local drafts, cloud reviews and returns the final answer
 *  plan-execute  cloud writes a short plan, local carries it out
 *  compress      local condenses long context, cloud answers from the condensed text
 *  auto          compress when the input is long, otherwise cascade
 *
 * cloud = "host" means the CLI that called us (Claude Code, Codex, Gemini) is the
 * cloud model: cloud steps are handed back to it in the result instead of
 * starting another CLI. */
#ifndef HYBRID_HYBRID_H
#define HYBRID_HYBRID_H

#include "cloud.h"
#include "config.h"
#include "json.h"

typedef enum { S_AUTO, S_LOCAL, S_CLOUD, S_CASCADE, S_DRAFT_REVIEW, S_PLAN_EXECUTE, S_COMPRESS } strategy;

int strategy_parse(const char *s, strategy *out);
const char *strategy_name(strategy s);

typedef struct {
    strategy strat;
    cloud_id cloud;
    const char *prompt;      /* required */
    const char *system;      /* optional */
    const char *context;     /* optional: long material (files, logs, docs) */
    const char *local_model; /* optional override */
    int threshold;           /* cascade threshold; < 0 = config */
} hybrid_req;

typedef struct {
    char *answer;
    char *note;         /* guidance for the caller (host mode, fallbacks); may be NULL */
    strategy used;      /* resolved strategy (auto -> cascade/compress) */
    int confidence;     /* local self-score, -1 if none */
    int escalated;      /* cascade went to the cloud */
    int needs_host;     /* host should review / finish */
    size_t local_chars;  /* chars sent to + received from the local model */
    size_t cloud_chars;  /* chars sent to + received from cloud CLIs */
    json *trace;        /* array of step objects */
} hybrid_res;

int hybrid_run(const config *c, const hybrid_req *req, hybrid_res *res, char *err, size_t errlen);
void hybrid_res_free(hybrid_res *res);
json *hybrid_res_json(const hybrid_res *res, const hybrid_req *req);
/* One-line summary: strategy, models, escalation, token estimates. */
char *hybrid_res_summary(const hybrid_res *res, const hybrid_req *req);

#endif
