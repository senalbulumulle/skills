/* proc.h - subprocess execution (no shell) and command templates. */
#ifndef HYBRID_PROC_H
#define HYBRID_PROC_H

#include <stddef.h>
#include <sys/types.h>

#include "util.h"

typedef struct {
    char **argv;
    size_t argc;
} argvec;

/* Split a command string with shell-like quoting ('..', "..", backslash). No
 * expansion is performed. Returns 0 on success. */
int argv_split(const char *cmd, argvec *out, char *err, size_t errlen);
/* Replace every occurrence of {name} inside each argument with value. */
void argv_subst(argvec *a, const char *name, const char *value);
int argv_has(const argvec *a, const char *placeholder);
void argv_free(argvec *a);

/* Run argv[0] (PATH lookup) with input on stdin. Captures stdout/stderr (up to
 * max_out bytes each). Kills the whole process group on timeout.
 * extra_env: NULL-terminated "KEY=VALUE" list added to the child's environment.
 * Returns 0 if the process ran (see *exit_code; -1 = killed by signal / timeout),
 * -1 if it could not be started. */
int proc_run(char *const argv[], const char *const extra_env[], const char *input, size_t inlen, int timeout_s,
             size_t max_out, sbuf *out, sbuf *errout, int *exit_code, int *timed_out, char *err, size_t errlen);

/* Start argv in the background, detached into its own session, with stdout and
 * stderr appended to log_path (or /dev/null). Returns the pid or -1. */
pid_t proc_spawn_detached(char *const argv[], const char *log_path, char *err, size_t errlen);

/* 1 if prog (no slash) is found on PATH or is an executable path. */
int prog_on_path(const char *prog);

#endif
