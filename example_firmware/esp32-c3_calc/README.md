# ESP32-C3 calc target

This target uses the paper's desktop [calc parser](../../example_programs/calc/), its 20 seeds and
1,000 evaluation inputs. It uses the same serial protocol as the C3 JSON target. Over native USB,
calc skips `Serial.flush()` because `HWCDC::flush` can discard a queued ready byte
(issue [#60](https://github.com/minh-dng/gdbminer/issues/60)). UART builds keep the flush.

## Prepare the parser

We are compiling from source, where `src/calc.c` is a symlink to the desktop
`example_programs/calc/calc.c`. Make sure to run `fetch_example_programs.sh` before hand to also
apply the intended patch by M. Eisele.

The desktop `main()` reads a file; the firmware never calls it, and the linker discards it.
`parser()` in `src/main.cpp` does the rest of the desktop `main()`: reject empty input (the desktop
exits with status 3), call the desktop `strip_input()`, establish `setjmp`, call
`rdp_parse_expression` and convert `longjmp` to rejection.

## Nesting limit

The parser is recursive. Each `(` adds four calls, `parse_primary`, `parse_expr`, `parse_sum` and
`parse_mult`, and at `-O0` each uses a 48-byte stack frame. The wrapper sets the stack of Arduino's
loop task, which runs the parser, to 32 KiB with `SET_LOOP_TASK_STACK_SIZE`. Both builds answer
like the desktop up to 168 levels of nesting. At 169 levels the stack overflows: the board reports
a stack protection fault and restarts without an answer. The default 8 KiB stack held 40 levels
(issue [#63](https://github.com/minh-dng/gdbminer/issues/63)).

GDBMiner stays far below the limit. The 70,185 calc mining queries recorded on 2026-10-20 nest at
most 6 levels, and the seeds and evaluation inputs at most 3. No stack size removes the limit: a
2,048-byte input can nest 2,048 levels, which would need more than 384 KiB, nearly all of the C3's
400 KiB of SRAM. The wrapper does not check the depth itself, because it would then reject valid
inputs that the desktop accepts.

## Build and upload

Follow the shared [Arduino CLI toolchain setup](../Arduino-CLI.md#toolchain) and
[C3 build and upload guide](../ESP32-C3%20DevKitM-1-N4X.md#build-and-upload), using
`TARGET=esp32-c3_calc`. Create `calc.c` first. No `arduino-cli lib install` is required.

The expected ELF is `build-2/esp32-c3_calc.ino.elf` for UART/two cables and
`build-1/esp32-c3_calc.ino.elf` for native USB/one cable. Build both with `-O0 -g3 -ggdb3` as in
the shared guide. Flash only the build matching the selected configuration.

## Prepare debugger symbols

After installing the Arduino toolchain and the chip-revision-specific ROM symbols from the shared
C3 guide, run:

```sh
example_firmware/esp32-c3_calc/prepare_debug.sh
```

The pinned v1.1 ROM symbol file lacks unwind information. At ROM `strtol`'s tail-call epilogue,
GDB misreads the restored stack pointer and loses the parser's caller chain. The script adds
debugger-only `.debug_frame` metadata from `configuration/strtol-unwind.S` to a copy of those
symbols in `build/debug/esp32c3_rev101_rom.elf`. Both TOMLs load that copy. Firmware still calls
ROM `strtol`; no parser substitution, skipped instruction or target instrumentation is needed.

The script rejects a ROM file with a different SHA-256, checks that the copy has the same symbols,
and checks the generated unwind range. It uses the Espressif assembler, linker, objcopy, nm and
readelf installed with the Arduino core, found through `arduino-cli`. Set `ROM_ELF` or
`TOOLCHAIN_BIN` to use other locations.

## Tracing

Run the three stages as in the C3 guide's
[Running the evaluation](../ESP32-C3%20DevKitM-1-N4X.md#running-the-evaluation), with
`TARGET=esp32-c3_calc`. Both configurations use the desktop calc corpora directly and write to
separate output bases.

Tracing starts at `rdp_parse_expression` and watches the original global `buf`. Nothing is
skipped, including `strtol`, which consumes the input digits. Eight read triggers occupy slots
0-7, as in CGI; no `finish` or explicit exit breakpoint is configured. The recorded smoke traces
cover every input byte, including digits inside ROM `_strtol_l.isra.0`, and merge consistently
across two windows.
