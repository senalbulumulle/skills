/* engine.c - local model discovery and the managed inference engine. */
#define _POSIX_C_SOURCE 200809L
#include "engine.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "http.h"
#include "proc.h"

#define SCAN_MAX_DEPTH 4
#define SCAN_MAX_MODELS 1024

void expand_home(const char *in, char *out, size_t cap)
{
    const char *home = getenv("HOME");
    if (in[0] == '~' && (in[1] == '/' || in[1] == '\0') && home && *home)
        snprintf(out, cap, "%s%s", home, in + 1);
    else
        snprintf(out, cap, "%s", in);
}

const char *model_kind_name(int kind)
{
    return kind == MODEL_GGUF ? "gguf" : kind == MODEL_MLX ? "mlx" : "unknown";
}

static int ends_with_ci(const char *s, const char *suf)
{
    size_t a = strlen(s), b = strlen(suf);
    return a >= b && strcasecmp(s + a - b, suf) == 0;
}

static int contains_ci(const char *hay, const char *needle)
{
    size_t n = strlen(needle);
    if (n == 0) return 1;
    for (; *hay; hay++)
        if (strncasecmp(hay, needle, n) == 0) return 1;
    return 0;
}

/* Split GGUF shards are named *-00002-of-00005.gguf; keep only shard 1. */
static int is_secondary_shard(const char *name)
{
    const char *of = strstr(name, "-of-");
    if (!of || of - name < 6) return 0;
    const char *num = of - 5;
    if (num[-1] != '-') return 0;
    for (int i = 0; i < 5; i++)
        if (num[i] < '0' || num[i] > '9') return 0;
    return strncmp(num, "00001", 5) != 0;
}

/* MLX folder: contains config.json and at least one .safetensors file. */
static long long mlx_weights_size(const char *dir)
{
    char p[4096];
    snprintf(p, sizeof p, "%s/config.json", dir);
    struct stat st;
    if (stat(p, &st) != 0 || !S_ISREG(st.st_mode)) return -1;
    DIR *d = opendir(dir);
    if (!d) return -1;
    long long total = 0;
    int found = 0;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!ends_with_ci(e->d_name, ".safetensors")) continue;
        snprintf(p, sizeof p, "%s/%s", dir, e->d_name);
        if (stat(p, &st) == 0 && S_ISREG(st.st_mode)) {
            total += (long long)st.st_size;
            found = 1;
        }
    }
    closedir(d);
    return found ? total : -1;
}

static void add_model(model_list *l, const char *path, const char *rel, int kind, long long size)
{
    if (l->n >= SCAN_MAX_MODELS) return;
    l->v = xrealloc(l->v, (l->n + 1) * sizeof *l->v);
    l->v[l->n].path = xstrdup(path);
    l->v[l->n].name = xstrdup(rel);
    l->v[l->n].kind = kind;
    l->v[l->n].size = size;
    l->n++;
}

static void scan_dir(model_list *l, const char *dir, const char *rel, int depth)
{
    DIR *d = opendir(dir);
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char full[4096], r[4096];
        snprintf(full, sizeof full, "%s/%s", dir, e->d_name);
        if (rel[0]) snprintf(r, sizeof r, "%s/%s", rel, e->d_name);
        else snprintf(r, sizeof r, "%s", e->d_name);
        struct stat st;
        if (stat(full, &st) != 0) continue;
        if (S_ISDIR(st.st_mode)) {
            long long sz = mlx_weights_size(full);
            if (sz >= 0) add_model(l, full, r, MODEL_MLX, sz);
            else if (depth < SCAN_MAX_DEPTH) scan_dir(l, full, r, depth + 1);
        } else if (S_ISREG(st.st_mode) && ends_with_ci(e->d_name, ".gguf")) {
            if (contains_ci(e->d_name, "mmproj") || is_secondary_shard(e->d_name)) continue;
            add_model(l, full, r, MODEL_GGUF, (long long)st.st_size);
        }
    }
    closedir(d);
}

