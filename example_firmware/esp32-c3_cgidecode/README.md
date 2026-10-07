# ESP32-C3 cgidecode target

Port of `example_firmware/stm32_cgidecode` for the paper replica (Eisele et al. 2025, Section 5.4).
The parser is the reference `percent_encode` library, called through the reference `parser()`
acceptance rule: `percent::decode`, then reject if any decoded byte is above 127. Seeds and the
evaluation corpus are byte-identical to the STM32 copies.

This replaces an earlier custom diagnostic parser (115,200 baud, 128-byte buffer, `0xa5` ready byte,
toolchain stubs). That project is archived under
`/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-paper-replica-2026-09-30/before/`.

## Differences from the STM32 wrapper

`diff ../stm32_cgidecode/src/main.cpp src/main.cpp` shows the [changes shared by all C3
ports](../ESP32-C3%20DevKitM-1-N4X.md#firmware-wrappers). The decoded-output array also has
an extra byte for its terminating NUL. Without it, a 2,048-byte input with no percent escapes writes
one byte past the stack array. This correction was made after the recorded September 30 run; that
run's ELF and results remain historical evidence. Rebuild and validate the new ELF before collecting
new traces.

Reference behaviour kept as is: `percent::decode` on a trailing `%` reads past the terminating NUL,
into bytes left from earlier inputs. The STM32 reference does the same.

## Build and upload

Install the toolchain and build as in the [C3 setup
README](../ESP32-C3%20DevKitM-1-N4X.md#arduino-build) with `TARGET=esp32-c3_cgidecode`.
Install the library at the base version that `stm32_cgidecode/platformio.ini` declares (`^2.0.1`):

```sh
arduino-cli lib install 'percent_encode@2.0.1'
arduino-cli lib list
```

The expected ELF is `build/esp32-c3_cgidecode.ino.elf`.

## Tracing

As in `stm32_cgidecode`, the entry point is `percent::decode` and nothing is skipped.
`percent::decode` calls only the library's `indexOf`. After the temporary entry breakpoint fires,
all eight slots observe input bytes. No exit breakpoint or `finish` needs a slot while the parser is
traced. The method is in the [C3 setup
README](../ESP32-C3%20DevKitM-1-N4X.md#tracing-the-paper-replica-method).
