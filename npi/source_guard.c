#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

/* Refuse RTL source reads even if the EDA runtime tries an implicit fallback. */
static int blocked(const char *p) {
    if (!p) return 0;
    const char *ext = strrchr(p, '.');
    if (!ext) return 0;
    if (strcasecmp(ext, ".v") && strcasecmp(ext, ".sv") && strcasecmp(ext, ".vh") &&
        strcasecmp(ext, ".svh") && strcasecmp(ext, ".vhd") && strcasecmp(ext, ".vhdl")) return 0;
    const char *msg = "RTLWIRE_SOURCE_BLOCKED: ";
    write(2, msg, strlen(msg)); write(2, p, strlen(p)); write(2, "\n", 1);
    errno = EACCES;
    return 1;
}

#define OPEN_WRAP(NAME) \
int NAME(const char *p, int flags, ...) { \
    static int (*next)(const char *, int, ...) = NULL; \
    if (!next) next = dlsym(RTLD_NEXT, #NAME); \
    if (blocked(p)) return -1; \
    mode_t mode = 0; \
    if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap); } \
    return next(p, flags, mode); \
}
OPEN_WRAP(open)
OPEN_WRAP(open64)

#define OPENAT_WRAP(NAME) \
int NAME(int fd, const char *p, int flags, ...) { \
    static int (*next)(int, const char *, int, ...) = NULL; \
    if (!next) next = dlsym(RTLD_NEXT, #NAME); \
    if (blocked(p)) return -1; \
    mode_t mode = 0; \
    if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = va_arg(ap, int); va_end(ap); } \
    return next(fd, p, flags, mode); \
}
OPENAT_WRAP(openat)
OPENAT_WRAP(openat64)

#define FOPEN_WRAP(NAME) \
FILE *NAME(const char *p, const char *mode) { \
    static FILE *(*next)(const char *, const char *) = NULL; \
    if (!next) next = dlsym(RTLD_NEXT, #NAME); \
    if (blocked(p)) return NULL; \
    return next(p, mode); \
}
FOPEN_WRAP(fopen)
FOPEN_WRAP(fopen64)

/* Fortified glibc entry points used by builds with _FORTIFY_SOURCE. */
int __open_2(const char *p, int flags) { return open(p, flags); }
int __open64_2(const char *p, int flags) { return open64(p, flags); }
int __openat_2(int fd, const char *p, int flags) { return openat(fd, p, flags); }
int __openat64_2(int fd, const char *p, int flags) { return openat64(fd, p, flags); }

#define FREOPEN_WRAP(NAME) \
FILE *NAME(const char *p, const char *mode, FILE *stream) { \
    static FILE *(*next)(const char *, const char *, FILE *) = NULL; \
    if (!next) next = dlsym(RTLD_NEXT, #NAME); \
    if (blocked(p)) return NULL; \
    return next(p, mode, stream); \
}
FREOPEN_WRAP(freopen)
FREOPEN_WRAP(freopen64)
