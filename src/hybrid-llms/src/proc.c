/* proc.c - subprocess execution (no shell) and command templates. */
#define _POSIX_C_SOURCE 200809L
#include "proc.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>


/* ---------- argv templates ---------- */

static void av_push(argvec *a, char *s)
{
    a->argv = xrealloc(a->argv, (a->argc + 2) * sizeof *a->argv);
    a->argv[a->argc++] = s;
    a->argv[a->argc] = NULL;
}

int argv_split(const char *cmd, argvec *out, char *err, size_t errlen)
{
    out->argv = NULL;
    out->argc = 0;
    const char *p = cmd;
    for (;;) {
        while (*p == ' ' || *p == '\t' || *p == '\n') p++;
        if (!*p) break;
        sbuf tok;
        sb_init(&tok);
        sb_append(&tok, "", 0);
        while (*p && *p != ' ' && *p != '\t' && *p != '\n') {
            if (*p == '\'') {
                const char *e = strchr(p + 1, '\'');
                if (!e) goto unterminated;
                sb_append(&tok, p + 1, (size_t)(e - p - 1));
                p = e + 1;
            } else if (*p == '"') {
                p++;
                while (*p && *p != '"') {
                    if (*p == '\\' && (p[1] == '"' || p[1] == '\\')) p++;
                    sb_putc(&tok, *p++);
                }
                if (*p != '"') goto unterminated;
                p++;
            } else if (*p == '\\' && p[1]) {
                sb_putc(&tok, p[1]);
                p += 2;
            } else {
                sb_putc(&tok, *p++);
            }
            continue;
        unterminated:
            sb_free(&tok);
            argv_free(out);
            snprintf(err, errlen, "unterminated quote in command: %s", cmd);
            return -1;
        }
        av_push(out, sb_take(&tok));
    }
    if (out->argc == 0) {
        snprintf(err, errlen, "empty command");
        return -1;
    }
    return 0;
}

void argv_subst(argvec *a, const char *name, const char *value)
{
    char ph[64];
    snprintf(ph, sizeof ph, "{%s}", name);
    size_t pl = strlen(ph);
    for (size_t i = 0; i < a->argc; i++) {
        if (!strstr(a->argv[i], ph)) continue;
        sbuf b;
        sb_init(&b);
        const char *s = a->argv[i];
        const char *hit;
        while ((hit = strstr(s, ph))) {
            sb_append(&b, s, (size_t)(hit - s));
            sb_puts(&b, value);
            s = hit + pl;
        }
        sb_puts(&b, s);
        free(a->argv[i]);
        a->argv[i] = sb_take(&b);
    }
}

int argv_has(const argvec *a, const char *placeholder)
{
    for (size_t i = 0; i < a->argc; i++)
        if (strstr(a->argv[i], placeholder)) return 1;
    return 0;
}

void argv_free(argvec *a)
{
    for (size_t i = 0; i < a->argc; i++) free(a->argv[i]);
    free(a->argv);
    a->argv = NULL;
    a->argc = 0;
}

/* ---------- PATH lookup ---------- */

int prog_on_path(const char *prog)
{
    if (!prog || !*prog) return 0;
    if (strchr(prog, '/')) return access(prog, X_OK) == 0;
    const char *path = getenv("PATH");
    if (!path) path = "/usr/local/bin:/usr/bin:/bin";
    char *dup = xstrdup(path);
    int found = 0;
    char *save = NULL;
    for (char *dir = strtok_r(dup, ":", &save); dir && !found; dir = strtok_r(NULL, ":", &save)) {
        char full[4096];
        snprintf(full, sizeof full, "%s/%s", *dir ? dir : ".", prog);
        struct stat st;
        if (stat(full, &st) == 0 && S_ISREG(st.st_mode) && access(full, X_OK) == 0) found = 1;
    }
    free(dup);
    return found;
}

/* ---------- running ---------- */

static void set_cloexec(int fd)
{
    int fl = fcntl(fd, F_GETFD);
    if (fl >= 0) fcntl(fd, F_SETFD, fl | FD_CLOEXEC);
}

static void set_nonblock(int fd)
{
    int fl = fcntl(fd, F_GETFL);
    if (fl >= 0) fcntl(fd, F_SETFL, fl | O_NONBLOCK);
}

