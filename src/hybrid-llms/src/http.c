/* http.c - minimal HTTP/1.1 client (plain http) and server-side helpers. */
#define _POSIX_C_SOURCE 200809L
#include "http.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

int write_all(int fd, const char *buf, size_t n)
{
    while (n > 0) {
        ssize_t w = write(fd, buf, n);
        if (w < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        buf += w;
        n -= (size_t)w;
    }
    return 0;
}

/* Wait until fd is readable or the deadline passes. 1 = ready, 0 = timeout, -1 = error. */
static int wait_readable(int fd, long long deadline)
{
    for (;;) {
        long long left = deadline - now_ms();
        if (left <= 0) return 0;
        struct pollfd p = {fd, POLLIN, 0};
        int r = poll(&p, 1, left > 1000000 ? 1000000 : (int)left);
        if (r < 0 && errno == EINTR) continue;
        if (r < 0) return -1;
        return r > 0 ? 1 : 0;
    }
}

static int parse_url(const char *url, char *host, size_t hcap, char *port, size_t pcap, const char **path)
{
    if (strncmp(url, "http://", 7) != 0) return -1;
    const char *p = url + 7;
    const char *hend;
    const char *after;
    if (*p == '[') {
        hend = strchr(p, ']');
        if (!hend) return -1;
        if ((size_t)(hend - p - 1) >= hcap) return -1;
        memcpy(host, p + 1, (size_t)(hend - p - 1));
        host[hend - p - 1] = '\0';
        after = hend + 1;
    } else {
        hend = p;
        while (*hend && *hend != ':' && *hend != '/') hend++;
        if (hend == p || (size_t)(hend - p) >= hcap) return -1;
        memcpy(host, p, (size_t)(hend - p));
        host[hend - p] = '\0';
        after = hend;
    }
    if (*after == ':') {
        const char *ps = after + 1;
        const char *pe = ps;
        while (*pe && *pe != '/') pe++;
        if (pe == ps || (size_t)(pe - ps) >= pcap) return -1;
        memcpy(port, ps, (size_t)(pe - ps));
        port[pe - ps] = '\0';
        after = pe;
    } else {
        snprintf(port, pcap, "80");
    }
    *path = *after ? after : "/";
    return 0;
}

static int connect_to(const char *host, const char *port, long long deadline, char *err, size_t errlen)
{
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    int gai = getaddrinfo(host, port, &hints, &res);
    if (gai != 0) {
        snprintf(err, errlen, "resolve %s: %s", host, gai_strerror(gai));
        return -1;
    }
    int fd = -1;
    int last_errno = 0;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0) {
            last_errno = errno;
            continue;
        }
#ifdef SO_NOSIGPIPE
        int one = 1;
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#endif
        int fl = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, fl | O_NONBLOCK);
        int r = connect(fd, ai->ai_addr, ai->ai_addrlen);
        if (r < 0 && errno == EINPROGRESS) {
            long long left = deadline - now_ms();
            struct pollfd p = {fd, POLLOUT, 0};
            r = left > 0 ? poll(&p, 1, (int)(left > 1000000 ? 1000000 : left)) : 0;
            if (r > 0) {
                int soerr = 0;
                socklen_t sl = sizeof soerr;
                getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &sl);
                if (soerr == 0) r = 0;
                else {
                    errno = soerr;
                    r = -1;
                }
            } else {
                if (r == 0) errno = ETIMEDOUT;
                r = -1;
            }
        }
        if (r == 0) {
            fcntl(fd, F_SETFL, fl & ~O_NONBLOCK);
            break;
        }
        last_errno = errno;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) snprintf(err, errlen, "connect %s:%s: %s", host, port, strerror(last_errno ? last_errno : ECONNREFUSED));
    return fd;
}

/* Decode chunked body in place. Returns new length or (size_t)-1 on error. */
static size_t dechunk(char *data, size_t n)
{
    size_t r = 0, w = 0;
    for (;;) {
        size_t ls = r;
        while (r + 1 < n && !(data[r] == '\r' && data[r + 1] == '\n')) r++;
        if (r + 1 >= n) return (size_t)-1;
        char tmp[32];
        size_t L = r - ls;
        if (L == 0 || L >= sizeof tmp) return (size_t)-1;
        memcpy(tmp, data + ls, L);
        tmp[L] = '\0';
        char *semi = strchr(tmp, ';');
        if (semi) *semi = '\0';
        char *end;
        unsigned long sz = strtoul(tmp, &end, 16);
        if (end == tmp) return (size_t)-1;
        r += 2;
        if (sz == 0) break;
        if (r + sz > n) return (size_t)-1;
        memmove(data + w, data + r, sz);
        w += sz;
        r += sz;
        if (r + 2 > n || data[r] != '\r' || data[r + 1] != '\n') return (size_t)-1;
        r += 2;
    }
    data[w] = '\0';
    return w;
}

