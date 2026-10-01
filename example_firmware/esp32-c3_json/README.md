# ESP32-C3 Arduino_JSON target

Hardware links, firmware wrappers, the Arduino build, the debugger and the tracing method are shared
by all C3 targets. See the [C3 setup README](../ESP32-C3%20DevKitM-1-N4X.md). This page
covers what is specific to json.

The parser remains `Arduino_JSON@0.2.0`. The source in `src/main.cpp`, seeds and evaluation corpus
are unchanged by this build migration. The empty `.ino` file lets Arduino CLI build that existing
C++ source without rewriting it. Compared with `stm32_arduinojson`, the wrapper has the [changes
shared by all C3 ports](../ESP32-C3%20DevKitM-1-N4X.md#firmware-wrappers) and also drops the
unused `input_len` variable and some redundant casts.

## Install the library

After the [toolchain](../ESP32-C3%20DevKitM-1-N4X.md#toolchain) is installed:

```sh
arduino-cli lib install 'Arduino_JSON@0.2.0'
arduino-cli lib list
```

Confirm library 0.2.0 before building.

## Build and upload

Build and flash as in [Build and upload](../ESP32-C3%20DevKitM-1-N4X.md#build-and-upload)
with `TARGET=esp32-c3_json`. The expected ELF is `build/esp32-c3_json.ino.elf`.

## Tracing

`configuration/configuration.2-cables.toml` follows `stm32_arduinojson`: same entry point
(`cJSON_Parse`) and the same `ignore_functions_regex`, skipped with GDB `finish`; `__aeabi_dadd` is
written as `__adddf3`. Six watchpoints use slots 2-7, and slots 0-1 stay free for `finish`. The
TOML selects Espressif's bundled GDB, not Homebrew's
([why](../ESP32-C3%20DevKitM-1-N4X.md#choosing-the-debugger)). The method and the slot layout
of all three targets are in the [C3 setup
README](../ESP32-C3%20DevKitM-1-N4X.md#tracing-the-paper-replica-method).

## Validation and evidence

A successful link without compatibility stubs is only the first gate. Then check the serial
acceptance oracle, complete hardware traces, watchpoint-window consistency, mining and evaluation.
Do not reuse traces from an older ELF.

The matched build compiled and flashed successfully, using Espressif GCC 14.2.0_20260121. All ten
serial oracle checks passed, including the 2,048-byte capacity, oversized rejection and the
following packet. The wrapper source is byte-identical to the archived version. No
compatibility-stub source is compiled.

Current ELF SHA-256:

```text
f6cf61b78578edf6b69a4dd9b6aae29597064bbae64e6620f38a29cd6947bd8e
```

Migration evidence is kept under:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-official-arduino-2026-09-29/
```

The previous complete project is archived there as `before/esp32-c3_json.tgz`. The older full-corpus
tracing run stopped on another runtime stack failure; its successful one-seed smoke evaluation was
not a full-corpus result.
