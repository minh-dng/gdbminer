# ESP32-S3 cgidecode target

Port of `example_firmware/stm32_cgidecode` for the paper replica (Eisele et al. 2025, Section 5.4)
on the Waveshare ESP32-S3-Zero. The parser is the reference `percent_encode` library, called through
the reference `parser()` acceptance rule: `percent::decode`, then reject if any decoded byte is
above 127. The TOML reads the seeds and the evaluation corpus from `stm32_cgidecode`.

## Firmware wrapper

`src/main.cpp` receives inputs over USB serial and reports parser results. The
[GPIO21 RGB LED](../ESP32-S3-Zero.md#status-led) shows input and parser status.

## Build and upload

Install the toolchain and build as in the [S3 setup guide](../ESP32-S3-Zero.md#arduino-build) with
`TARGET=esp32-s3_cgidecode`. Install and verify the parser library using the shared
[Arduino CLI CGI library setup](../Arduino-CLI.md#cgi).

The expected ELF is `build/esp32-s3_cgidecode.ino.elf`. A build on 2026-10-08 gave SHA-256
`5a32668b52eda4e50b145f66da87d2ccded837a9e7f6f0e00f56b929dcc926ae`. Its code and data sections are
byte-identical to the ELF of the recorded S3 runs (`31b93a18…`); only the build date and time in the
Arduino core's start-up banner differ. That historical hash predates the status-LED changes;
rebuild and flash the current firmware together with its matching ELF before tracing.

## Tracing

As in `stm32_cgidecode`, the entry point is `percent::decode` and nothing is skipped. No exit
breakpoint or `finish` is needed. `configuration.1-watchpoint.toml` watches one byte per run;
`configuration.2-watchpoints.toml` watches two, at least 4 bytes apart
(`watchpoint_min_distance = 4`). The method is in the [S3 setup
guide](../ESP32-S3-Zero.md#tracing-the-paper-replica-method).