static int cmp_model(const void *a, const void *b)
{
    return strcmp(((const model_info *)a)->name, ((const model_info *)b)->name);
}

int models_scan(const config *c, model_list *out, char *err, size_t errlen)
{
    out->v = NULL;
    out->n = 0;
    char dir[1024];
    expand_home(c->models_dir, dir, sizeof dir);
    struct stat st;
    if (stat(dir, &st) != 0 || !S_ISDIR(st.st_mode)) {
        snprintf(err, errlen, "models_dir '%s' does not exist or is not a directory", dir);
        return -1;
    }
    scan_dir(out, dir, "", 0);
    if (out->n > 1) qsort(out->v, out->n, sizeof *out->v, cmp_model);
    return 0;
}

void model_info_free(model_info *m)
{
    free(m->path);
    free(m->name);
    m->path = m->name = NULL;
}

void models_free(model_list *l)
{
    for (size_t i = 0; i < l->n; i++) model_info_free(&l->v[i]);
    free(l->v);
    l->v = NULL;
    l->n = 0;
}

static void copy_model(model_info *dst, const model_info *src)
{
    dst->path = xstrdup(src->path);
    dst->name = xstrdup(src->name);
    dst->kind = src->kind;
    dst->size = src->size;
}

static const char *base_name(const char *p)
{
    const char *s = strrchr(p, '/');
    return s ? s + 1 : p;
}

int models_resolve(const config *c, const char *want, model_info *out, char *err, size_t errlen)
{
    memset(out, 0, sizeof *out);
    if (want && want[0] == '/') {
        struct stat st;
        if (stat(want, &st) != 0) {
            snprintf(err, errlen, "model path '%s' not found", want);
            return -1;
        }
        long long sz = S_ISDIR(st.st_mode) ? mlx_weights_size(want) : -1;
        if (S_ISDIR(st.st_mode) && sz < 0) {
            snprintf(err, errlen, "'%s' is not an MLX model folder (needs config.json and *.safetensors)", want);
            return -1;
        }
        if (!S_ISDIR(st.st_mode) && !ends_with_ci(want, ".gguf")) {
            snprintf(err, errlen, "'%s' is not a .gguf file", want);
            return -1;
        }
        out->path = xstrdup(want);
        out->name = xstrdup(base_name(want));
        out->kind = S_ISDIR(st.st_mode) ? MODEL_MLX : MODEL_GGUF;
        out->size = S_ISDIR(st.st_mode) ? sz : (long long)st.st_size;
        return 0;
    }
    model_list l;
    if (models_scan(c, &l, err, errlen) != 0) return -1;
    if (l.n == 0) {
        char dir[1024];
        expand_home(c->models_dir, dir, sizeof dir);
        snprintf(err, errlen, "no models found in %s (expected *.gguf files or MLX folders)", dir);
        models_free(&l);
        return -1;
    }
    const model_info *hit = NULL;
    if (!want || !*want) {
        hit = &l.v[0];
    } else {
        for (size_t i = 0; i < l.n && !hit; i++)
            if (strcmp(l.v[i].name, want) == 0) hit = &l.v[i];
        for (size_t i = 0; i < l.n && !hit; i++) {
            const char *b = base_name(l.v[i].name);
            size_t wl = strlen(want);
            if (strcasecmp(b, want) == 0) hit = &l.v[i];
            else if (ends_with_ci(b, ".gguf") && strlen(b) == wl + 5 && strncasecmp(b, want, wl) == 0)
                hit = &l.v[i];
        }
        for (size_t i = 0; i < l.n && !hit; i++)
            if (contains_ci(l.v[i].name, want)) hit = &l.v[i];
    }
    if (!hit) {
        sbuf names;
        sb_init(&names);
        for (size_t i = 0; i < l.n && i < 20; i++) sb_printf(&names, "%s%s", i ? ", " : "", l.v[i].name);
        snprintf(err, errlen, "no local model matches '%s'; available: %s", want, names.s ? names.s : "");
        sb_free(&names);
        models_free(&l);
        return -1;
    }
    copy_model(out, hit);
    models_free(&l);
    return 0;
}

