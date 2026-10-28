# ESP32-S3 jsonrs target

This target runs the paper's desktop Rust parser, [`json.rs`](../../example_programs/jsonrs/json.rs)
(tinyjson 2.5.1), on the Waveshare ESP32-S3-Zero with the corpora that the desktop jsonrs
configuration names (`example_programs/json/{seeds,eval}`). It uses the serial protocol and the
status LED of [esp32-s3_json](../esp32-s3_json/README.md). The Rust library is the one of the
[C3 target](../esp32-c3_jsonrs/README.md#how-the-parser-gets-onto-the-board): `rust/lib.rs` is a
symlink to its source.

## Build the parser

The S3 is Xtensa, so the library needs Espressif's Rust fork. Install it once as described in
[Rust parsers](../README.md#rust-parsers-jsonrs), then build from the repository root:

```sh
(cd example_firmware/esp32-s3_jsonrs/rust && cargo +esp rustc --target-dir ../build-rust)
```

Run it from the `rust/` directory: Cargo reads `.cargo/config.toml` from the working directory. The
first build downloads the crates that `core`'s source tree needs (`build-std`).

The library is `build-rust/xtensa-esp32s3-none-elf/debug/libjsonrs.a`. The configuration in
`rust/.cargo/config.toml` builds `core` and `alloc` from source, at `opt-level = 0` with debug
information and `panic = "abort"`.

## Build and upload

Follow the [S3 setup guide](../ESP32-S3-Zero.md#arduino-build) with `TARGET=esp32-s3_jsonrs` and add
this property to the `compile` command, so the linker takes the library inside its group:

```sh
LIB=$PWD/example_firmware/esp32-s3_jsonrs/build-rust/xtensa-esp32s3-none-elf/debug/libjsonrs.a
  --build-property "build.extra_libs=$LIB"
```

The expected ELF is `build/esp32-s3_jsonrs.ino.elf`.

## Tracing

Both configurations follow `esp32-s3_json`, with the entry point `jsonrs_parse` and the C3 target's
[extended `ignore_functions_regex`](../esp32-c3_jsonrs/README.md#tracing). Each `finish` takes one
instruction breakpoint. As in the C3 target, the watch expression is the desktop's `&data[3]`
(`input_buffer = "data"`, `watchpoint_type = ""`), which parses in the Rust frame.

## Runtime routines

As in the [C3 target](../esp32-c3_jsonrs/README.md#runtime-routines), none of the library's
`compiler_builtins` code reaches the firmware. The map pulls 16 `compiler_builtins` members, for
`strlen`, `__extendhfsf2`, `__truncsfhf2` and references between the members, and every symbol
they define is weak. `memcpy`, `memset`, `memmove`, `memcmp`, `strlen` and the libgcc helpers
resolve to ROM addresses (`esp32s3.rom.libc.ld`, `esp32s3.rom.libgcc.ld`), `--gc-sections`
discards all `compiler_builtins` code sections, and the ELF has no `compiler_builtins` symbol:

```sh
xtensa-esp32s3-elf-nm -C example_firmware/esp32-s3_jsonrs/build/esp32-s3_jsonrs.ino.elf |
  grep -c compiler_builtins  # 0
```

## Stack depth

The recursion is the one described for the [C3](../esp32-c3_jsonrs/README.md#stack-depth). The
Xtensa frames, from each function's `entry a1, N`:

| Frames | Bytes |
| --- | ---: |
| Loop task to the first `parse_any` (`vPortTaskWrapper`, `loopTask`, `loop`, `parser`, `jsonrs_parse`, `from_str`, `parse`, `parse_any`) | 912 |
| One array level (`parse_array` + `parse_any`) | 992 |
| One object level (`parse_object` + `parse_any`) | 1,264 |

Measured on an S3-Zero without a debugger on 2026-10-29, with `scripts/esp32_jsonrs_oracle.py
depth` and inputs of the form `[[0]]` and `{"":{"":0}}`:

| Input | Deepest nesting answered | First nesting that restarts the chip |
| --- | ---: | ---: |
| Arrays | 29 | 30 |
| Objects | 23 | 24 |

The 32 KiB loop-task stack therefore holds 29 array levels: 912 + 29 × 992 = 29,680 bytes of
parser frames, and the innermost `parse_number` with `core`'s float parser needs the rest. At 30
levels the chip prints `Stack canary watchpoint triggered (loopTask)`
(`CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK`) and restarts. The backtrace steps 0x3e0 = 992 bytes per
array level, as the table predicts. The host sees the restart as described for the C3: the run
stops, and no rejection is recorded. Built for the host, the desktop `json.rs` accepts all these
inputs.

```sh
uv run scripts/esp32_jsonrs_oracle.py depth --kind array \
  --config example_firmware/esp32-s3_jsonrs/configuration/configuration.2-watchpoints.toml \
  --port PORT
```

## Oracle check

On 2026-10-29 the S3-Zero, without a debugger, gave the desktop's verdict on every corpus input:
20 of 20 seeds and 993 of 1,000 eval inputs accepted, none different. The setup and the seven
rejected inputs are described for the [C3](../esp32-c3_jsonrs/README.md#oracle-check); the command
for the S3 is:

```sh
B=example_firmware/esp32-c3_jsonrs/build/host
uv run scripts/esp32_jsonrs_oracle.py corpus --desktop $B/jsonrs \
  --config example_firmware/esp32-s3_jsonrs/configuration/configuration.2-watchpoints.toml \
  --port PORT example_programs/json/seeds example_programs/json/eval
```
