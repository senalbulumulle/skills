/* util.c - memory, string buffer, and logging helpers. */
#define _POSIX_C_SOURCE 200809L
#include "util.h"

#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int g_log_level = LOG_INFO;

static void oom(void)
{
    fputs("hybrid-llms: out of memory\n", stderr);
    abort();
}

void *xmalloc(size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p) oom();
    return p;
}

void *xcalloc(size_t n, size_t sz)
{
    void *p = calloc(n ? n : 1, sz ? sz : 1);
    if (!p) oom();
    return p;
}

void *xrealloc(void *p, size_t n)
{
    void *q = realloc(p, n ? n : 1);
    if (!q) oom();
    return q;
}

char *xstrdup(const char *s)
{
    return xstrndup(s ? s : "", strlen(s ? s : ""));
}

char *xstrndup(const char *s, size_t n)
{
    char *p = xmalloc(n + 1);
    if (n) memcpy(p, s, n);
    p[n] = '\0';
    return p;
}

void sb_init(sbuf *b)
{
    b->s = NULL;
    b->len = 0;
    b->cap = 0;
}

void sb_free(sbuf *b)
{
    free(b->s);
    sb_init(b);
}

void sb_reset(sbuf *b)
{
    b->len = 0;
    if (b->s) b->s[0] = '\0';
}

static void sb_grow(sbuf *b, size_t extra)
{
    size_t need = b->len + extra + 1;
    if (need <= b->cap) return;
    size_t cap = b->cap ? b->cap : 64;
    while (cap < need) {
        if (cap > ((size_t)-1) / 2) oom();
        cap *= 2;
    }
    b->s = xrealloc(b->s, cap);
    b->cap = cap;
}

void sb_append(sbuf *b, const char *s, size_t n)
{
    sb_grow(b, n);
    if (n) memcpy(b->s + b->len, s, n);
    b->len += n;
    b->s[b->len] = '\0';
}

void sb_puts(sbuf *b, const char *s)
{
    sb_append(b, s, strlen(s));
}

void sb_putc(sbuf *b, char c)
{
    sb_append(b, &c, 1);
}

void sb_printf(sbuf *b, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    va_list ap2;
    va_copy(ap2, ap);
    int n = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);
    if (n < 0) {
        va_end(ap2);
        return;
    }
    sb_grow(b, (size_t)n);
    vsnprintf(b->s + b->len, (size_t)n + 1, fmt, ap2);
    va_end(ap2);
    b->len += (size_t)n;
}

char *sb_take(sbuf *b)
{
    char *s = b->s ? b->s : xstrdup("");
    sb_init(b);
    return s;
}

char *str_trim(char *s)
{
    size_t n = strlen(s);
    size_t i = 0;
    while (i < n && isspace((unsigned char)s[i])) i++;
    while (n > i && isspace((unsigned char)s[n - 1])) n--;
    memmove(s, s + i, n - i);
    s[n - i] = '\0';
    return s;
}

void str_strip_ansi(char *s)
{
    char *r = s, *w = s;
    while (*r) {
        if (*r == 0x1b) {
            r++;
            if (*r == '[') {
                r++;
                while (*r && !(*r >= 0x40 && *r <= 0x7e)) r++;
                if (*r) r++;
            } else if (*r == ']') {
                /* OSC: terminated by BEL or ESC \ */
                r++;
                while (*r && *r != 0x07 && !(*r == 0x1b && r[1] == '\\')) r++;
                if (*r == 0x07) r++;
                else if (*r) r += 2;
            } else if (*r) {
                r++;
            }
            continue;
        }
        *w++ = *r++;
    }
    *w = '\0';
}

void str_strip_think(char *s)
{
    for (;;) {
        char *a = strstr(s, "<think>");
        if (!a) break;
        char *b = strstr(a, "</think>");
        if (!b) {
            /* Unterminated: drop everything from <think> on only if nothing precedes it. */
            break;
        }
        b += strlen("</think>");
        memmove(a, b, strlen(b) + 1);
    }
}

int str_ieq(const char *a, const char *b)
{
    if (!a || !b) return 0;
    while (*a && *b) {
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
        a++;
        b++;
    }
    return *a == *b;
}

size_t est_tokens(size_t chars)
{
    return (chars + 3) / 4;
}

static pthread_mutex_t log_mu = PTHREAD_MUTEX_INITIALIZER;

void log_msg(int level, const char *fmt, ...)
{
    if (level > g_log_level) return;
    static const char *names[] = {"error", "warn", "info", "debug"};
    char ts[32];
    time_t t = time(NULL);
    struct tm tm;
    localtime_r(&t, &tm);
    strftime(ts, sizeof ts, "%Y-%m-%d %H:%M:%S", &tm);
    pthread_mutex_lock(&log_mu);
    fprintf(stderr, "%s hybrid-llms[%s] ", ts, names[level]);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
    fflush(stderr);
    pthread_mutex_unlock(&log_mu);
}

long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