/* ---------- engine state ---------- */

static pthread_mutex_t engine_mu = PTHREAD_MUTEX_INITIALIZER;
static pid_t owned_pid = 0; /* engine started by this process */

static void state_dir(char *out, size_t cap)
{
    /* Always under $HOME (not XDG_CACHE_HOME): every process, including MCP servers
     * started with a reduced environment, must agree on the same state files. */
    const char *home = getenv("HOME");
    if (home && *home) snprintf(out, cap, "%s/.cache/hybrid-llms", home);
    else snprintf(out, cap, "/tmp/hybrid-llms-%ld", (long)getuid());
}

static int ensure_dir(const char *path)
{
    char tmp[1024];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0700) != 0 && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    if (mkdir(tmp, 0700) != 0 && errno != EEXIST) return -1;
    return 0;
}

static void state_file(const config *c, const char *ext, char *out, size_t cap)
{
    char d[1024];
    state_dir(d, sizeof d);
    snprintf(out, cap, "%s/engine-%d.%s", d, c->engine_port, ext);
}

typedef struct {
    pid_t pid;
    char path[4096];
    int kind;
} engine_state;

static int read_state(const config *c, engine_state *s)
{
    memset(s, 0, sizeof *s);
    char p[1100];
    state_file(c, "state", p, sizeof p);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    long pid = 0;
    int kind = 0;
    char line[4200];
    int ok = 0;
    if (fgets(line, sizeof line, f)) pid = strtol(line, NULL, 10);
    if (fgets(line, sizeof line, f)) kind = atoi(line);
    if (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\n")] = '\0';
        snprintf(s->path, sizeof s->path, "%s", line);
        ok = 1;
    }
    fclose(f);
    if (!ok || pid <= 1) return -1;
    s->pid = (pid_t)pid;
    s->kind = kind;
    return 0;
}

static int write_state(const config *c, const engine_state *s)
{
    char p[1100], tmp[1200];
    state_file(c, "state", p, sizeof p);
    snprintf(tmp, sizeof tmp, "%s.tmp.%ld", p, (long)getpid());
    FILE *f = fopen(tmp, "w");
    if (!f) return -1;
    fprintf(f, "%ld\n%d\n%s\n", (long)s->pid, s->kind, s->path);
    if (fclose(f) != 0) {
        unlink(tmp);
        return -1;
    }
    return rename(tmp, p);
}

static void clear_state(const config *c)
{
    char p[1100];
    state_file(c, "state", p, sizeof p);
    unlink(p);
}

static int pid_alive(pid_t pid)
{
    if (pid <= 1) return 0;
    /* Reap it first if it is our own exited child (kill() succeeds on zombies). */
    int st;
    pid_t w = waitpid(pid, &st, WNOHANG);
    if (w == pid) return 0;
    if (kill(pid, 0) == 0) return 1;
    return errno == EPERM;
}

static void sleep_ms(long ms)
{
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000L};
    while (nanosleep(&ts, &ts) != 0 && errno == EINTR) {
    }
}

static void stop_pid(pid_t pid)
{
    if (!pid_alive(pid)) return;
    kill(pid, SIGTERM);
    for (int i = 0; i < 100 && pid_alive(pid); i++) sleep_ms(100);
    if (pid_alive(pid)) {
        kill(pid, SIGKILL);
        for (int i = 0; i < 20 && pid_alive(pid); i++) sleep_ms(100);
    }
}

/* 200 = ready, 503 = loading, 0 = nothing listening, other = unexpected. */
static int probe(const config *c, int kind)
{
    char url[128];
    snprintf(url, sizeof url, "http://127.0.0.1:%d%s", c->engine_port, kind == MODEL_MLX ? "/v1/models" : "/health");
    int status = 0;
    sbuf resp;
    sb_init(&resp);
    char err[256];
    int rc = http_request("GET", url, NULL, NULL, 0, 5, &status, &resp, err, sizeof err);
    sb_free(&resp);
    return rc == 0 ? status : 0;
}