static int make_pipe(int p[2])
{
    if (pipe(p) != 0) return -1;
    set_cloexec(p[0]);
    set_cloexec(p[1]);
    return 0;
}

/* Close every inherited descriptor above stderr except keep (or -1). */
static void close_extra_fds(int keep)
{
    struct rlimit rl;
    long maxfd = 1024;
    if (getrlimit(RLIMIT_NOFILE, &rl) == 0 && rl.rlim_cur != RLIM_INFINITY) maxfd = (long)rl.rlim_cur;
    if (maxfd > 65536) maxfd = 65536;
    for (long fd = 3; fd < maxfd; fd++)
        if (fd != keep) close((int)fd);
}

static void child_exec(char *const argv[], const char *const extra_env[])
{
    close_extra_fds(-1);
    signal(SIGPIPE, SIG_DFL);
    signal(SIGINT, SIG_DFL);
    signal(SIGTERM, SIG_DFL);
    if (extra_env) {
        for (size_t i = 0; extra_env[i]; i++) {
            const char *eq = strchr(extra_env[i], '=');
            if (!eq) continue;
            char key[256];
            size_t kl = (size_t)(eq - extra_env[i]);
            if (kl == 0 || kl >= sizeof key) continue;
            memcpy(key, extra_env[i], kl);
            key[kl] = '\0';
            setenv(key, eq + 1, 1);
        }
    }
    execvp(argv[0], argv);
    char msg[512];
    int n = snprintf(msg, sizeof msg, "hybrid-llms: cannot execute '%s': %s\n", argv[0], strerror(errno));
    if (n > 0) {
        ssize_t ignored = write(STDERR_FILENO, msg, (size_t)n);
        (void)ignored;
    }
    _exit(127);
}

int proc_run(char *const argv[], const char *const extra_env[], const char *input, size_t inlen, int timeout_s,
             size_t max_out, sbuf *out, sbuf *errout, int *exit_code, int *timed_out, char *err, size_t errlen)
{
    int pin[2], pout[2], perr[2];
    *exit_code = -1;
    *timed_out = 0;
    if (make_pipe(pin) != 0) goto pipe_fail0;
    if (make_pipe(pout) != 0) goto pipe_fail1;
    if (make_pipe(perr) != 0) goto pipe_fail2;

    pid_t pid = fork();
    if (pid < 0) {
        snprintf(err, errlen, "fork: %s", strerror(errno));
        close(pin[0]); close(pin[1]); close(pout[0]); close(pout[1]); close(perr[0]); close(perr[1]);
        return -1;
    }
    if (pid == 0) {
        setpgid(0, 0);
        dup2(pin[0], STDIN_FILENO);
        dup2(pout[1], STDOUT_FILENO);
        dup2(perr[1], STDERR_FILENO);
        child_exec(argv, extra_env);
    }
    setpgid(pid, pid); /* avoid a race with the child's own setpgid */
    close(pin[0]);
    close(pout[1]);
    close(perr[1]);
    int fin = pin[1], fo = pout[0], fe = perr[0];
    set_nonblock(fin);
    set_nonblock(fo);
    set_nonblock(fe);
    size_t written = 0;
    if (!input || inlen == 0) {
        close(fin);
        fin = -1;
    }
    long long deadline = now_ms() + (long long)timeout_s * 1000;
    char buf[16384];
    while (fo >= 0 || fe >= 0) {
        struct pollfd pf[3];
        int n = 0, io = -1, ie = -1, ii = -1;
        if (fo >= 0) { pf[n].fd = fo; pf[n].events = POLLIN; io = n++; }
        if (fe >= 0) { pf[n].fd = fe; pf[n].events = POLLIN; ie = n++; }
        if (fin >= 0) { pf[n].fd = fin; pf[n].events = POLLOUT; ii = n++; }
        long long left = deadline - now_ms();
        if (left <= 0) {
            *timed_out = 1;
            break;
        }
        int r = poll(pf, (nfds_t)n, left > 1000000 ? 1000000 : (int)left);
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) continue;
        if (ii >= 0 && (pf[ii].revents & (POLLOUT | POLLERR | POLLHUP))) {
            ssize_t w = write(fin, input + written, inlen - written);
            if (w > 0) written += (size_t)w;
            if ((w < 0 && errno != EAGAIN && errno != EINTR) || written >= inlen) {
                close(fin);
                fin = -1;
            }
        }
        int idx[2] = {io, ie};
        int *fds[2] = {&fo, &fe};
        sbuf *dst[2] = {out, errout};
        for (int k = 0; k < 2; k++) {
            if (idx[k] < 0 || !(pf[idx[k]].revents & (POLLIN | POLLHUP | POLLERR))) continue;
            ssize_t rd = read(*fds[k], buf, sizeof buf);
            if (rd > 0) {
                if (dst[k]->len < max_out) {
                    size_t take = (size_t)rd;
                    if (dst[k]->len + take > max_out) take = max_out - dst[k]->len;
                    sb_append(dst[k], buf, take);
                }
            } else if (rd == 0 || (errno != EAGAIN && errno != EINTR)) {
                close(*fds[k]);
                *fds[k] = -1;
            }
        }
    }
    if (fin >= 0) close(fin);
    if (fo >= 0) close(fo);
    if (fe >= 0) close(fe);

    int st = 0;
    if (*timed_out) {
        kill(-pid, SIGTERM);
        long long grace = now_ms() + 3000;
        while (waitpid(pid, &st, WNOHANG) == 0) {
            if (now_ms() > grace) {
                kill(-pid, SIGKILL);
                waitpid(pid, &st, 0);
                break;
            }
            struct timespec ts = {0, 50 * 1000000L};
            nanosleep(&ts, NULL);
        }
        *exit_code = -1;
        return 0;
    }
    /* Output streams closed; wait for exit but never forever. */
    for (;;) {
        pid_t w = waitpid(pid, &st, WNOHANG);
        if (w == pid) break;
        if (w < 0 && errno != EINTR) {
            st = 0;
            break;
        }
        if (now_ms() > deadline) {
            *timed_out = 1;
            kill(-pid, SIGKILL);
            waitpid(pid, &st, 0);
            *exit_code = -1;
            return 0;
        }
        struct timespec ts = {0, 20 * 1000000L};
        nanosleep(&ts, NULL);
    }
    *exit_code = WIFEXITED(st) ? WEXITSTATUS(st) : -1;
    return 0;

