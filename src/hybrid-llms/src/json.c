/* json.c - small JSON DOM: parse, build, serialize. */
#define _POSIX_C_SOURCE 200809L
#include "json.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define JSON_MAX_DEPTH 256

/* ---------- construction ---------- */

static json *jnew(jtype t)
{
    json *j = xcalloc(1, sizeof *j);
    j->t = t;
    return j;
}

json *json_new_null(void) { return jnew(J_NULL); }

json *json_new_bool(int b)
{
    json *j = jnew(J_BOOL);
    j->b = b ? 1 : 0;
    return j;
}

json *json_new_num(double n)
{
    json *j = jnew(J_NUM);
    j->n = n;
    return j;
}

json *json_new_strn(const char *s, size_t n)
{
    json *j = jnew(J_STR);
    j->s = xstrndup(s ? s : "", s ? n : 0);
    j->slen = s ? n : 0;
    return j;
}

json *json_new_str(const char *s)
{
    return json_new_strn(s ? s : "", s ? strlen(s) : 0);
}

json *json_new_arr(void) { return jnew(J_ARR); }
json *json_new_obj(void) { return jnew(J_OBJ); }

static void jgrow(json *j)
{
    if (j->len < j->cap) return;
    size_t cap = j->cap ? j->cap * 2 : 8;
    j->items = xrealloc(j->items, cap * sizeof *j->items);
    if (j->t == J_OBJ) j->keys = xrealloc(j->keys, cap * sizeof *j->keys);
    j->cap = cap;
}

void json_push(json *arr, json *val)
{
    if (!arr || arr->t != J_ARR) {
        json_free(val);
        return;
    }
    jgrow(arr);
    arr->items[arr->len++] = val;
}

void json_set(json *obj, const char *key, json *val)
{
    if (!obj || obj->t != J_OBJ) {
        json_free(val);
        return;
    }
    for (size_t i = 0; i < obj->len; i++) {
        if (strcmp(obj->keys[i], key) == 0) {
            json_free(obj->items[i]);
            obj->items[i] = val;
            return;
        }
    }
    jgrow(obj);
    obj->keys[obj->len] = xstrdup(key);
    obj->items[obj->len] = val;
    obj->len++;
}

void json_set_str(json *obj, const char *key, const char *s) { json_set(obj, key, json_new_str(s)); }
void json_set_num(json *obj, const char *key, double n) { json_set(obj, key, json_new_num(n)); }
void json_set_bool(json *obj, const char *key, int b) { json_set(obj, key, json_new_bool(b)); }

void json_free(json *j)
{
    if (!j) return;
    free(j->s);
    for (size_t i = 0; i < j->len; i++) {
        json_free(j->items[i]);
        if (j->keys) free(j->keys[i]);
    }
    free(j->items);
    free(j->keys);
    free(j);
}

json *json_clone(const json *j)
{
    if (!j) return NULL;
    json *c = jnew(j->t);
    c->b = j->b;
    c->n = j->n;
    if (j->t == J_STR) {
        c->s = xstrndup(j->s, j->slen);
        c->slen = j->slen;
    }
    for (size_t i = 0; i < j->len; i++) {
        if (j->t == J_OBJ) json_set(c, j->keys[i], json_clone(j->items[i]));
        else json_push(c, json_clone(j->items[i]));
    }
    return c;
}

/* ---------- access ---------- */

json *json_get(const json *obj, const char *key)
{
    if (!obj || obj->t != J_OBJ) return NULL;
    for (size_t i = 0; i < obj->len; i++)
        if (strcmp(obj->keys[i], key) == 0) return obj->items[i];
    return NULL;
}

const char *json_get_str(const json *obj, const char *key)
{
    json *v = json_get(obj, key);
    return (v && v->t == J_STR) ? v->s : NULL;
}

double json_get_num(const json *obj, const char *key, double dflt)
{
    json *v = json_get(obj, key);
    return (v && v->t == J_NUM) ? v->n : dflt;
}

int json_get_bool(const json *obj, const char *key, int dflt)
{
    json *v = json_get(obj, key);
    return (v && v->t == J_BOOL) ? v->b : dflt;
}

/* ---------- parsing ---------- */

typedef struct {
    const char *p;
    const char *end;
    const char *start;
    char *err;
    size_t errlen;
    int failed;
} parser;

