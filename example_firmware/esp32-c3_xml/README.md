# ESP32-C3 xml target

Port of `example_firmware/stm32_libyxml` for the paper replica (Eisele et al. 2025, Section 5.4). The parser is the
reference `LibYxml` library, called through the unchanged `parser()` wrapper: `yxml_parse` per byte, reject on the
first negative return. Seeds and the evaluation corpus are byte-identical to the STM32 copies.

This replaces an earlier adapter (115,200 baud, 128-byte buffer, `0xa5` ready byte, toolchain stubs). That project
is archived under `/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-paper-replica-2026-09-30/before/`.

## Layout and line numbers

The STM32 configuration traces from `main.ino:46` to `main.ino:53`, so the wrapper stays in `main.ino`. The
comment-only `esp32-c3_xml.ino` is the sketch entry that Arduino CLI requires; it concatenates both files with
`#line` directives, so GDB resolves `main.ino:46` to the `for` loop and `main.ino:53` to `return ret_val` in
`parser()`. Every change in lines 1-54 is made on its original line.

## Differences from the STM32 wrapper

`diff ../stm32_libyxml/src/main.ino main.ino` shows only the
[changes shared by all C3 ports](../ESP32-C3%20DevKitM-1-N4X.README.md#firmware-wrappers).

## Build and upload

Install the toolchain and build as in the [C3 setup README](../ESP32-C3%20DevKitM-1-N4X.README.md#arduino-build) with
`TARGET=esp32-c3_xml`. Install the library at the base version that `stm32_libyxml/platformio.ini` declares
(`^1.0.2`):

```sh
arduino-cli lib install 'LibYxml@1.0.2'
arduino-cli lib list
```

The expected ELF is `build/esp32-c3_xml.ino.elf`.

## Tracing

The ignore list is the STM32 one, with `__aeabi_dadd` written as its libgcc name `__adddf3`. `yxml_parse` reaches
only LibYxml functions, so no `finish` occurs in practice. The exit breakpoint needs one trigger slot; slots 1-7
observe input bytes. The method is in the
[C3 setup README](../ESP32-C3%20DevKitM-1-N4X.README.md#tracing-the-paper-replica-method).
