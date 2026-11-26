/* util.h - memory, string buffer, and logging helpers. */
#ifndef HYBRID_UTIL_H
#define HYBRID_UTIL_H

#include <stdarg.h>
#include <stddef.h>

#define HYBRID_VERSION "1.0.0"

typedef struct {
    char *s;
    size_t len;
    size_t cap;
} sbuf;

void *xmalloc(size_t n);
void *xcalloc(size_t n, size_t sz);
void *xrealloc(void *p, size_t n);
char *xstrdup(const char *s);
char *xstrndup(const char *s, size_t n);

void sb_init(sbuf *b);
void sb_free(sbuf *b);
void sb_reset(sbuf *b);
void sb_append(sbuf *b, const char *s, size_t n);
void sb_puts(sbuf *b, const char *s);
void sb_putc(sbuf *b, char c);
void sb_printf(sbuf *b, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
/* Returns the heap string and leaves the buffer empty. Never NULL. */
char *sb_take(sbuf *b);

/* Trim ASCII whitespace in place; returns s. */
char *str_trim(char *s);
/* Remove ANSI escape sequences in place. */
void str_strip_ansi(char *s);
/* Remove <think>...</think> blocks (reasoning models) in place. */
void str_strip_think(char *s);
int str_ieq(const char *a, const char *b);
size_t est_tokens(size_t chars);

enum { LOG_ERROR = 0, LOG_WARN = 1, LOG_INFO = 2, LOG_DEBUG = 3 };
extern int g_log_level;
void log_msg(int level, const char *fmt, ...) __attribute__((format(printf, 2, 3)));

/* Monotonic milliseconds. */
long long now_ms(void);

#endif
