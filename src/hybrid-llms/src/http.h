/* http.h - minimal HTTP/1.1 client (plain http) and server-side helpers. */
#ifndef HYBRID_HTTP_H
#define HYBRID_HTTP_H

#include <stddef.h>

#include "util.h"

/* Perform one request. extra_headers is "Name: value\r\n..." or NULL.
 * Returns 0 when a response was received (check *status), -1 on transport error. */
int http_request(const char *method, const char *url, const char *extra_headers, const char *body, size_t blen,
                 int timeout_s, int *status, sbuf *resp, char *err, size_t errlen);

typedef struct {
    char method[16];
    char path[2048];
    char authorization[512];
    char content_type[128];
    char *body;
    size_t body_len;
} http_req;

/* Read a request from fd. Returns 0 on success, otherwise an HTTP status code
 * to answer with (400, 408, 413, 431, 501), or -1 if the peer went away. */
int http_read_request(int fd, size_t max_body, int timeout_s, http_req *req);
void http_req_free(http_req *req);

/* Write a full response with Content-Length. Returns 0 on success. */
int http_send(int fd, int status, const char *content_type, const char *body, size_t blen);
/* Write all bytes. Returns 0 on success. */
int write_all(int fd, const char *buf, size_t n);
const char *http_reason(int status);

#endif
