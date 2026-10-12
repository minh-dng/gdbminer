# Setting up the Waveshare ESP32-S3-Zero

This guide covers the ESP32-S3-Zero hardware, the firmware wrappers, the Arduino build, the debugger
and the tracing method shared by the three S3 targets (`esp32-s3_cgidecode`, `esp32-s3_json`,
`esp32-s3_xml`). Each target README adds what is specific to it.

The S3-Zero uses **one USB-C cable**. The cable carries both the inputs
(`input_channel = "esp32-usb-serial-jtag"`) and the debugger, through the chip's built-in
USB-Serial/JTAG peripheral. The board has no USB-to-UART bridge.

Each target has two configurations, one per watchpoint count. Both use the same build and
the same firmware; they differ in the data breakpoints that GDBMiner takes from the firmware.

| Option                | TOML file                          | Data breakpoints     | Runs per seed of n bytes     |
| --------------------- | ---------------------------------- | -------------------- | ---------------------------- |
| One watchpoint (conservative) | `configuration.1-watchpoint.toml`  | DBREAK0              | n                            |
| Two watchpoints       | `configuration.2-watchpoints.toml` | DBREAK0 and DBREAK1  | max(ceil(n / 2), min(n, 4)) |

DBREAK1 is also the firmware's FreeRTOS stack guard ([details](#tracing-the-paper-replica-method)).
One watchpoint leaves it to the firmware and is the conservative choice. Two watchpoints share it:
the backend checks both pairs after every recorded step and stops on unexpected changes. The
[historical JSON comparison](#recorded-results) matched all 20 seeds by address, function, stack
and read set. Two watchpoints needed 102 passes instead of 168. Five- and six-byte seeds each need
four passes; seeds of one to four bytes need n passes.
Each option writes to its own `output/<target>-1-watchpoint/` or `output/<target>-2-watchpoints/`,
so a trial never mixes the two.

## Hardware

The board is the [Waveshare ESP32-S3-Zero][waveshare]: an ESP32-S3FH4R2 (dual-core Xtensa LX7,
4 MB flash and 2 MB PSRAM in the package), a WS2812 RGB LED on GPIO21, BOOT (GPIO0) and RESET
buttons, and a USB-C port wired to the chip's native USB pins (GPIO19 and GPIO20). Waveshare's N8R8
variant has more flash and PSRAM; it was not tested.

The native USB pins carry the USB-Serial/JTAG peripheral. It is one USB device with two functions,
used at the same time:

| Function | Mac side                                             | Used for                           | Configured in                              |
| -------- | ---------------------------------------------------- | ---------------------------------- | ------------------------------------------ |
| CDC-ACM  | `/dev/cu.usbmodem<n>` ("USB JTAG_serial debug unit") | Flashing, each input and its answer | `[Connection] port`                        |
| JTAG     | No `/dev` path; OpenOCD finds it over USB            | OpenOCD and GDB                    | `[GDB] gdb_server_path` (`--adapter-serial`) |

No external JTAG probe is needed, and one would not help: the number of breakpoints and
watchpoints belongs to the CPU's debug unit, not to the probe (see
[Debug resources](#debug-resources-per-core)).

The pads TX (GPIO43) and RX (GPIO44) are UART0. An external USB-to-UART adapter there could carry
the inputs over the `esp32-uart` channel. That setup was not built or tested.

### Finding the identifiers

The port name depends on the Mac's USB socket (`ls /dev/cu.usbmodem*`). The USB vendor and product
ID is `0x303A:0x1001`; with several boards attached, use the USB serial number in `adapter serial`
to select the target. The serial number is the chip's MAC address.

```sh
ioreg -p IOUSB -w0 -l | grep -E '"(USB Product Name|USB Serial Number)"'
```

Boards used for this guide (`esptool chip-id`, 2026-10-02): ESP32-S3 (QFN56) revision v0.2,
USB mode USB-Serial/JTAG.

| Board | USB serial number   | Port on the recording Mac, 2026-10-08 |
| ----- | ------------------- | ------------------------------------- |
| S3 A  | `E8:06:90:95:F2:70` | `/dev/cu.usbmodem1101`                |
| S3 B  | `E8:06:90:95:80:6C` | `/dev/cu.usbmodem2101`                |

The checked-in TOML files name S3 B's port in `[Connection] port` and leave the serial number to
`--adapter-serial`, which fills `{adapter_serial}` in `adapter serial` and in `usb_reset_command`.
Port and serial number must name the same board. With the port of the other board, the inputs go to
one board while OpenOCD debugs the other. `--port` replaces `[Connection] port`.

### Reset and serial behaviour

[`ESP32USBSerialJTAGConnection`](../src/tracer/connection/esp32_serial_connection.py) handles the
CDC port:

- Opening the port resets the chip (RTS asserted, DTR released), and the firmware then prints the
  ready byte `A`.
- The host must pace its writes: the Arduino `HWCDC` driver keeps 256 received bytes and drops
  the rest. The adapter writes 64-byte chunks, 2 ms apart.
- The baud rate has no effect, so the TOML has no `baud_rate`.

Waveshare's guide says to hold BOOT while plugging in the cable before each upload. Esptool's
automatic reset into download mode over the USB-Serial/JTAG port worked for every recorded upload,
so BOOT is needed only when the running firmware has disabled its USB function.

### Debug resources per core

| Unit                             | Count | Used by                                                                          |
| -------------------------------- | ----- | -------------------------------------------------------------------------------- |
| Instruction breakpoints (IBREAK) | 2     | entry breakpoint (temporary), xml exit breakpoint, `finish` return breakpoint     |
| Data breakpoints (DBREAK)        | 2     | read watchpoints; the firmware also uses DBREAK1 as a FreeRTOS end-of-stack guard |

Source: `xtensa-core-esp32s3.cfg` (`ibreaknum 2`, `dbreaknum 2`) in Espressif OpenOCD. The two
units are separate, so breakpoints never take a watchpoint. `finish` needs one instruction
breakpoint: GDB also breaks on the C++ exception hook `_Unwind_DebugHook` when the ELF has one,
and these ELFs do not. The xml exit breakpoint and a `finish` return breakpoint fit the two IBREAKs.

An external JTAG probe would not add breakpoints: they belong to the target's debug unit. Switching
the S3 to JTAG on its GPIO pads would need an irreversible eFuse burn (`DIS_USB_JTAG` or
`STRAP_JTAG_SEL`).

## Firmware wrappers

The three wrappers use the paper's STM32 parser libraries and acceptance rules. Each accepts up
to 2,048 input bytes, with an extra buffer byte for the terminating NUL. They yield with `delay(1)`
while waiting for input, flush ready and result bytes, and drain oversized packets before rejecting
them with `0xff`. The serial protocol uses `A` as the ready marker, a four-byte little-endian length
followed by the payload, and `0` (accepted) or `0xff` (rejected) as the result.

The wrappers drive the Waveshare WS2812 on GPIO21 with Arduino's built-in `rgbLedWrite`. The generic
variant's RGB pin is not used.

### Status LED

| Colour | Firmware state |
| --- | --- |
| Blue | Startup complete enough to initialize the LED; waiting for the first input |
| Amber | Length header received; receiving the payload |
| Cyan | About to parse, parsing, or halted by GDB inside the parser |
| Green | Last input accepted |
| Red | Last input rejected by the parser |
| Magenta | Oversized packet being drained, or last packet rejected for size |

The last result stays visible while waiting for the next packet. Colours use low brightness
(channel values at most 16 out of 255). There is no blink task or added delay. LED writes run
outside the traced parser, using the core's RMT driver; XML's entry and exit remain
`main.ino:46` and `main.ino:53`. The first driver initialization happens during setup, before
input handling.

These are firmware states, not host stages: the existing protocol does not identify tracing,
mining or precision/recall evaluation. Amber and cyan can be too brief to see during normal
execution; cyan persists while GDB holds the parser. A retained colour is not a heartbeat or
proof of progress. The parser itself remains uninstrumented.

Seeds and evaluation corpora are the authors' STM32 directories, which the TOML files name
directly.

## Arduino build

Use [Arduino CLI 1.5.1](https://github.com/arduino/arduino-cli/releases/tag/v1.5.1) and Espressif's
Arduino-ESP32 core `esp32:esp32@3.3.12`. Install the core before building:

```sh
arduino-cli core update-index \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.12 \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core list
```

Confirm core 3.3.12, then install the target's library as its README says.

### Apple Silicon prerequisite

Arduino CLI 1.5.1 installs an Intel-only `ctags` 5.8-arduino11
([upstream issue](https://github.com/arduino/ctags/issues/20)). On a Mac without Rosetta, build the
unmodified upstream release natively:

```sh
curl -fL -o /tmp/arduino-ctags.tar.xz \
  https://github.com/arduino/ctags/releases/download/5.8-arduino11/ctags-5.8-arduino11.tar.xz
PREFIX="$HOME/.local/opt/arduino-ctags/5.8-arduino11"
mkdir -p "$PREFIX/source"
tar -xf /tmp/arduino-ctags.tar.xz -C "$PREFIX/source" --strip-components=1
(cd "$PREFIX/source" && ./configure --prefix="$PREFIX" && \
  make -j4 CFLAGS='-O2 -include dirent.h' && make install)
```

Pre-including the system header avoids the old `ctags` `__unused__` macro colliding with the macOS
SDK header. The build property below selects this executable; omit it where the packaged one works.

### Build and upload

From the repository root, set `TARGET` to `esp32-s3_json`, `esp32-s3_cgidecode` or
`esp32-s3_xml`:

```sh
TARGET=<?>
FQBN=esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,LoopCore=0

arduino-cli compile -b "$FQBN" \
  --build-property 'compiler.optimization_flags=-O0 -g3 -ggdb3' \
  --build-property "runtime.tools.ctags.path=$HOME/.local/opt/arduino-ctags/5.8-arduino11/bin" \
  --build-path "$PWD/example_firmware/$TARGET/build" \
  -v "example_firmware/$TARGET"

arduino-cli upload -b "$FQBN" -p /dev/cu.usbmodem<n> \
  --input-dir "$PWD/example_firmware/$TARGET/build" \
  "example_firmware/$TARGET"
```

The expected ELF is `build/$TARGET.ino.elf`.

- `CDCOnBoot=cdc,USBMode=hwcdc`: `Serial` is the CDC function of the USB-Serial/JTAG peripheral
  (the `HWCDC` driver), not the S3's USB-OTG peripheral.
- `LoopCore=0`: the Arduino loop task, and so the wrapper and the parser, runs on core 0, the only
  core OpenOCD debugs. The default is core 1. The option sets `ARDUINO_RUNNING_CORE=0`; the
  wrapper and parser sources are unchanged.
- Stop OpenOCD before flashing: it holds the JTAG function, and esptool resets the chip through the
  CDC port.

## Debugger and tracing

### Debugger and debug server

| Tool        | Version                                                                     | Path on the recording Mac                                                        |
| ----------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| GDB         | Espressif `xtensa-esp32s3-elf-gdb` 17.1_20260402, installed with the core | `~/Library/Arduino15/packages/esp32/tools/xtensa-esp-elf-gdb/17.1_20260402/bin/` |
| OpenOCD     | Espressif [`v0.12.0-esp32-20260831`][openocd-release], macOS arm64 archive  | `~/.espressif/openocd-esp32/`                                                    |
| ROM symbols | [`esp-rom-elfs` 20241011][rom-elfs], `esp32s3_rev0_rom.elf` (all v0.x chips) | `~/.espressif/tools/esp-rom-elfs/20241011/`                                      |

OpenOCD options in `gdb_server_path`, all required:

| Option                  | Effect                                      | Without it                                                          |
| ----------------------- | ------------------------------------------- | ------------------------------------------------------------------- |
| `set ESP_RTOS none`     | GDB sees the CPU, not FreeRTOS tasks        | OpenOCD reads the task lists at every halt, which slows every step  |
| `set ESP_ONLYCPU 1`     | Debug core 0 only                           | OpenOCD hands GDB the first halted core it polls, not the parser's  |
| `set ESP_FLASH_SIZE 0`  | No flash support; every breakpoint hardware | A third breakpoint is written into flash, which changes the program |
| `adapter serial {adapter_serial}` | Select this board's USB device    | OpenOCD may open a different attached Espressif device  |

### Values to change on another machine

| Table and key                    | Value to change                                                   |
| -------------------------------- | ----------------------------------------------------------------- |
| `[Connection] port`              | The CDC port, `/dev/cu.usbmodem<n>`                               |
| `[GDB] gdb_path`                 | Espressif `xtensa-esp32s3-elf-gdb` from the Arduino core          |
| `[GDB] gdb_server_path`          | OpenOCD executable and scripts folder; keep all placeholders      |
| `[GDB.esp32s3] rom_elf`          | ROM symbol file matching the chip revision                        |
| `[GDB.esp32s3] usb_reset_command` | The script path; keep `{adapter_serial}` after `--serial`         |

### Target settings in TOML

Shared settings stay in `[GDB]`; see the [configuration
reference](../README.md#writing-up-configuration-tomls). Set `instance = "esp32s3"` and
`input_channel = "esp32-usb-serial-jtag"`. The watchpoint count stays in `[GDB]`; the S3-specific
minimum distance and other S3 settings live in `[GDB.esp32s3]`:

| Table         | Field                     | Type and meaning                                                                       |
| ------------- | ------------------------- | -------------------------------------------------------------------------------------- |
| `GDB`         | `watchpoint_count`        | int, 1 or 2 (the DBREAK pairs).                                                        |
| `GDB.esp32s3` | `watchpoint_min_distance` | optional positive int, defaults to 1; must explicitly be at least 4 when `watchpoint_count = 2`. |
| `GDB.esp32s3` | `rom_elf`                 | optional str, ROM symbol ELF matching the chip revision.                               |
| `GDB.esp32s3` | `reset_on_connect`        | optional bool, must be `false` (the default); see below.                               |
| `GDB.esp32s3` | `startup_retry_interval`  | optional positive finite seconds between OpenOCD start attempts, default `0.2`.        |
| `GDB.esp32s3` | `startup_delay`           | optional non-negative finite seconds from the serial reset to OpenOCD's start, default `3`. |
| `GDB.esp32s3` | `usb_reset_command`       | optional str, command run between attach attempts; empty attaches once. May contain `{adapter_serial}`. |

`reset_on_connect` must be `false`: the serial port's reset pulse restarts the firmware before
OpenOCD attaches, and again after a serial reconnect. With `reset_on_connect = true` on the board
(2026-10-08), the USB device re-enumerated after OpenOCD's `reset halt`: the open serial port
failed with `Device not configured`, and the trace stopped at the entry breakpoint.

Serial settings live in `[Connection]`:

| Field | Type and meaning |
| --- | --- |
| `dtr` | optional bool, defaults to `false`. |
| `rts` | optional bool, defaults to `true`. |
| `reset_pulse` | optional bool, defaults to `true`; setting it to `false` requires `rts = false`. |
| `reset_pulse_sec` | optional positive finite seconds, default `0.05`. |
| `quiet_sec` | optional positive finite seconds after the latest ready marker, default `0.2`. |
| `grace_sec` | optional positive finite seconds to wait after a reboot before resending, default `1.0`. |
| `write_gap_sec` | optional positive finite seconds between 64-byte writes, default `0.002`. |

The USB channel rejects `baud_rate`. The loader also rejects unknown or misplaced S3 keys, ARM DWT
settings, more than two watchpoints, two watchpoints without the minimum distance,
`reset_on_connect = true` and a non-byte `watchpoint_type`.

### Debug register values

[`esp32s3_debug.py`](../src/tracer/instance/esp32s3_debug.py) defines the values used by the S3
backend. Their sources are pinned to the OpenOCD release above and to ESP-IDF's `soc.h`.

| Python definition                 | Source definition                                     | Value                    |
| --------------------------------- | ----------------------------------------------------- | ------------------------ |
| `DebugCause.IC`, `.IB`, `.DB`     | `DEBUGCAUSE_IC`, `_IB`, `_DB` (`xtensa_debug_module.h`) | `1`, `2`, `4`            |
| `DebugCause.BI`, `.BN`, `.DI`     | `DEBUGCAUSE_BI`, `_BN`, `_DI`                         | `8`, `0x10`, `0x20`      |
| `DEBUGCAUSE_DBNUM_SHIFT`, `_MASK` | `DEBUGCAUSE_DBNUM_SHIFT`, `DEBUGCAUSE_DBNUM_MASK`     | `8`, `0xf`               |
| `DBreakC.LOAD`, `.STORE`          | `BIT(30)`, `BIT(31)` in `xtensa_watchpoint_add`       | `0x40000000`, `0x80000000` |
| `DBREAKC_READ_BYTE`               | `ALIGN_DOWN(0x3F, 1) \| BIT(30)`                       | `0x4000003f`             |
| `DATA_BREAKPOINT_COUNT`           | `dbreaknum 2` (`xtensa-core-esp32s3.cfg`)             | `2`                      |
| `PRO_CPU_PRID`                    | `PRO_CPUID` (ESP-IDF `soc.h`)                          | `0xcdcd`                 |
| `MASK_ROM`                        | `SOC_IROM_MASK_LOW` to `SOC_IROM_MASK_HIGH`           | `0x40000000`-`0x40060000` |

The same module decodes the few instructions the backend must recognise, from the Xtensa ISA
opcode maps: the scalar loads (`L8UI`, `L16UI`, `L16SI`, `L32I`, `L32AI`, `L32I.N`), `ENTRY`,
`CALL4/8/12`, `CALLX4/8/12`, `L32R` and `JX`. The host tests pin each value and encoding.

### Running the evaluation

Flash the target's firmware, then run the three stages with the target's TOML, in this order:

```sh
TARGET=esp32-s3_json
OPTION=2-watchpoints   # or 1-watchpoint
CONFIG=example_firmware/$TARGET/configuration/configuration.$OPTION.toml
BOARD=(--adapter-serial E8:06:90:95:80:6C)  # add --port and --gdb-port as needed
uv run src/tracer/trace.py --config "$CONFIG" "${BOARD[@]}"
uv run src/miner/mine.py --config "$CONFIG" "${BOARD[@]}"
uv run src/eval/precision_recall.py --config "$CONFIG" "${BOARD[@]}" --out evaluation.json
```

All three stages start OpenOCD and run inputs on the board, so pass them the same flags. The
configurations use `{gdb_port}`, `{telnet_port}` and `{tcl_port}` placeholders; the
[configuration reference](../README.md#writing-up-configuration-tomls) lists the flags
and how to enable the OpenOCD consoles. A missing `--adapter-serial` stops the stage before any
server starts.

`trace.py` creates the next free `output/<target>/trial-<n>/`; `mine.py` and `precision_recall.py`
use the newest one. Mine only after every seed has a trace. Before each stage, check that nothing
holds the port (`lsof /dev/cu.usbmodem<n>`) and that no OpenOCD runs (`pgrep -fl openocd`): a
stopped `trace.py` or `mine.py` can leave its serial worker, GDB and OpenOCD running.

### Tracing: the paper replica method

Each TOML follows the paper's embedded setup (Eisele et al. 2025, Sections 4.1 and 5.4) and the
configuration of its STM32 reference: same entry point, exit point and skip list
(`ignore_functions_regex`, skipped with GDB `finish`; `__aeabi_dadd` written as `__adddf3`). The
firmware is not instrumented. Window selection stays in the generic tracer; the S3 debugger
behaviour below is in [`esp32s3_instance.py`](../src/tracer/instance/esp32s3_instance.py).

**Reads are polled after every step.** A DBREAK match halts the core *before* the load executes.
During a single step OpenOCD reports that halt as an ordinary step (`xtensa_do_step`): GDB shows
`end-stepping-range` with the pc unchanged, and no watchpoint. `DEBUGCAUSE` keeps the cause. The
backend reads it after every step, records the read on the load's trace entry and steps again; on
that step OpenOCD disables the DBREAKs, executes the load and re-arms them. This is the paper's own
method on ARMv7, where the DWT does not halt during single-step and the tracer reads `DWT_FUNCTION`
after every step. The poll reads OpenOCD's register cache, which OpenOCD refills at every halt; it
costs about 1 % of a step.

**Watched bytes are at least 4 apart.** One halt names one DBREAK (`DEBUGCAUSE.DBNUM`). When one
32-bit load reads two watched bytes, the second read is lost. With two watchpoints and
`GDB.esp32s3.watchpoint_min_distance = 4`, the generic tracer spreads each run's two bytes at
least four apart, and every byte is still watched in exactly one run (see the [configuration
reference](../README.md#shared-fields)). S3 defaults to distance 1, but two-watchpoint
configurations must explicitly set at least 4. Non-S3 targets always use contiguous windows
with distance 1. The backend also checks the distance, and accepts a hit
only from a scalar load of at most 4 bytes that then retires to its successor (or to `LBEG` at the
end of a zero-overhead loop).

**The firmware can rewrite DBREAK1.** The Arduino-ESP32 SDK is built with
`CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK=y`: every FreeRTOS task switch writes a stack-guard
watchpoint into the last DBREAK. A task switch happens at an interrupt exit, which OpenOCD masks
while stepping, or at a direct `vPortYield()`, which needs no interrupt. The backend compares both
DBREAK pairs after every step and stops the trace on any change. When a `finish` ends at its return
breakpoint, the core has run freely and no reads were recorded, so a changed watchpoint is inserted
again. The [2026-10-08 positive control](#check-of-this-backend-on-the-board) observed a real
FreeRTOS overwrite of DBREAK1 and verified that this recovery path restored it.

**Register-window exceptions are not trace entries.** A step at `retw` or a call can end at the
same pc because OpenOCD stepped through a WindowUnderflow or WindowOverflow handler, which returns
to the instruction. A same-pc step with a changed `WindowStart` is repeated, so the trace keeps one
entry per executed instruction.

**ROM jump stubs are followed.** The S3 calls ROM routines (`strlen`, `strncmp`, `memcpy`,
`memset`) through two-instruction stubs: `l32r aN, <routine>; jx aN`. A stub has no `ENTRY`, so
GDB cannot unwind it: it shows the caller's stack, and `finish` overshoots. After a windowed call
into a stub inside mask ROM, the backend steps through the stub and reports the stop at the
routine's `ENTRY`. Any other call target without `ENTRY` stops the trace.

**`finish` stops are checked.** The return breakpoint and the exit breakpoint are IBREAKs, so their
stops must show `DEBUGCAUSE.IB`. ROM routines have no DWARF, so GDB reports their return without a
reason; the tracer accepts that while a `finish` is pending. GDB treats Xtensa watchpoints as
nonsteppable: on a read inside the skipped function it removes its watchpoints, steps over the
load and reports `read-watchpoint-trigger`. That read is not recorded, as in the authors' STM32
traces, and the tracer keeps skipping. GDB inserts the watchpoints again at the next resume.

**Attach recovery.** OpenOCD starts `startup_delay` seconds after the serial reset: opening the JTAG
function while the firmware was still starting its USB serial port wedged the device in 1 of 17
attaches with 1 s, and in none of 40 with 3 s. The USB device can still stop answering
(`libusb_get_string_descriptor_ascii() failed`); then the backend runs `usb_reset_command`
([`scripts/esp32_usb_reset.py`](../scripts/esp32_usb_reset.py)) and attaches again, up to three
attempts. Nothing has been traced at that point.

| Target               | Skipped with `finish`                                                                         | Breakpoints while tracing          |
| -------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------- |
| `esp32-s3_json`      | `malloc`, `free`, `_strtod_l`, `__adddf3`, `__floatdidf`, `__floatundidf`, `strlen`, `memset` | one IBREAK per `finish`            |
| `esp32-s3_cgidecode` | nothing                                                                                       | none                               |
| `esp32-s3_xml`       | list never fires                                                                              | one IBREAK for the exit breakpoint |

### Recorded results

One run per program, as in the paper's Section 5.4: the authors' 20 seeds, two watchpoints unless
stated, and precision and recall on 1,000 inputs. The runs used the S3 replica branch of 2026-10-02
to 10-05 and precede the current backend. Mining is unseeded, so each score is one sample. The
comparison scripts, configurations, evaluations and trace hashes are archived on the `docs/thesis`
branch (`docs/thesis/esp32s3-watchpoint-review-fixes-2026-10-08/`); the recorded checkout
revisions do not identify the exact source of every resumed trace.

| Program   | S3 precision | S3 recall | S3 F1  | Paper precision | Paper recall |
| --------- | ------------ | --------- | ------ | --------------- | ------------ |
| cgidecode | 98.2 %       | 97.1 %    | 97.7 % | 93.9 %          | 97.5 %       |
| json      | 99.0 %       | 88.1 %    | 93.2 % | 99.3 %          | 88.1 %       |
| json, one watchpoint | 99.5 % | 94.3 % | 96.8 % | 99.3 %   | 88.1 %       |
| xml       | 97.9 %       | 67.2 %    | 79.7 % | 99.4 %          | 93.5 %       |

The cgidecode and xml traces match the authors' STM32 reads (function, input offset and order,
20 of 20 seeds each); json matches the STM32 reads on 17 of 20 seeds. For json, both watchpoint
options matched addresses, functions, stacks and read sets on all 20 seeds. Their different scores
are unseeded samples.

### Check of this backend on the board

On 2026-10-08 both boards traced selected seeds with each watchpoint option:

| Target | Board | Seed | Coverage in both options | Entries | Reads |
| --- | --- | --- | --- | --- | --- |
| json | S3 A | `input.17` | complete seed | 590 | 11 |
| cgidecode | S3 B | `input.17` | offsets 0 and 5 | 637 | 3 |
| xml | S3 B | `input.2` | offset 0 and exit breakpoint | 1,292 | 1 |

JSON traces matched the historical reference in every field. CGI and XML matched their historical
references after removing `function_args`, which the miner does not read, and restricting reads to
the tested offsets. In a positive control on S3 B the firmware's FreeRTOS stack guard replaced
DBREAK1 (`DBREAKC = 0x80000020`); the backend reported `S3 DBREAK1 changed` and restored the
watchpoint. These checks cover selected parser paths and do not repeat the 20-seed campaigns,
mining or evaluation. The report, scripts and captured artifacts are on the `docs/thesis` branch
(`docs/thesis/esp32s3-watchpoint-review-2026-10-08/`).

On 2026-10-12 the status-LED firmware traced cgidecode seeds 4, 10, 11 and 20 on S3 B with both
options. All eight traces were byte-identical to the trial-0 traces of the same firmware on S3 A.

[waveshare]: https://docs.waveshare.com/ESP32-S3-zero
[openocd-release]: https://github.com/espressif/openocd-esp32/releases/tag/v0.12.0-esp32-20260831
[rom-elfs]: https://github.com/espressif/esp-rom-elfs/releases/tag/20241011
