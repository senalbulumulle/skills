/* local.c - talk to the local language model. */
#define _POSIX_C_SOURCE 200809L
#include "local.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "engine.h"
#include "http.h"

static int is_managed(const config *c) { return strcmp(c->local_api, "managed") == 0; }
static int is_ollama(const config *c) { return strcmp(c->local_api, "ollama") == 0; }

/* Join base + path, avoiding a doubled "/v1" for OpenAI-style base URLs. */
static void join_url(const char *base, const char *path, char *out, size_t cap)
{
    size_t bl = strlen(base);
    if (strncmp(path, "/v1/", 4) == 0 && bl >= 3 && strcmp(base + bl - 3, "/v1") == 0) path += 3;
    snprintf(out, cap, "%s%s", base, path);
}

static int post_json(const config *c, const char *url, const json *body, json **out, char *err, size_t errlen)
{
    char *payload = json_dump(body);
    char hdr[600];
    hdr[0] = '\0';
    if (!is_managed(c) && c->local_api_key[0]) snprintf(hdr, sizeof hdr, "Authorization: Bearer %s\r\n", c->local_api_key);
    int status = 0;
    sbuf resp;
    sb_init(&resp);
    int rc = http_request("POST", url, hdr[0] ? hdr : NULL, payload, strlen(payload), c->local_timeout, &status, &resp,
                          err, errlen);
    free(payload);
    if (rc != 0) {
        sb_free(&resp);
        return -1;
    }
    char perr[128];
    json *j = resp.s ? json_parse(resp.s, resp.len, perr, sizeof perr) : NULL;
    if (status != 200) {
        const char *msg = NULL;
        json *e = j ? json_get(j, "error") : NULL;
        if (e && e->t == J_STR) msg = e->s;
        else if (e && e->t == J_OBJ) msg = json_get_str(e, "message");
        snprintf(err, errlen, "local model HTTP %d: %.300s", status, msg ? msg : (resp.s ? resp.s : ""));
        json_free(j);
        sb_free(&resp);
        return -1;
    }
    if (!j) {
        snprintf(err, errlen, "local model returned invalid JSON: %s", perr);
        sb_free(&resp);
        return -1;
    }
    sb_free(&resp);
    *out = j;
    return 0;
}

int local_chat(const config *c, const json *messages, const char *model, sbuf *out, char *model_used, size_t mucap,
               char *err, size_t errlen)
{
    char url[1200];
    char model_field[4200];
    model_info mi = {0};
    const char *want = (model && *model) ? model : c->local_model;

    if (is_managed(c)) {
        if (models_resolve(c, want, &mi, err, errlen) != 0) return -1;
        char base[128];
        if (engine_ensure(c, &mi, base, sizeof base, model_field, sizeof model_field, err, errlen) != 0) {
            model_info_free(&mi);
            return -1;
        }
        join_url(base, "/v1/chat/completions", url, sizeof url);
        if (model_used) snprintf(model_used, mucap, "%s", mi.name);
        model_info_free(&mi);
    } else {
        if (!want || !*want) {
            snprintf(err, errlen, "local_model is not set (required for local_api = %s)", c->local_api);
            return -1;
        }
        snprintf(model_field, sizeof model_field, "%s", want);
        join_url(c->local_url, is_ollama(c) ? "/api/chat" : "/v1/chat/completions", url, sizeof url);
        if (model_used) snprintf(model_used, mucap, "%s", want);
    }

    json *body = json_new_obj();
    json_set_str(body, "model", model_field);
    json_set(body, "messages", json_clone(messages));
    json_set_bool(body, "stream", 0);
    if (is_ollama(c)) {
        json *opts = json_new_obj();
        if (c->local_temperature >= 0) json_set_num(opts, "temperature", c->local_temperature);
        if (c->local_num_ctx > 0) json_set_num(opts, "num_ctx", c->local_num_ctx);
        json_set(body, "options", opts);
    } else if (c->local_temperature >= 0) {
        json_set_num(body, "temperature", c->local_temperature);
    }

    json *resp = NULL;
    int rc = post_json(c, url, body, &resp, err, errlen);
    json_free(body);
    if (rc != 0) return -1;

    const char *text = NULL;
    if (is_ollama(c)) {
        text = json_get_str(json_get(resp, "message"), "content");
    } else {
        json *choices = json_get(resp, "choices");
        if (choices && choices->t == J_ARR && choices->len > 0)
            text = json_get_str(json_get(choices->items[0], "message"), "content");
    }
    if (!text) {
        snprintf(err, errlen, "local model response has no message content");
        json_free(resp);
        return -1;
    }
    char *t = xstrdup(text);
    json_free(resp);
    if (c->strip_think) str_strip_think(t);
    str_trim(t);
    sb_puts(out, t);
    free(t);
    return 0;
}