pipe_fail2:
    close(pout[0]);
    close(pout[1]);
pipe_fail1:
    close(pin[0]);
    close(pin[1]);
pipe_fail0:
    snprintf(err, errlen, "pipe: %s", strerror(errno));
    return -1;
}

pid_t proc_spawn_detached(char *const argv[], const char *log_path, char *err, size_t errlen)
{
    int errp[2];
    if (make_pipe(errp) != 0) {
        snprintf(err, errlen, "pipe: %s", strerror(errno));
        return -1;
    }
    pid_t pid = fork();
    if (pid < 0) {
        snprintf(err, errlen, "fork: %s", strerror(errno));
        close(errp[0]);
        close(errp[1]);
        return -1;
    }
    if (pid == 0) {
        close(errp[0]);
        setsid();
        close_extra_fds(errp[1]);
        int devnull = open("/dev/null", O_RDWR);
        int logfd = log_path ? open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0644) : -1;
        if (logfd < 0) logfd = devnull;
        if (devnull >= 0) dup2(devnull, STDIN_FILENO);
        if (logfd >= 0) {
            dup2(logfd, STDOUT_FILENO);
            dup2(logfd, STDERR_FILENO);
        }
        signal(SIGPIPE, SIG_DFL);
        signal(SIGINT, SIG_DFL);
        signal(SIGTERM, SIG_DFL);
        execvp(argv[0], argv);
        int e = errno;
        ssize_t ignored = write(errp[1], &e, sizeof e);
        (void)ignored;
        _exit(127);
    }
    close(errp[1]);
    int e = 0;
    ssize_t r;
    do {
        r = read(errp[0], &e, sizeof e);
    } while (r < 0 && errno == EINTR);
    close(errp[0]);
    if (r == (ssize_t)sizeof e) {
        waitpid(pid, NULL, 0);
        snprintf(err, errlen, "cannot execute '%s': %s", argv[0], strerror(e));
        return -1;
    }
    return pid;
}