static void log_tail(const char *log_path, char *out, size_t cap)
{
    out[0] = '\0';
    FILE *f = fopen(log_path, "r");
    if (!f) return;
    if (fseek(f, 0, SEEK_END) == 0) {
        long sz = ftell(f);
        long start = sz > 600 ? sz - 600 : 0;
        fseek(f, start, SEEK_SET);
        size_t n = fread(out, 1, cap - 1, f);
        out[n] = '\0';
        for (char *p = out; *p; p++)
            if (*p == '\n' || *p == '\r') *p = ' ';
        str_trim(out);
    }
    fclose(f);
}

static int lock_engine(const config *c, char *err, size_t errlen)
{
    char d[1024], lp[1100];
    state_dir(d, sizeof d);
    if (ensure_dir(d) != 0) {
        snprintf(err, errlen, "cannot create %s: %s", d, strerror(errno));
        return -1;
    }
    state_file(c, "lock", lp, sizeof lp);
    int fd = open(lp, O_RDWR | O_CREAT, 0600);
    if (fd < 0) {
        snprintf(err, errlen, "cannot open %s: %s", lp, strerror(errno));
        return -1;
    }
    int fl = fcntl(fd, F_GETFD);
    if (fl >= 0) fcntl(fd, F_SETFD, fl | FD_CLOEXEC);
    while (flock(fd, LOCK_EX) != 0) {
        if (errno != EINTR) {
            snprintf(err, errlen, "flock %s: %s", lp, strerror(errno));
            close(fd);
            return -1;
        }
    }
    return fd;
}

static void unlock_engine(int fd)
{
    if (fd >= 0) {
        flock(fd, LOCK_UN);
        close(fd);
    }
}

static void fill_out(const config *c, const model_info *m, char *base_url, size_t bcap, char *model_field,
                     size_t mcap)
{
    snprintf(base_url, bcap, "http://127.0.0.1:%d", c->engine_port);
    /* llama-server ignores the field; mlx_lm.server loads whatever path it names. */
    snprintf(model_field, mcap, "%s", m->kind == MODEL_MLX ? m->path : base_name(m->path));
}

/* Wait until ready; fails early if pid dies. */
static int wait_ready(const config *c, int kind, pid_t pid, const char *log_path, char *err, size_t errlen)
{
    long long deadline = now_ms() + (long long)c->engine_load_timeout * 1000;
    while (now_ms() < deadline) {
        if (pid > 0 && !pid_alive(pid)) {
            char tail[640];
            log_tail(log_path, tail, sizeof tail);
            snprintf(err, errlen, "local engine exited during startup (log %s): %s", log_path, tail);
            return -1;
        }
        int s = probe(c, kind);
        if (s == 200) return 0;
        sleep_ms(250);
    }
    snprintf(err, errlen, "local engine not ready after %ds (log %s)", c->engine_load_timeout, log_path);
    return -1;
}

