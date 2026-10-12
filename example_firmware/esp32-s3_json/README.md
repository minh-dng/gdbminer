# ESP32-S3 Arduino_JSON target

Port of `example_firmware/stm32_arduinojson` for the paper replica (Eisele et al. 2025, Section 5.4)
on the Waveshare ESP32-S3-Zero. The parser is `Arduino_JSON@0.2.0`. The TOML reads the seeds and the
evaluation corpus from `stm32_arduinojson`. The empty `.ino` file lets Arduino CLI build the C++
source in `src/main.cpp` without rewriting it.

## Firmware wrapper

`src/main.cpp` receives inputs over USB serial and reports parser results. The
[GPIO21 RGB LED](../ESP32-S3-Zero.md#status-led) shows input and parser status.

## Build and upload

Install the toolchain and build as in the [S3 setup guide](../ESP32-S3-Zero.md#arduino-build) with
`TARGET=esp32-s3_json`. Install the library at the base version that
`stm32_arduinojson/platformio.ini` declares (`^0.2.0`):

```sh
arduino-cli lib install 'Arduino_JSON@0.2.0'
arduino-cli lib list
```

The expected ELF is `build/esp32-s3_json.ino.elf`. A build on 2026-10-08 gave SHA-256
`29ea3fa3d804422cf68f0b74d3b1f2cb31303283538b92782e13d059d5cdac65`. Its code and data sections are
byte-identical to the ELF of the recorded S3 runs (`ed65ad67…`); only the build date and time in the
Arduino core's start-up banner differ. That historical hash predates the status-LED changes;
rebuild and flash the current firmware together with its matching ELF before tracing.

## Tracing

Both configurations (`configuration.1-watchpoint.toml`, `configuration.2-watchpoints.toml`) follow
`stm32_arduinojson`: same entry point (`cJSON_Parse`) and the same `ignore_functions_regex`, skipped
with GDB `finish`; `__aeabi_dadd` is written as `__adddf3`. `strlen` and `memset` run from mask ROM
and are reached through ROM jump stubs, which the adapter follows to the routine's `ENTRY`. Each
`finish` takes one instruction breakpoint: the ELF has no `_Unwind_DebugHook`. The method is in the
[S3 setup guide](../ESP32-S3-Zero.md#tracing-the-paper-replica-method).