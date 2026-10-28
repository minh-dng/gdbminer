# Desktop mJS benchmark

Fetch the Cmimid benchmark source with the shared script from the repository root:

```sh
./fetch_example_programs.sh --mjs-source-only
```

This downloads `mjs.c`, `mjs.h` and `mjs_extra.h` from the same pinned Cmimid revision used by
Docker (`9c96909783ba99035372f78d6c52003f7f42b1ec`). The full fetch command also compiles the
desktop binary and prepares the other examples. The sources contain expanded glibc expressions;
build the desktop program on Linux/glibc or in the project's Docker environment:

```sh
clang -g -O0 -o example_programs/mjs/mjs example_programs/mjs/mjs.c
```

Cmimid's `mjs_exec_internal` returns immediately after `mjs_parse`; inputs are parsed, never
executed. The desktop file reader rejects a zero-length file and passes nonempty files as
NUL-terminated C strings, so embedded NUL truncates the parsed content.

The [ESP32-C3 target](../../example_firmware/esp32-c3_mjs/README.md) links to these same fetched
files and supplies the libc compatibility operations needed on the microcontroller.
