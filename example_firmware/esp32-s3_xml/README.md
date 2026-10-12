# ESP32-S3 xml target

Port of `example_firmware/stm32_libyxml` for the paper replica (Eisele et al. 2025, Section 5.4) on
the Waveshare ESP32-S3-Zero. The parser is the reference `LibYxml` library, called through the
unchanged `parser()` wrapper: `yxml_parse` per byte, reject on the first negative return. The TOML
reads the seeds and the evaluation corpus from `stm32_libyxml`.

## Layout and line numbers

The wrapper is in `main.ino`, and the comment-only `esp32-s3_xml.ino` is the sketch entry that
Arduino CLI requires. Lines 1-54 keep their numbers, so `main.ino:46` (the `for` loop)
and `main.ino:53` (`return ret_val`) are the STM32 entry and exit points.

## Firmware wrapper

`main.ino` receives inputs over USB serial and reports parser results. The
[GPIO21 RGB LED](../ESP32-S3-Zero.md#status-led) shows input and parser status. LED writes stay
outside the parser and preserve its source-line breakpoints.

## Build and upload

Install the toolchain and build as in the [S3 setup guide](../ESP32-S3-Zero.md#arduino-build) with
`TARGET=esp32-s3_xml`. Install the library at the base version that `stm32_libyxml/platformio.ini`
declares (`^1.0.2`):

```sh
arduino-cli lib install 'LibYxml@1.0.2'
arduino-cli lib list
```

The expected ELF is `build/esp32-s3_xml.ino.elf`. A build on 2026-10-08 gave SHA-256
`290bdb582a895c58730a095f448870b860abd5fc7d643ef1c7adf94b2be351e9`. Its code and data sections are
byte-identical to the ELF of the recorded S3 runs (`72d23117…`); only the build date and time in the
Arduino core's start-up banner differ. That historical hash predates the status-LED changes;
rebuild and flash the current firmware together with its matching ELF before tracing.

## Tracing

The ignore list is the STM32 one, with `__aeabi_dadd` written as its libgcc name `__adddf3`.
`yxml_parse` reaches only LibYxml functions, so no `finish` occurs in practice. The exit breakpoint
takes one of the two instruction breakpoints. `configuration.1-watchpoint.toml` observes one input
byte per run with DBREAK0; `configuration.2-watchpoints.toml` observes two with both DBREAKs. The
method is in the [S3 setup guide](../ESP32-S3-Zero.md#tracing-the-paper-replica-method).
