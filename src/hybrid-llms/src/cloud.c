/* cloud.c - run cloud model CLIs (claude, codex, gemini) headlessly. */
#define _POSIX_C_SOURCE 200809L
#include "cloud.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "proc.h"

int cloud_parse(const char *s, cloud_id *out)
{
    if (!s) return -1;
    if (str_ieq(s, "host")) *out = CLOUD_HOST;
    else if (str_ieq(s, "claude")) *out = CLOUD_CLAUDE;
    else if (str_ieq(s, "codex")) *out = CLOUD_CODEX;
    else if (str_ieq(s, "gemini")) *out = CLOUD_GEMINI;
    else if (str_ieq(s, "none")) *out = CLOUD_NONE;
    else return -1;
    return 0;
}

const char *cloud_name(cloud_id id)
{
    switch (id) {
    case CLOUD_HOST: return "host";
    case CLOUD_CLAUDE: return "claude";
    case CLOUD_CODEX: return "codex";
    case CLOUD_GEMINI: return "gemini";
    default: return "none";
    }
}

int cloud_depth(void)
{
    const char *d = getenv("HYBRID_LLMS_DEPTH");
    if (!d || !*d) return 0;
    int n = atoi(d);
    return n < 0 ? 0 : n;
}

static const char *cmd_for(const config *c, cloud_id id)
{
    switch (id) {
    case CLOUD_CLAUDE: return c->claude_cmd;
    case CLOUD_CODEX: return c->codex_cmd;
    case CLOUD_GEMINI: return c->gemini_cmd;
    default: return NULL;
    }
}

static int read_file(const char *path, size_t max, sbuf *out)
{
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && out->len < max) sb_append(out, buf, n);
    fclose(f);
    return 0;
}

/* Last non-empty lines of stderr, for error messages. */
static void tail_text(const char *s, char *dst, size_t cap)
{
    dst[0] = '\0';
    if (!s) return;
    size_t n = strlen(s);
    size_t start = n > 400 ? n - 400 : 0;
    snprintf(dst, cap, "%s", s + start);
    for (char *p = dst; *p; p++)
        if (*p == '\n' || *p == '\r') *p = ' ';
    str_trim(dst);
}

int cloud_ask(const config *c, cloud_id id, const char *prompt, sbuf *out, char *err, size_t errlen)
{
    const char *tmpl = cmd_for(c, id);
    if (!tmpl) {
        snprintf(err, errlen, "cloud '%s' cannot be run as a subprocess", cloud_name(id));
        return -1;
    }
    int depth = cloud_depth();
    if (depth >= c->max_depth) {
        snprintf(err, errlen,
                 "refusing nested cloud call (depth %d >= max_depth %d): this hybrid-llms runs inside a cloud CLI "
                 "that hybrid-llms started",
                 depth, c->max_depth);
        return -1;
    }
    argvec av;
    if (argv_split(tmpl, &av, err, errlen) != 0) return -1;
    if (!prog_on_path(av.argv[0])) {
        snprintf(err, errlen, "'%s' not found on PATH (set %s_cmd in the config)", av.argv[0], cloud_name(id));
        argv_free(&av);
        return -1;
    }

    char outfile[1024] = "";
    if (argv_has(&av, "{out}")) {
        const char *tmpdir = getenv("TMPDIR");
        if (!tmpdir || !*tmpdir) tmpdir = "/tmp";
        size_t tl = strlen(tmpdir);
        snprintf(outfile, sizeof outfile, "%s%shybrid-llms-XXXXXX", tmpdir, (tl && tmpdir[tl - 1] == '/') ? "" : "/");
        int fd = mkstemp(outfile);
        if (fd < 0) {
            snprintf(err, errlen, "mkstemp: %s", strerror(errno));
            argv_free(&av);
            return -1;
        }
        close(fd);
        argv_subst(&av, "out", outfile);
    }
    int prompt_in_argv = argv_has(&av, "{prompt}");
    if (prompt_in_argv) argv_subst(&av, "prompt", prompt);

    char depth_env[64];
    snprintf(depth_env, sizeof depth_env, "HYBRID_LLMS_DEPTH=%d", depth + 1);
    const char *env[] = {depth_env, "NO_COLOR=1", NULL};

    sbuf so, se;
    sb_init(&so);
    sb_init(&se);
    int code = -1, timed_out = 0;
    long long t0 = now_ms();
    log_msg(LOG_INFO, "cloud call: %s (%zu chars)", cloud_name(id), strlen(prompt));
    int rc = proc_run(av.argv, env, prompt_in_argv ? NULL : prompt, prompt_in_argv ? 0 : strlen(prompt),
                      c->cloud_timeout, c->max_output, &so, &se, &code, &timed_out, err, errlen);
    argv_free(&av);
    log_msg(LOG_INFO, "cloud call: %s finished in %lld ms (exit %d)", cloud_name(id), now_ms() - t0, code);

    if (rc == 0 && outfile[0]) {
        sbuf fileout;
        sb_init(&fileout);
        if (read_file(outfile, c->max_output, &fileout) == 0 && fileout.len > 0) {
            sb_free(&so);
            so = fileout;
        } else {
            sb_free(&fileout);
        }
    }
    if (outfile[0]) unlink(outfile);

    if (rc != 0) goto fail;
    if (timed_out) {
        snprintf(err, errlen, "%s timed out after %ds", cloud_name(id), c->cloud_timeout);
        rc = -1;
        goto fail;
    }
    char *text = sb_take(&so);
    str_strip_ansi(text);
    str_trim(text);
    if (code != 0 || text[0] == '\0') {
        char tail[480];
        tail_text(se.s ? se.s : text, tail, sizeof tail);
        snprintf(err, errlen, "%s exited with status %d%s%s", cloud_name(id), code, tail[0] ? ": " : "",
                 tail[0] ? tail : (text[0] ? "" : " and produced no output"));
        free(text);
        rc = -1;
        goto fail;
    }
    sb_puts(out, text);
    free(text);
    sb_free(&se);
    return 0;
fail:
    sb_free(&so);
    sb_free(&se);
    return -1;
}

json *cloud_status_json(const config *c)
{
    json *o = json_new_obj();
    cloud_id ids[] = {CLOUD_CLAUDE, CLOUD_CODEX, CLOUD_GEMINI};
    for (size_t i = 0; i < sizeof ids / sizeof *ids; i++) {
        json *e = json_new_obj();
        const char *tmpl = cmd_for(c, ids[i]);
        json_set_str(e, "command", tmpl);
        argvec av;
        char err[256];
        int ok = argv_split(tmpl, &av, err, sizeof err) == 0;
        json_set_bool(e, "installed", ok && prog_on_path(av.argv[0]));
        if (ok) argv_free(&av);
        json_set(o, cloud_name(ids[i]), e);
    }
    json_set_num(o, "depth", cloud_depth());
    json_set_num(o, "max_depth", c->max_depth);
    return o;
}
