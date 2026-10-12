# Testing on hardware

These firmware examples run parsers on microcontrollers. GDBMiner sends inputs over a serial
connection, traces input reads through a debugger, and mines a grammar from the resulting traces.
Build and flash one target before running the tracing, mining and evaluation stages.

## Boards

| Board          | SoC       | Architecture    | Debug interface | Documentation              |
| -------------- | --------- | --------------- | --------------- | -------------------------- |
| B-L4S5I-IOT01A | STM32L4S5 | Arm Cortex-M4   | ST-Link/SWD     | [ST docs][stm32-board]     |
| DevKitM-1-N4X  | ESP32-C3  | 32-bit RISC-V   | USB Serial/JTAG | [Espressif docs][c3-board] |
| ESP32-S3-Zero  | ESP32-S3  | Xtensa LX7 (×2) | USB Serial/JTAG | [Waveshare docs][s3-board] |

The STM32 reference targets use the B-L4S5I-IOT01A Discovery kit, with an STM32L4S5 MCU
supporting a 120 MHz core clock.

The C3 board's Micro-USB port provides UART through a USB-to-UART bridge, **not JTAG**. The C3
workflow needs a USB connection wired to the native USB pins, for the debugger and, in the
one-cable setup, also for the inputs. Follow the [hardware setup][c3-setup] before connecting the
debugger.

The Waveshare ESP32-S3-Zero has no USB-to-UART bridge: its USB-C port is wired to the native USB
pins, so one cable carries both the debugger and the inputs. Follow the [S3 setup
guide][s3-setup].

## Parser targets

Each target includes firmware, seed inputs, an evaluation corpus and a TOML file in
`configuration/`: `configuration.toml` for STM32, `configuration.2-cables.toml` and
`configuration.1-cable.toml` for the C3 two-cable and one-cable setups, and
`configuration.1-watchpoint.toml` and `configuration.2-watchpoints.toml` for the S3 options. The C3
and S3 targets use the corresponding STM32 parser libraries and acceptance rules; build and
validation notes are documented in their READMEs. The S3 targets read the STM32 seeds and evaluation
corpora.

| Parser                        | STM32 reference              | ESP32-C3 port                | ESP32-S3 port                |
| ----------------------------- | ---------------------------- | ---------------------------- | ---------------------------- |
| JSON (`Arduino_JSON` / cJSON) | [stm32_arduinojson][st-json] | [esp32-c3_json][c3-json]     | [esp32-s3_json][s3-json]     |
| CGI (`percent_encode`)        | [stm32_cgidecode][st-cgi]    | [esp32-c3_cgidecode][c3-cgi] | [esp32-s3_cgidecode][s3-cgi] |
| XML (`LibYxml`)               | [stm32_libyxml][st-xml]      | [esp32-c3_xml][c3-xml]       | [esp32-s3_xml][s3-xml]       |

## Build and flash

First install GDBMiner's Python environment as described in the [repository README](../README.md).
Run the commands below from the repository root.

### STM32

Install [PlatformIO](https://platformio.org/), the ST-Link tools (`st-util`) and an Arm-compatible
GDB. The target's `platformio.ini` selects the Arduino framework, parser dependency and debug build
flags. For example, for the B-L4S5I-IOT01A:

```sh
TARGET=stm32_arduinojson
pio run --project-dir "example_firmware/$TARGET"
pio run --project-dir "example_firmware/$TARGET" --target upload
```

Set `[BASIC] binary_file` to the generated firmware ELF, `[Connection] port` to the board's serial
port, and `[GDB] gdb_path` to your Arm GDB. Check the `st-util` command and remote address in
`[GDB]`, and the DWT settings in `[GDB.stm32]`. The checked-in paths are examples, not portable
machine defaults. GDBMiner starts the configured debug server; do not start another server on the
same port.

### ESP32-C3

Follow the [C3 setup guide][c3-setup] for the Arduino CLI toolchain, dual USB connections,
Espressif GDB, OpenOCD and chip-revision-specific ROM symbols. Then follow the chosen target's
README to install its parser library, build and upload. The expected firmware ELF is
`example_firmware/<target>/build-1/<target>.ino.elf` for one cable and
`example_firmware/<target>/build-2/<target>.ino.elf` for two.

Use the target's existing watchpoint budget and trigger window as the starting point. The C3's
hardware breakpoints and read triggers share eight slots; assigning all eight to input reads is
not safe for every parser.

### ESP32-S3

Follow the [S3 setup guide][s3-setup] for the build options
(`CDCOnBoot=cdc,USBMode=hwcdc,LoopCore=0`), Espressif's Xtensa GDB, the OpenOCD options and the ROM
symbols. Then follow the chosen target's README. The expected firmware
ELF is `example_firmware/<target>/build/<target>.ino.elf`.

The S3 has two data breakpoints per core, separate from its two instruction breakpoints. One
watchpoint leaves the second to the firmware's stack guard; two watchpoints need about half the
runs. Two require `watchpoint_min_distance = 4`.

## Running GDBMiner on the firmware

Follow the root README's [trace and mine workflow](../README.md#run-local) and
[precision and recall workflow](../README.md#calculate-precision-and-recall), using `uv run`
and passing `--config` with the target's TOML file.
See the [configuration reference](../README.md#writing-up-configuration-tomls) for field meanings.

Before running:

- Update the target's TOML with your local paths and device identifiers.
- Ensure the flashed firmware and configured ELF come from the same build.
- Keep the board connected throughout tracing, mining and evaluation. The C3's two-cable setup
  needs both USB links.
- Run one stage at a time and release the serial port before starting the next; an interrupted
  run can leave a serial worker holding the port.
- Mine only after every seed has a trace. Mining selects the newest trial, including incomplete
  trials left by interrupted runs.
- Collect new traces after changing the firmware or tracing configuration. Consult the target
  README for recorded validation limits; a smoke run is not a complete evaluation.

[stm32-board]: https://www.st.com/en/evaluation-tools/b-l4s5i-iot01a.html#documentation
[upstream-stm32]: https://github.com/boschresearch/gdbminer/blob/15d6b592385a6ad22d1d84752b0a05a73d7afb6f/README.md#L140
[c3-board]: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
[c3-setup]: ESP32-C3%20DevKitM-1-N4X.md
[st-json]: stm32_arduinojson/
[st-cgi]: stm32_cgidecode/
[st-xml]: stm32_libyxml/
[c3-json]: esp32-c3_json/README.md
[c3-cgi]: esp32-c3_cgidecode/README.md
[c3-xml]: esp32-c3_xml/README.md
[s3-board]: https://docs.waveshare.com/ESP32-S3-zero
[s3-setup]: ESP32-S3-Zero.md
[s3-json]: esp32-s3_json/README.md
[s3-cgi]: esp32-s3_cgidecode/README.md
[s3-xml]: esp32-s3_xml/README.md
