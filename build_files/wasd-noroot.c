#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* umu refuses euid 0. The games mount runs in a user namespace whose root
   is this account, so umu is shown that account's id. Wine keeps the
   namespace id, which is the owner of the prefix.
   A native launcher sets WASD_SPOOF_UID=1. Java takes its home directory
   from getuid, and that home is /root while the namespace id is 0.
   Bubblewrap refuses to start when a process that is not root still has
   the namespace's capabilities. It keeps the namespace id. The marker
   below is how a checkout finds this copy. */
static const char wasd_noroot_keeps_bwrap[] __attribute__((used)) = "wasd-noroot-keeps-bwrap";

static int umu_process(void)
{
    char buf[4096];
    FILE *file;
    size_t got;

    file = fopen("/proc/self/cmdline", "rb");
    if (!file)
        return 0;
    got = fread(buf, 1, sizeof buf, file);
    fclose(file);
    if (memmem(buf, got, "umu-run", 7) || memmem(buf, got, "/umu/", 5))
        return 1;
    return 0;
}

static int spoof_all(void)
{
    const char *flag = getenv("WASD_SPOOF_UID");

    return flag && flag[0] == '1' && flag[1] == '\0';
}

static int is_bubblewrap(void)
{
    char path[4096];
    ssize_t got;
    const char *base;
    size_t len;

    got = readlink("/proc/self/exe", path, sizeof path - 1);
    if (got <= 0 || (size_t)got >= sizeof path)
        return 0;
    path[got] = '\0';
    base = strrchr(path, '/');
    base = base ? base + 1 : path;
    len = strlen(base);
    if ((len == 5 && memcmp(base, "bwrap", 5) == 0) ||
        (len == 9 && memcmp(base, "srt-bwrap", 9) == 0))
        return 1;
    return 0;
}

static uid_t shown(uid_t (*real)(void))
{
    const char *text = getenv("WASD_EUID");
    char *end = 0;
    unsigned long value;

    if (!real)
        return 0;
    /* A path under the umu directory is still bubblewrap. Spoofing its
       id makes the games-folder namespace look like a broken setuid install. */
    if (is_bubblewrap() || !text || !*text)
        return real();
    if (!spoof_all() && !umu_process())
        return real();
    value = strtoul(text, &end, 10);
    if (!end || *end || value == 0)
        return real();
    return (uid_t)value;
}

uid_t getuid(void)
{
    static uid_t (*real)(void);
    if (!real)
        real = dlsym(RTLD_NEXT, "getuid");
    return shown(real);
}

uid_t geteuid(void)
{
    static uid_t (*real)(void);
    if (!real)
        real = dlsym(RTLD_NEXT, "geteuid");
    return shown(real);
}