static const char *find_header(const char *hdrs, const char *hend, const char *name)
{
    size_t nl = strlen(name);
    const char *p = hdrs;
    while (p < hend) {
        const char *eol = strstr(p, "\r\n");
        if (!eol || eol > hend) eol = hend;
        if ((size_t)(eol - p) > nl && strncasecmp(p, name, nl) == 0 && p[nl] == ':') {
            p += nl + 1;
            while (*p == ' ' || *p == '\t') p++;
            return p;
        }
        p = eol + 2;
    }
    return NULL;
}

int http_request(const char *method, const char *url, const char *extra_headers, const char *body, size_t blen,
                 int timeout_s, int *status, sbuf *resp, char *err, size_t errlen)
{
    char host[256], port[16];
    const char *path;
    *status = 0;
    sb_reset(resp);
    if (parse_url(url, host, sizeof host, port, sizeof port, &path) != 0) {
        snprintf(err, errlen, "unsupported URL '%s' (only http://host[:port]/path)", url);
        return -1;
    }
    long long deadline = now_ms() + (long long)timeout_s * 1000;
    int fd = connect_to(host, port, deadline, err, errlen);
    if (fd < 0) return -1;

    sbuf req;
    sb_init(&req);
    int v6 = strchr(host, ':') != NULL;
    sb_printf(&req, "%s %s HTTP/1.1\r\nHost: %s%s%s:%s\r\nUser-Agent: hybrid-llms/%s\r\nAccept: application/json\r\n"
                    "Connection: close\r\n",
              method, path, v6 ? "[" : "", host, v6 ? "]" : "", port, HYBRID_VERSION);
    if (body) sb_printf(&req, "Content-Type: application/json\r\nContent-Length: %zu\r\n", blen);
    if (extra_headers) sb_puts(&req, extra_headers);
    sb_puts(&req, "\r\n");
    int rc = write_all(fd, req.s, req.len);
    if (rc == 0 && body && blen) rc = write_all(fd, body, blen);
    sb_free(&req);
    if (rc != 0) {
        snprintf(err, errlen, "send to %s:%s failed: %s", host, port, strerror(errno));
        close(fd);
        return -1;
    }

    sbuf raw;
    sb_init(&raw);
    char buf[16384];
    for (;;) {
        int w = wait_readable(fd, deadline);
        if (w == 0) {
            snprintf(err, errlen, "timed out after %ds waiting for %s", timeout_s, url);
            close(fd);
            sb_free(&raw);
            return -1;
        }
        if (w < 0) break;
        ssize_t r = read(fd, buf, sizeof buf);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) break;
        sb_append(&raw, buf, (size_t)r);
        if (raw.len > (size_t)256 * 1024 * 1024) {
            snprintf(err, errlen, "response too large");
            close(fd);
            sb_free(&raw);
            return -1;
        }
    }
    close(fd);
    if (!raw.s) {
        snprintf(err, errlen, "empty response from %s", url);
        return -1;
    }
    char *hend = strstr(raw.s, "\r\n\r\n");
    if (!hend || strncmp(raw.s, "HTTP/", 5) != 0) {
        snprintf(err, errlen, "malformed HTTP response from %s", url);
        sb_free(&raw);
        return -1;
    }
    const char *sp = strchr(raw.s, ' ');
    *status = sp ? atoi(sp + 1) : 0;
    char *bodyp = hend + 4;
    size_t bl = raw.len - (size_t)(bodyp - raw.s);
    const char *te = find_header(raw.s, hend, "Transfer-Encoding");
    if (te && strncasecmp(te, "chunked", 7) == 0) {
        size_t nl = dechunk(bodyp, bl);
        if (nl == (size_t)-1) {
            snprintf(err, errlen, "bad chunked encoding from %s", url);
            sb_free(&raw);
            return -1;
        }
        bl = nl;
    } else {
        const char *cl = find_header(raw.s, hend, "Content-Length");
        if (cl) {
            size_t want = (size_t)strtoull(cl, NULL, 10);
            if (want < bl) bl = want;
        }
    }
    sb_append(resp, bodyp, bl);
    sb_free(&raw);
    return 0;
}

/* ---------- server side ---------- */

