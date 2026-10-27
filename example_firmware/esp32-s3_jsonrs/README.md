# ESP32-S3 jsonrs target

This target runs the paper's desktop Rust parser, [`json.rs`](../../example_programs/jsonrs/json.rs)
(tinyjson 2.5.1), on the Waveshare ESP32-S3-Zero with the corpora that the desktop jsonrs
configuration names (`example_programs/json/{seeds,eval}`). It uses the serial protocol and the status LED of [esp32-s3_json](../esp32-s3_json/README.md).
The Rust library is the one of the [C3 target](../esp32-c3_jsonrs/README.md#how-the-parser-gets-onto-the-board):
`rust/lib.rs` is a symlink to its source.

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
  --build-property "build.extra_libs=$PWD/example_firmware/esp32-s3_jsonrs/build-rust/xtensa-esp32s3-none-elf/debug/libjsonrs.a"
```

The expected ELF is `build/esp32-s3_jsonrs.ino.elf`.

## Tracing

Both configurations follow `esp32-s3_json`, with the entry point `jsonrs_parse` and the C3 target's
[extended `ignore_functions_regex`](../esp32-c3_jsonrs/README.md#tracing). Each `finish` takes one
instruction breakpoint. As in the C3 target, the watch expression is the desktop's `&data[3]`
(`input_buffer = "data"`, `watchpoint_type = ""`), which parses in the Rust frame.
