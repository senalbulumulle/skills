/* server.h - HTTP daemon with an OpenAI-compatible API plus /v1/hybrid. */
#ifndef HYBRID_SERVER_H
#define HYBRID_SERVER_H

#include "config.h"

int server_main(const config *c);

#endif
