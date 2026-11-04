#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* umu refuses euid 0. The games mount runs in a user namespace whose root
   is this account, so umu is shown that account's id. Wine keeps the
   namespace id, which is the owner of the prefix. */

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

static uid_t shown(uid_t (*real)(void))
{
    const char *text = getenv("WASD_EUID");
    char *end = 0;
    unsigned long value;

    if (!real)
        return 0;
    if (!umu_process() || !text || !*text)
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