int engine_ensure(const config *c, const model_info *m, char *base_url, size_t bcap, char *model_field, size_t mcap,
                  char *err, size_t errlen)
{
    pthread_mutex_lock(&engine_mu);
    int lfd = lock_engine(c, err, errlen);
    if (lfd < 0) {
        pthread_mutex_unlock(&engine_mu);
        return -1;
    }
    char log_path[1100];
    state_file(c, "log", log_path, sizeof log_path);
    int rc = -1;

    engine_state s;
    if (read_state(c, &s) == 0) {
        if (pid_alive(s.pid) && strcmp(s.path, m->path) == 0) {
            if (wait_ready(c, m->kind, s.pid, log_path, err, errlen) == 0) {
                fill_out(c, m, base_url, bcap, model_field, mcap);
                rc = 0;
                goto out;
            }
            log_msg(LOG_WARN, "existing engine pid %ld unhealthy; restarting", (long)s.pid);
        }
        if (pid_alive(s.pid)) {
            log_msg(LOG_INFO, "stopping engine pid %ld (%s) to load %s", (long)s.pid, s.path, m->name);
            stop_pid(s.pid);
        }
        if (s.pid == owned_pid) owned_pid = 0;
        clear_state(c);
    }
    if (probe(c, MODEL_GGUF) != 0) {
        snprintf(err, errlen,
                 "port %d is already used by a process hybrid-llms did not start; set engine_port to a free port",
                 c->engine_port);
        goto out;
    }

    {
        const char *tmpl = m->kind == MODEL_MLX ? c->mlx_cmd : c->llama_cmd;
        argvec av;
        if (argv_split(tmpl, &av, err, errlen) != 0) goto out;
        char port[16], ctx[16];
        snprintf(port, sizeof port, "%d", c->engine_port);
        snprintf(ctx, sizeof ctx, "%d", c->engine_ctx);
        argv_subst(&av, "model", m->path);
        argv_subst(&av, "port", port);
        argv_subst(&av, "ctx", ctx);
        argv_subst(&av, "name", base_name(m->name));
        if (!prog_on_path(av.argv[0])) {
            snprintf(err, errlen, "'%s' not found on PATH (needed for %s models; install %s or set %s)", av.argv[0],
                     model_kind_name(m->kind), m->kind == MODEL_MLX ? "mlx-lm" : "llama.cpp",
                     m->kind == MODEL_MLX ? "mlx_cmd" : "llama_cmd");
            argv_free(&av);
            goto out;
        }
        log_msg(LOG_INFO, "starting %s engine for %s on port %d", model_kind_name(m->kind), m->name, c->engine_port);
        pid_t pid = proc_spawn_detached(av.argv, log_path, err, errlen);
        argv_free(&av);
        if (pid < 0) goto out;
        engine_state ns;
        memset(&ns, 0, sizeof ns);
        ns.pid = pid;
        ns.kind = m->kind;
        snprintf(ns.path, sizeof ns.path, "%s", m->path);
        if (write_state(c, &ns) != 0) log_msg(LOG_WARN, "could not write engine state file");
        owned_pid = pid;
        if (wait_ready(c, m->kind, pid, log_path, err, errlen) != 0) {
            stop_pid(pid);
            clear_state(c);
            owned_pid = 0;
            goto out;
        }
        fill_out(c, m, base_url, bcap, model_field, mcap);
        rc = 0;
    }
out:
    unlock_engine(lfd);
    pthread_mutex_unlock(&engine_mu);
    return rc;
}

int engine_stop(const config *c, char *err, size_t errlen)
{
    pthread_mutex_lock(&engine_mu);
    int lfd = lock_engine(c, err, errlen);
    if (lfd < 0) {
        pthread_mutex_unlock(&engine_mu);
        return -1;
    }
    engine_state s;
    if (read_state(c, &s) == 0) {
        stop_pid(s.pid);
        clear_state(c);
        if (s.pid == owned_pid) owned_pid = 0;
    }
    unlock_engine(lfd);
    pthread_mutex_unlock(&engine_mu);
    return 0;
}

void engine_shutdown_owned(const config *c)
{
    if (c->engine_keep_alive || owned_pid == 0) return;
    engine_state s;
    if (read_state(c, &s) == 0 && s.pid == owned_pid) {
        char err[256];
        engine_stop(c, err, sizeof err);
    } else {
        stop_pid(owned_pid);
    }
    owned_pid = 0;
}

json *engine_status_json(const config *c)
{
    json *o = json_new_obj();
    json_set_num(o, "port", c->engine_port);
    engine_state s;
    if (read_state(c, &s) == 0 && pid_alive(s.pid)) {
        json_set_bool(o, "running", 1);
        json_set_num(o, "pid", (double)s.pid);
        json_set_str(o, "model_path", s.path);
        json_set_str(o, "kind", model_kind_name(s.kind));
        json_set_bool(o, "ready", probe(c, s.kind) == 200);
    } else {
        json_set_bool(o, "running", 0);
    }
    return o;
}
