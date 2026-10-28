// Host model of the firmware's answer to one input: loop()'s length check and parser() from
// src/main.cpp, linked with rust/lib.rs built for the host. Prints the result byte: 0 or 255.
// SPDX-License-Identifier: AGPL-3.0

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define FUZZ_INPUT_SIZE 2048

bool utf8_valid(const uint8_t *data, size_t length);
int jsonrs_parse(const uint8_t *data, size_t length);

// The library allocates through newlib's memalign on the board.
void *memalign(size_t alignment, size_t size) {
    void *ptr = NULL;
    if (alignment < sizeof(void *)) {
        alignment = sizeof(void *);
    }
    return posix_memalign(&ptr, alignment, size ? size : 1) == 0 ? ptr : NULL;
}

// The host's precompiled alloc crate refers to the unwinding personality. A panic aborts, as on the
// board, so it is never called.
void rust_eh_personality(void) { abort(); }

int main(int argc, char **argv) {
    static uint8_t buf[FUZZ_INPUT_SIZE + 2];
    if (argc != 2) {
        fprintf(stderr, "usage: %s FILE\n", argv[0]);
        return 2;
    }
    FILE *file = fopen(argv[1], "rb");
    if (!file) {
        perror(argv[1]);
        return 2;
    }
    // Read one byte more than the firmware takes, to see an oversized input.
    size_t length = fread(buf, 1, sizeof buf - 1, file);
    fclose(file);

    int res;
    if (length > FUZZ_INPUT_SIZE) {
        res = 0xff;
    } else if (!utf8_valid(buf, length)) {
        res = 0;
    } else {
        res = jsonrs_parse(buf, length);
    }
    printf("%d\n", (uint8_t)res);
    return 0;
}
