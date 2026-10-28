// Use the desktop Cmimid benchmark, including its parse-only mjs_exec modification.
// SPDX-License-Identifier: GPL-2.0-only

#include "cmimid_compat.h"

// A header symlink lets Arduino copy the source without compiling it a second time.
#define main cmimid_desktop_main
#include "mjs_source.h"
#undef main

int parser(const char *input, size_t length) {
    // The desktop file reader rejects an empty file, but accepts a nonempty file starting in NUL.
    if (length == 0) return -1;
#ifndef __GLIBC__
    // Initialize before mjs_parse so lazy libc setup cannot enter the instruction trace.
    (void)cmimid_ctype_b_loc();
#endif
    struct mjs *mjs = mjs_create();
    mjs_val_t value = MJS_UNDEFINED;
    mjs_err_t result = mjs_exec(mjs, input, &value);
    mjs_destroy(mjs);
    return result == MJS_OK ? 0 : -1;
}
