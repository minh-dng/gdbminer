// Restore the libc operations already expanded in Cmimid's benchmark source.
// SPDX-License-Identifier: GPL-2.0-only

#pragma once

#include <ctype.h>
#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

// The benchmark's expanded glibc expressions use these little-endian classification masks.
enum {
    CMIMID_ISALNUM = 0x0008,
    CMIMID_ISXDIGIT = 0x1000,
    CMIMID_ISSPACE = 0x2000,
    CMIMID_ISPRINT = 0x4000,
};

static inline const unsigned short **cmimid_ctype_b_loc(void) {
    // glibc permits signed-char indices -128..-2, unsigned bytes 0..255, and EOF (-1).
    static unsigned short table[384];
    static const unsigned short *base = table + 128;
    static int initialized;
    if (!initialized) {
        for (int c = -128; c < 256; ++c) {
            unsigned char byte = (unsigned char)c;
            if (c != EOF) {
                table[c + 128] = (isalnum(byte) ? CMIMID_ISALNUM : 0)
                    | (isxdigit(byte) ? CMIMID_ISXDIGIT : 0)
                    | (isspace(byte) ? CMIMID_ISSPACE : 0)
                    | (isprint(byte) ? CMIMID_ISPRINT : 0);
            }
        }
        initialized = 1;
    }
    return &base;
}

static inline _Noreturn void cmimid_assert_fail(
    const char *expression, const char *file, unsigned line, const char *function
) {
    // Expanded benchmark assertions must still abort, including builds with NDEBUG.
    fprintf(stderr, "%s:%u: %s: Assertion `%s' failed.\n", file, line, function, expression);
    abort();
}

#ifndef __GLIBC__
#define _ISalnum CMIMID_ISALNUM
#define _ISxdigit CMIMID_ISXDIGIT
#define _ISspace CMIMID_ISSPACE
#define _ISprint CMIMID_ISPRINT
#define __ctype_b_loc cmimid_ctype_b_loc
#define __assert_fail cmimid_assert_fail
#define __isnan isnan
#define __isnanf isnan
#define __isnanl isnan
#endif