static void perr(parser *ps, const char *msg)
{
    if (ps->failed) return;
    ps->failed = 1;
    if (ps->err && ps->errlen)
        snprintf(ps->err, ps->errlen, "%s at offset %zu", msg, (size_t)(ps->p - ps->start));
}

static void skip_ws(parser *ps)
{
    while (ps->p < ps->end && (*ps->p == ' ' || *ps->p == '\t' || *ps->p == '\n' || *ps->p == '\r'))
        ps->p++;
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int read_hex4(parser *ps, unsigned *out)
{
    if (ps->end - ps->p < 4) return 0;
    unsigned v = 0;
    for (int i = 0; i < 4; i++) {
        int h = hexval(ps->p[i]);
        if (h < 0) return 0;
        v = (v << 4) | (unsigned)h;
    }
    ps->p += 4;
    *out = v;
    return 1;
}

static void put_utf8(sbuf *b, unsigned cp)
{
    char tmp[4];
    if (cp < 0x80) {
        tmp[0] = (char)cp;
        sb_append(b, tmp, 1);
    } else if (cp < 0x800) {
        tmp[0] = (char)(0xC0 | (cp >> 6));
        tmp[1] = (char)(0x80 | (cp & 0x3F));
        sb_append(b, tmp, 2);
    } else if (cp < 0x10000) {
        tmp[0] = (char)(0xE0 | (cp >> 12));
        tmp[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        tmp[2] = (char)(0x80 | (cp & 0x3F));
        sb_append(b, tmp, 3);
    } else {
        tmp[0] = (char)(0xF0 | (cp >> 18));
        tmp[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
        tmp[2] = (char)(0x80 | ((cp >> 6) & 0x3F));
        tmp[3] = (char)(0x80 | (cp & 0x3F));
        sb_append(b, tmp, 4);
    }
}

static int parse_string_raw(parser *ps, sbuf *out)
{
    /* ps->p points at opening quote */
    ps->p++;
    while (ps->p < ps->end) {
        unsigned char c = (unsigned char)*ps->p;
        if (c == '"') {
            ps->p++;
            return 1;
        }
        if (c < 0x20) {
            perr(ps, "control character in string");
            return 0;
        }
        if (c == '\\') {
            ps->p++;
            if (ps->p >= ps->end) break;
            char e = *ps->p++;
            switch (e) {
            case '"': sb_putc(out, '"'); break;
            case '\\': sb_putc(out, '\\'); break;
            case '/': sb_putc(out, '/'); break;
            case 'b': sb_putc(out, '\b'); break;
            case 'f': sb_putc(out, '\f'); break;
            case 'n': sb_putc(out, '\n'); break;
            case 'r': sb_putc(out, '\r'); break;
            case 't': sb_putc(out, '\t'); break;
            case 'u': {
                unsigned cp;
                if (!read_hex4(ps, &cp)) {
                    perr(ps, "bad \\u escape");
                    return 0;
                }
                if (cp >= 0xD800 && cp <= 0xDBFF) {
                    unsigned lo;
                    if (ps->end - ps->p >= 6 && ps->p[0] == '\\' && ps->p[1] == 'u') {
                        const char *save = ps->p;
                        ps->p += 2;
                        if (read_hex4(ps, &lo) && lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        } else {
                            ps->p = save;
                            cp = 0xFFFD;
                        }
                    } else {
                        cp = 0xFFFD;
                    }
                } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                    cp = 0xFFFD;
                }
                put_utf8(out, cp);
                break;
            }
            default:
                perr(ps, "bad escape");
                return 0;
            }
            continue;
        }
        /* copy run of plain bytes */
        const char *run = ps->p;
        while (ps->p < ps->end && *ps->p != '"' && *ps->p != '\\' && (unsigned char)*ps->p >= 0x20) ps->p++;
        sb_append(out, run, (size_t)(ps->p - run));
    }
    perr(ps, "unterminated string");
    return 0;
}

static json *parse_value(parser *ps, int depth);

static json *parse_number(parser *ps)
{
    const char *s = ps->p;
    if (ps->p < ps->end && *ps->p == '-') ps->p++;
    if (ps->p >= ps->end) goto bad;
    if (*ps->p == '0') {
        ps->p++;
    } else if (*ps->p >= '1' && *ps->p <= '9') {
        while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++;
    } else {
        goto bad;
    }
    if (ps->p < ps->end && *ps->p == '.') {
        ps->p++;
        if (ps->p >= ps->end || !(*ps->p >= '0' && *ps->p <= '9')) goto bad;
        while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++;
    }
    if (ps->p < ps->end && (*ps->p == 'e' || *ps->p == 'E')) {
        ps->p++;
        if (ps->p < ps->end && (*ps->p == '+' || *ps->p == '-')) ps->p++;
        if (ps->p >= ps->end || !(*ps->p >= '0' && *ps->p <= '9')) goto bad;
        while (ps->p < ps->end && *ps->p >= '0' && *ps->p <= '9') ps->p++;
    }
    {
        char tmp[64];
        size_t n = (size_t)(ps->p - s);
        char *heap = NULL;
        char *buf = tmp;
        if (n >= sizeof tmp) buf = heap = xmalloc(n + 1);
        memcpy(buf, s, n);
        buf[n] = '\0';
        double v = strtod(buf, NULL);
        free(heap);
        return json_new_num(v);
    }
bad:
    perr(ps, "bad number");
    return NULL;
}

static int match_lit(parser *ps, const char *lit)
{
    size_t n = strlen(lit);
    if ((size_t)(ps->end - ps->p) < n || memcmp(ps->p, lit, n) != 0) return 0;
    ps->p += n;
    return 1;
}

static json *parse_value(parser *ps, int depth)
{
    if (depth > JSON_MAX_DEPTH) {
        perr(ps, "nesting too deep");
        return NULL;
    }
    skip_ws(ps);
    if (ps->p >= ps->end) {
        perr(ps, "unexpected end of input");
        return NULL;
    }
    char c = *ps->p;
    if (c == '{') {
        ps->p++;
        json *o = json_new_obj();
        skip_ws(ps);
        if (ps->p < ps->end && *ps->p == '}') {
            ps->p++;
            return o;
        }
        for (;;) {
            skip_ws(ps);
            if (ps->p >= ps->end || *ps->p != '"') {
                perr(ps, "expected object key");
                json_free(o);
                return NULL;
            }
            sbuf k;
            sb_init(&k);
            if (!parse_string_raw(ps, &k)) {
                sb_free(&k);
                json_free(o);
                return NULL;
            }
            skip_ws(ps);
            if (ps->p >= ps->end || *ps->p != ':') {
                perr(ps, "expected ':'");
                sb_free(&k);
                json_free(o);
                return NULL;
            }
            ps->p++;
            json *v = parse_value(ps, depth + 1);
            if (!v) {
                sb_free(&k);
                json_free(o);
                return NULL;
            }
            char *key = sb_take(&k);
            json_set(o, key, v);
            free(key);
            skip_ws(ps);
            if (ps->p < ps->end && *ps->p == ',') {
                ps->p++;
                continue;
            }
            if (ps->p < ps->end && *ps->p == '}') {
                ps->p++;
                return o;
            }
            perr(ps, "expected ',' or '}'");
            json_free(o);
            return NULL;
        }
    }
    if (c == '[') {
        ps->p++;
        json *a = json_new_arr();
        skip_ws(ps);
        if (ps->p < ps->end && *ps->p == ']') {
            ps->p++;
            return a;
        }
        for (;;) {
            json *v = parse_value(ps, depth + 1);
            if (!v) {
                json_free(a);
                return NULL;
            }
            json_push(a, v);
            skip_ws(ps);
            if (ps->p < ps->end && *ps->p == ',') {
                ps->p++;
                continue;
            }
            if (ps->p < ps->end && *ps->p == ']') {
                ps->p++;
                return a;
            }
            perr(ps, "expected ',' or ']'");
            json_free(a);
            return NULL;
        }
    }
    if (c == '"') {
        sbuf s;
        sb_init(&s);
        if (!parse_string_raw(ps, &s)) {
            sb_free(&s);
            return NULL;
        }
        json *j = jnew(J_STR);
        j->slen = s.len;
        j->s = sb_take(&s);
        return j;
    }
    if (c == '-' || (c >= '0' && c <= '9')) return parse_number(ps);
    if (match_lit(ps, "true")) return json_new_bool(1);
    if (match_lit(ps, "false")) return json_new_bool(0);
    if (match_lit(ps, "null")) return json_new_null();
    perr(ps, "unexpected character");
    return NULL;
}

json *json_parse(const char *src, size_t n, char *err, size_t errlen)
{
    if (err && errlen) err[0] = '\0';
    parser ps = {src, src + n, src, err, errlen, 0};
    json *v = parse_value(&ps, 0);
    if (!v) {
        if (!ps.failed) perr(&ps, "parse error");
        return NULL;
    }
    skip_ws(&ps);
    if (ps.p != ps.end) {
        perr(&ps, "trailing data");
        json_free(v);
        return NULL;
    }
    return v;
}

/* ---------- serialization ---------- */

/* Length of a valid UTF-8 sequence at s (max n bytes), or 0 if invalid. */
static size_t utf8_seq(const unsigned char *s, size_t n)
{
    unsigned char c = s[0];
    size_t len;
    unsigned cp;
    if (c < 0x80) return 1;
    if (c >= 0xC2 && c <= 0xDF) {
        len = 2;
        cp = c & 0x1F;
    } else if (c >= 0xE0 && c <= 0xEF) {
        len = 3;
        cp = c & 0x0F;
    } else if (c >= 0xF0 && c <= 0xF4) {
        len = 4;
        cp = c & 0x07;
    } else {
        return 0;
    }
    if (n < len) return 0;
    for (size_t i = 1; i < len; i++) {
        if ((s[i] & 0xC0) != 0x80) return 0;
        cp = (cp << 6) | (s[i] & 0x3F);
    }
    if ((len == 3 && cp < 0x800) || (len == 4 && (cp < 0x10000 || cp > 0x10FFFF))) return 0;
    if (cp >= 0xD800 && cp <= 0xDFFF) return 0;
    return len;
}

void json_escape_into(sbuf *b, const char *str, size_t n)
{
    const unsigned char *s = (const unsigned char *)str;
    sb_putc(b, '"');
    size_t i = 0;
    while (i < n) {
        unsigned char c = s[i];
        switch (c) {
        case '"': sb_puts(b, "\\\""); i++; continue;
        case '\\': sb_puts(b, "\\\\"); i++; continue;
        case '\n': sb_puts(b, "\\n"); i++; continue;
        case '\r': sb_puts(b, "\\r"); i++; continue;
        case '\t': sb_puts(b, "\\t"); i++; continue;
        case '\b': sb_puts(b, "\\b"); i++; continue;
        case '\f': sb_puts(b, "\\f"); i++; continue;
        default: break;
        }
        if (c < 0x20 || c == 0x7f) {
            sb_printf(b, "\\u%04x", c);
            i++;
            continue;
        }
        size_t L = utf8_seq(s + i, n - i);
        if (L == 0) {
            sb_puts(b, "\\ufffd");
            i++;
            continue;
        }
        sb_append(b, (const char *)s + i, L);
        i += L;
    }
    sb_putc(b, '"');
}

void json_dump_into(sbuf *b, const json *j)
{
    if (!j) {
        sb_puts(b, "null");
        return;
    }
    switch (j->t) {
    case J_NULL: sb_puts(b, "null"); break;
    case J_BOOL: sb_puts(b, j->b ? "true" : "false"); break;
    case J_NUM:
        if (!isfinite(j->n)) sb_puts(b, "null");
        else if (j->n == floor(j->n) && fabs(j->n) < 1e15) sb_printf(b, "%.0f", j->n);
        else sb_printf(b, "%.17g", j->n);
        break;
    case J_STR: json_escape_into(b, j->s, j->slen); break;
    case J_ARR:
        sb_putc(b, '[');
        for (size_t i = 0; i < j->len; i++) {
            if (i) sb_putc(b, ',');
            json_dump_into(b, j->items[i]);
        }
        sb_putc(b, ']');
        break;
    case J_OBJ:
        sb_putc(b, '{');
        for (size_t i = 0; i < j->len; i++) {
            if (i) sb_putc(b, ',');
            json_escape_into(b, j->keys[i], strlen(j->keys[i]));
            sb_putc(b, ':');
            json_dump_into(b, j->items[i]);
        }
        sb_putc(b, '}');
        break;
    }
}

char *json_dump(const json *j)
{
    sbuf b;
    sb_init(&b);
    json_dump_into(&b, j);
    return sb_take(&b);
}