int local_simple(const config *c, const char *system, const char *prompt, const char *model, sbuf *out,
                 char *model_used, size_t mucap, char *err, size_t errlen)
{
    json *msgs = json_new_arr();
    if (system && *system) {
        json *m = json_new_obj();
        json_set_str(m, "role", "system");
        json_set_str(m, "content", system);
        json_push(msgs, m);
    }
    json *m = json_new_obj();
    json_set_str(m, "role", "user");
    json_set_str(m, "content", prompt);
    json_push(msgs, m);
    int rc = local_chat(c, msgs, model, out, model_used, mucap, err, errlen);
    json_free(msgs);
    return rc;
}

json *local_models_json(const config *c, char *err, size_t errlen)
{
    json *arr = json_new_arr();
    if (is_managed(c)) {
        model_list l;
        if (models_scan(c, &l, err, errlen) != 0) {
            json_free(arr);
            return NULL;
        }
        for (size_t i = 0; i < l.n; i++) {
            json *m = json_new_obj();
            json_set_str(m, "name", l.v[i].name);
            json_set_str(m, "kind", model_kind_name(l.v[i].kind));
            json_set_num(m, "size_gb", (double)(l.v[i].size / 10000000) / 100.0);
            json_push(arr, m);
        }
        models_free(&l);
        return arr;
    }
    char url[1200];
    join_url(c->local_url, is_ollama(c) ? "/api/tags" : "/v1/models", url, sizeof url);
    char hdr[600];
    hdr[0] = '\0';
    if (c->local_api_key[0]) snprintf(hdr, sizeof hdr, "Authorization: Bearer %s\r\n", c->local_api_key);
    int status = 0;
    sbuf resp;
    sb_init(&resp);
    if (http_request("GET", url, hdr[0] ? hdr : NULL, NULL, 0, 10, &status, &resp, err, errlen) != 0 ||
        status != 200) {
        if (status) snprintf(err, errlen, "GET %s returned HTTP %d", url, status);
        sb_free(&resp);
        json_free(arr);
        return NULL;
    }
    json *j = resp.s ? json_parse(resp.s, resp.len, NULL, 0) : NULL;
    sb_free(&resp);
    json *list = j ? json_get(j, is_ollama(c) ? "models" : "data") : NULL;
    if (list && list->t == J_ARR) {
        for (size_t i = 0; i < list->len; i++) {
            const char *n = json_get_str(list->items[i], is_ollama(c) ? "name" : "id");
            if (!n) continue;
            json *m = json_new_obj();
            json_set_str(m, "name", n);
            json_push(arr, m);
        }
    }
    json_free(j);
    return arr;
}

json *local_status_json(const config *c)
{
    json *o = json_new_obj();
    json_set_str(o, "backend", c->local_api);
    if (is_managed(c)) {
        char dir[1024];
        expand_home(c->models_dir, dir, sizeof dir);
        json_set_str(o, "models_dir", dir);
        json_set(o, "engine", engine_status_json(c));
    } else {
        json_set_str(o, "url", c->local_url);
    }
    json_set_str(o, "configured_model", c->local_model[0] ? c->local_model : "(first model found)");
    char err[512] = "";
    json *models = local_models_json(c, err, sizeof err);
    json_set_bool(o, "reachable", models != NULL);
    if (models) json_set(o, "models", models);
    else json_set_str(o, "error", err);
    return o;
}
