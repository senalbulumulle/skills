/* json.h - small JSON DOM: parse, build, serialize. */
#ifndef HYBRID_JSON_H
#define HYBRID_JSON_H

#include <stddef.h>

#include "util.h"

typedef enum { J_NULL, J_BOOL, J_NUM, J_STR, J_ARR, J_OBJ } jtype;

typedef struct json json;
struct json {
    jtype t;
    int b;
    double n;
    char *s;      /* J_STR: NUL-terminated (may contain embedded NUL; see slen) */
    size_t slen;
    json **items; /* J_ARR / J_OBJ values */
    char **keys;  /* J_OBJ keys */
    size_t len;
    size_t cap;
};

json *json_parse(const char *src, size_t n, char *err, size_t errlen);
void json_free(json *j);
json *json_clone(const json *j);

json *json_new_null(void);
json *json_new_bool(int b);
json *json_new_num(double n);
json *json_new_str(const char *s);
json *json_new_strn(const char *s, size_t n);
json *json_new_arr(void);
json *json_new_obj(void);

/* Object set: takes ownership of val, replaces an existing key. */
void json_set(json *obj, const char *key, json *val);
void json_set_str(json *obj, const char *key, const char *s);
void json_set_num(json *obj, const char *key, double n);
void json_set_bool(json *obj, const char *key, int b);
/* Array push: takes ownership. */
void json_push(json *arr, json *val);

json *json_get(const json *obj, const char *key);
/* String value of obj[key], or NULL if missing / not a string. */
const char *json_get_str(const json *obj, const char *key);
/* Number value of obj[key], or dflt. */
double json_get_num(const json *obj, const char *key, double dflt);
int json_get_bool(const json *obj, const char *key, int dflt);

/* Serialize compactly. Invalid UTF-8 in strings becomes U+FFFD. */
char *json_dump(const json *j);
void json_dump_into(sbuf *b, const json *j);
void json_escape_into(sbuf *b, const char *s, size_t n);

#endif