const char *http_reason(int status)
{
    switch (status) {
    case 200: return "OK";
    case 204: return "No Content";
    case 400: return "Bad Request";
    case 401: return "Unauthorized";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 408: return "Request Timeout";
    case 411: return "Length Required";
    case 413: return "Payload Too Large";
    case 431: return "Request Header Fields Too Large";
    case 500: return "Internal Server Error";
    case 501: return "Not Implemented";
    case 502: return "Bad Gateway";
    case 503: return "Service Unavailable";
    default: return "Unknown";
    }
}

void http_req_free(http_req *req)
{
    free(req->body);
    req->body = NULL;
    req->body_len = 0;
}

static void copy_header(const char *hdrs, const char *hend, const char *name, char *dst, size_t cap)
{
    dst[0] = '\0';
    const char *v = find_header(hdrs, hend, name);
    if (!v) return;
    const char *e = strstr(v, "\r\n");
    if (!e || e > hend) e = hend;
    size_t n = (size_t)(e - v);
    if (n >= cap) n = cap - 1;
    memcpy(dst, v, n);
    dst[n] = '\0';
    str_trim(dst);
}

int http_read_request(int fd, size_t max_body, int timeout_s, http_req *req)
{
    memset(req, 0, sizeof *req);
    long long deadline = now_ms() + (long long)timeout_s * 1000;
    sbuf raw;
    sb_init(&raw);
    char buf[8192];
    char *hend = NULL;
    while (!hend) {
        int w = wait_readable(fd, deadline);
        if (w <= 0) {
            sb_free(&raw);
            return w == 0 ? 408 : -1;
        }
        ssize_t r = read(fd, buf, sizeof buf);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) {
            sb_free(&raw);
            return -1;
        }
        sb_append(&raw, buf, (size_t)r);
        hend = strstr(raw.s, "\r\n\r\n");
        if (!hend && raw.len > 65536) {
            sb_free(&raw);
            return 431;
        }
    }
    /* request line */
    char *eol = strstr(raw.s, "\r\n");
    char *m_end = memchr(raw.s, ' ', (size_t)(eol - raw.s));
    if (!m_end) goto bad;
    char *p_start = m_end + 1;
    char *p_end = memchr(p_start, ' ', (size_t)(eol - p_start));
    if (!p_end || strncmp(p_end + 1, "HTTP/1.", 7) != 0) goto bad;
    if ((size_t)(m_end - raw.s) >= sizeof req->method || (size_t)(p_end - p_start) >= sizeof req->path) goto bad;
    memcpy(req->method, raw.s, (size_t)(m_end - raw.s));
    memcpy(req->path, p_start, (size_t)(p_end - p_start));

    const char *hdrs = eol + 2;
    copy_header(hdrs, hend, "Authorization", req->authorization, sizeof req->authorization);
    copy_header(hdrs, hend, "Content-Type", req->content_type, sizeof req->content_type);
    char te[64];
    copy_header(hdrs, hend, "Transfer-Encoding", te, sizeof te);
    if (te[0] && !str_ieq(te, "identity")) {
        sb_free(&raw);
        return 501;
    }
    char cl[32];
    copy_header(hdrs, hend, "Content-Length", cl, sizeof cl);
    size_t want = 0;
    if (cl[0]) {
        for (const char *c = cl; *c; c++)
            if (!isdigit((unsigned char)*c)) goto bad;
        want = (size_t)strtoull(cl, NULL, 10);
    }
    if (want > max_body) {
        sb_free(&raw);
        return 413;
    }
    size_t have = raw.len - (size_t)(hend + 4 - raw.s);
    sbuf body;
    sb_init(&body);
    sb_append(&body, hend + 4, have < want ? have : want);
    sb_free(&raw);
    while (body.len < want) {
        int w = wait_readable(fd, deadline);
        if (w <= 0) {
            sb_free(&body);
            return w == 0 ? 408 : -1;
        }
        size_t need = want - body.len;
        ssize_t r = read(fd, buf, need < sizeof buf ? need : sizeof buf);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) {
            sb_free(&body);
            return -1;
        }
        sb_append(&body, buf, (size_t)r);
    }
    req->body_len = body.len;
    req->body = sb_take(&body);
    return 0;
bad:
    sb_free(&raw);
    return 400;
}

int http_send(int fd, int status, const char *content_type, const char *body, size_t blen)
{
    sbuf h;
    sb_init(&h);
    sb_printf(&h,
              "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\nConnection: close\r\n"
              "Cache-Control: no-store\r\n\r\n",
              status, http_reason(status), content_type ? content_type : "application/json", blen);
    int rc = write_all(fd, h.s, h.len);
    if (rc == 0 && blen) rc = write_all(fd, body, blen);
    sb_free(&h);
    return rc;
}
