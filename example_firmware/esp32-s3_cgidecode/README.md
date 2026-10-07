# ESP32-S3 cgidecode target

Port of `example_firmware/stm32_cgidecode` for the paper replica (Eisele et al. 2025, Section 5.4)
on the Waveshare ESP32-S3-Zero. The parser is the reference `percent_encode` library, called through
the reference `parser()` acceptance rule: `percent::decode`, then reject if any decoded byte is
above 127. The TOML reads the seeds and the evaluation corpus from `stm32_cgidecode`.

## Differences from the C3 port

`src/main.cpp` is the [C3 port](../esp32-c3_cgidecode/README.md), with its changes to the STM32
wrapper, and one [S3 change](../ESP32-S3-Zero.md#firmware-wrappers): the LED toggle uses GPIO21.

## Build and upload

Install the toolchain and build as in the [S3 setup guide](../ESP32-S3-Zero.md#arduino-build) with
`TARGET=esp32-s3_cgidecode`. Install the library at the base version that
`stm32_cgidecode/platformio.ini` declares (`^2.0.1`):

```sh
arduino-cli lib install 'percent_encode@2.0.1'
arduino-cli lib list
```

The expected ELF is `build/esp32-s3_cgidecode.ino.elf`. A build on 2026-10-08 gave SHA-256
`5a32668b52eda4e50b145f66da87d2ccded837a9e7f6f0e00f56b929dcc926ae`. Its code and data sections are
byte-identical to the ELF of the recorded S3 runs (`31b93a18…`); only the build date and time in the
Arduino core's start-up banner differ.

## Tracing

As in `stm32_cgidecode`, the entry point is `percent::decode` and nothing is skipped. Two read
watchpoints per run, at least 4 bytes apart (`watchpoint_min_distance = 4`). No exit breakpoint or
`finish` is needed. The method is in the [S3 setup
guide](../ESP32-S3-Zero.md#tracing-the-paper-replica-method).
