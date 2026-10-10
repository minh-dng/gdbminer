# Setting up the ESP32-C3 DevKitM-1-N4X

We are discussing the ESP32-C3 DevKitM-1-N4X hardware setup, firmware wrappers, the Arduino build,
the debugger and the tracing method. See each target README for more information

GDBMiner runs this board in one of two setups. Both debug through the chip's built-in
USB-Serial/JTAG peripheral; they differ in the port that carries the inputs and the accept/reject
byte. Connect the cables of your setup before you run `trace.py`, `mine.py` or
`precision_recall.py`.

| Setup      | Inputs over               | TOML file                     | `input_channel`         |
| ---------- | ------------------------- | ----------------------------- | ----------------------- |
| Two cables | UART (CP2102N, Micro-USB) | `configuration.2-cables.toml` | `esp32-uart`            |
| One cable  | Native USB (CDC-ACM port) | `configuration.1-cable.toml`  | `esp32-usb-serial-jtag` |

The firmware source is the same in both setups. The build option `CDCOnBoot` decides whether
`Serial` is UART0 or the USB-Serial/JTAG serial port, so each setup has its own build directory (see
[Build and upload](#build-and-upload)): `build-1/` for one cable, `build-2/` for two.

|               | UART link                           | Native USB link                            |
| ------------- | ----------------------------------- | ------------------------------------------ |
| Chip side     | CP2102N USB-to-UART bridge on UART0 | Built-in USB-Serial/JTAG on GPIO18 and 19  |
| Connection    | The board's Micro-USB port          | A USB breakout wired to the pins (below)   |
| Mac device    | `/dev/cu.usbserial-<n>`             | `/dev/cu.usbmodem<n>`                      |
| Two cables    | Flashing, each input and its answer | OpenOCD and GDB (debugging)                |
| One cable     | Not used                            | Debugging, flashing, each input and answer |
| Configured in | `[Connection] port`                 | `adapter serial`; one cable: also `port`   |

The Micro-USB port is UART-only: the chip's native USB pins (GPIO18 and GPIO19) are not wired to
it, so the native USB link needs the extra wiring in both setups. macOS lists the native USB device
as "USB JTAG_serial debug unit".

## Hardware

### UART link (Micro-USB)

Plug a USB cable into the board's Micro-USB port. The CP2102N bridge appears as
`/dev/cu.usbserial-<n>`. Set that path as `port` in the `[Connection]` section of the target's
`configuration.2-cables.toml`. The number `<n>` changes when you re-plug the board or use another
USB port, so check it before each session.

To find the port, list the serial ports. `arduino-cli` comes from the [Toolchain](#toolchain) step;
without it, compare `ls /dev/cu.*` before and after plugging in the cable.

```sh
arduino-cli board list
```

Example output:

```text
Port                            Protocol Type              Board Name          FQBN                      Core
/dev/cu.Bluetooth-Incoming-Port serial   Serial Port       Unknown
/dev/cu.CMFBuds                 serial   Serial Port       Unknown
/dev/cu.JabraEvolve75SE         serial   Serial Port       Unknown
/dev/cu.debug-console           serial   Serial Port       Unknown
/dev/cu.usbmodem1101            serial   Serial Port (USB) ESP32 Family Device esp32:esp32:esp32_family  esp32:esp32
                                         Serial Port (USB) Ozobot DRVKit       esp32:esp32:ozobot_drvkit esp32:esp32
/dev/cu.usbserial-210           serial   Serial Port (USB) Unknown
```

Use the `usbserial-<n>` entry. That is the Micro-USB port on the board, the CP2102N USB-to-UART
bridge. The `usbmodem<n>` entry is the native USB link.

### Native USB link (GPIO18 and GPIO19)

Wire a USB breakout to the board so the Mac talks directly to the chip's USB-Serial/JTAG peripheral:

| Breakout line | Board pin |
| ------------- | --------- |
| D−            | GPIO18    |
| D+            | GPIO19    |
| GND           | GND       |
| 5 V           | 5 V       |

All four wires are required. D− and D+ form one USB differential pair, referenced to GND. Plug the
breakout into the Mac. It shows up as a second device next to the UART bridge. A loose joint drops
this link mid-run: OpenOCD then reports `esp_usb_jtag: device not found`, and the tracer exits on a
command or stop timeout. The September 30 XML run recorded such a failure. Mining and evaluation
start OpenOCD in the same way, so they need this link too, although in the two-cable setup they
only use the UART to test inputs.

The peripheral is one USB device with two functions: a vendor-specific JTAG adapter, which OpenOCD
uses, and a CDC-ACM serial port, `/dev/cu.usbmodem<n>` (ESP32-C3 TRM v1.4, §30.2). The one-cable
setup sends the inputs over that serial port, so the breakout is the only cable: set the
`usbmodem<n>` path as `port` in `configuration.1-cable.toml`. Esptool flashes over it too.

### Finding the identifiers

OpenOCD finds the JTAG device over USB, not through a `/dev` path. `interface/esp_usb_jtag.cfg`
matches the vendor and product ID `0x303a:0x1001`. The `adapter serial` option in `gdb_server_path`
then selects one board when several are attached. For this chip the USB serial number is the chip's
MAC address, and it stays the same when you re-plug.

List the attached devices with either command:

```sh
arduino-cli board list --format json    # per port: properties.vid, .pid, .serialNumber
ioreg -p IOUSB -w0 -l | grep -E '"(USB Product Name|USB Serial Number|idVendor|idProduct)"'
```

The default `arduino-cli board list` table does not show serial numbers; use the JSON output.

Values for this board (checked 2026-09-30):

| Link | Port                    | VID:PID         | USB serial number                    |
| ---- | ----------------------- | --------------- | ------------------------------------ |
| JTAG | `/dev/cu.usbmodem1101`  | `0x303A:0x1001` | `A0:F2:62:01:70:28` (the chip's MAC) |
| UART | `/dev/cu.usbserial-210` | `0x10C4:0xEA60` | `8afe88d078bcf0119b5f157148e9de0f`   |

Pass the JTAG serial number as `--adapter-serial <MAC>` to `trace.py`, `mine.py` and
`precision_recall.py`: the configuration files carry `-c "adapter serial {adapter_serial}"` in
`gdb_server_path` and each stage fills it in. The UART serial number is not used.

## Firmware wrappers

Each C3 target ports the wrapper of its STM32 reference (`stm32_arduinojson`, `stm32_cgidecode`,
`stm32_libyxml`) with the same parser library, acceptance rule and serial protocol. Diffing each
wrapper against its reference shows these five changes in all three ports; the target READMEs list
any others:

- LED on GPIO8.
- `buf` has one extra byte, so a 2,048-byte input can be NUL-terminated inside the array.
- `delay(1)` while waiting for UART input, so the ESP32 runtime can run.
- `Serial.flush()` after the ready and result bytes.
- An oversized packet is drained and rejected with `0xff` instead of hanging the board.

### Serial protocol values

[`ParserResult`][parser-result] names the result bytes emitted by the
[JSON wrapper][json-wrapper], [CGI wrapper][cgi-wrapper] and [XML wrapper][xml-wrapper].
`ACCEPTED = 0` and `REJECTED = 0xff` are fixed wire values, so the enum uses `@unique` with
explicit assignments. `auto()` would assign different values. The existing `READY_BYTE = ord("A")`
names the request marker.

The UART transfer estimate uses `_UART_BITS_PER_BYTE = 10`, matching PySerial's default 8N1
framing: one start bit, eight data bits and one stop bit. Baud rate and reset/recovery timings
remain TOML settings. The [PySerial constructor reference][pyserial-api] defines those defaults.

## Arduino build

The steps in this part are specific to Arduino CLI and the Arduino-ESP32 core.

### Toolchain

Build with Espressif's official Arduino-ESP32 distribution and its declared compiler/runtime
dependencies.

Use Arduino CLI 1.5.1 ([GitHub](https://github.com/arduino/arduino-cli/releases/tag/v1.5.1))
[^arduino-cli]. It runs used the archive, unpacked to `~/.local/opt/arduino-cli/1.5.1/`.
Run these commands before building:

```sh
arduino-cli core update-index \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.12 \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core list
```

Confirm core 3.3.12 before building. The official package index selects matching compiler and
runtime versions. Then install the target's library as its README says, and check it with
`arduino-cli lib list`.

### Apple Silicon host prerequisite

Arduino CLI 1.5.1 installs an Intel-only `ctags` 5.8-arduino11 ([GitHub issue](https://github.com/arduino/ctags/issues/20)).
On a Mac without Rosetta, compile the same unmodified upstream release natively.

```sh
curl -fL -o /tmp/arduino-ctags.tar.xz \
  https://github.com/arduino/ctags/releases/download/5.8-arduino11/ctags-5.8-arduino11.tar.xz
PREFIX="$HOME/.local/opt/arduino-ctags/5.8-arduino11"
mkdir -p "$PREFIX/source"
tar -xf /tmp/arduino-ctags.tar.xz -C "$PREFIX/source" --strip-components=1
(cd "$PREFIX/source" && ./configure --prefix="$PREFIX" && \
  make -j4 CFLAGS='-O2 -include dirent.h' && make install)
```

Pre-including the system header avoids the old ctags `__unused__` macro colliding with the current
macOS SDK header. No ctags source or installed Arduino package is patched. The build property below
selects this native executable. Omit that property on hosts where the packaged executable works.

### Build and upload

From the repository root, set `TARGET` to `esp32-c3_json`, `esp32-c3_cgidecode` or `esp32-c3_xml`.
For the two-cable setup, build into `build-2/` and upload over the UART port (see
[UART link](#uart-link-micro-usb)):

```sh
TARGET=<?>

arduino-cli compile \
  -b esp32:esp32:esp32c3:CDCOnBoot=default,FlashMode=dio \
  --build-property 'compiler.optimization_flags=-O0 -g3 -ggdb3' \
  --build-property "runtime.tools.ctags.path=$HOME/.local/opt/arduino-ctags/5.8-arduino11/bin" \
  --build-path "$PWD/example_firmware/$TARGET/build-2" \
  -v "example_firmware/$TARGET"

arduino-cli upload \
  -b esp32:esp32:esp32c3:CDCOnBoot=default,FlashMode=dio \
  -p /dev/cu.usbserial-<n> \
  --input-dir "$PWD/example_firmware/$TARGET/build-2" \
  "example_firmware/$TARGET"
```

The expected ELF is `build-2/$TARGET.ino.elf`. `-O0` and debug information apply to source compiled
by this command, including the parser. They do not rebuild Espressif's precompiled SDK libraries.

`CDCOnBoot=default` keeps CDC-on-boot disabled: input uses the UART, while the separate native USB
connection provides JTAG. No upload is needed for each seed or mining query.

For the one-cable setup, build with `CDCOnBoot=cdc` into `build-1/` and upload over the
native USB serial port (see [Native USB link](#native-usb-link-gpio18-and-gpio19)):

```sh
arduino-cli compile \
  -b esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio \
  --build-property 'compiler.optimization_flags=-O0 -g3 -ggdb3' \
  --build-property "runtime.tools.ctags.path=$HOME/.local/opt/arduino-ctags/5.8-arduino11/bin" \
  --build-path "$PWD/example_firmware/$TARGET/build-1" \
  -v "example_firmware/$TARGET"

arduino-cli upload \
  -b esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio \
  -p /dev/cu.usbmodem<n> \
  --input-dir "$PWD/example_firmware/$TARGET/build-1" \
  "example_firmware/$TARGET"
```

`CDCOnBoot=cdc` defines `ARDUINO_USB_CDC_ON_BOOT=1` (check `build-1/compile_commands.json`),
which makes `Serial` the `HWCDC` driver of the USB-Serial/JTAG serial port. Only the driver behind
`Serial` changes; the wrapper and parser sources are the same, but the ELF is not. Esptool reports
`USB mode: USB-Serial/JTAG` and can flash either build over this port. OpenOCD must not run while
it flashes.

### Upstream sources

- [Arduino-ESP32 3.3.12](https://github.com/espressif/arduino-esp32/releases/tag/3.3.12)
- [Official installation
  instructions](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)
- [Official package index](https://espressif.github.io/arduino-esp32/package_esp32_index.json)

## Debugger and tracing

### Choosing the debugger

The `[GDB] gdb_path` of all three C3 targets points to Espressif's own `riscv32-esp-elf-gdb`
17.1_20260402. Arduino CLI installs it with the `esp32:esp32` core:

```text
~/Library/Arduino15/packages/esp32/tools/riscv32-esp-elf-gdb/17.1_20260402/bin/riscv32-esp-elf-gdb
```

GDBMiner sets a breakpoint at each target's entry function (`break cJSON_Parse` for json). Homebrew
GDB 17.2 crashes with a fatal internal error (exit code 139) when it does this on the json ELF, even
with no board attached. Espressif's GDB sets the breakpoint correctly. The cause of the crash is not
recorded. Only the debugger differs: the ELF, its debug information and the firmware instructions
are unchanged.

Check a debugger against an ELF without a board:

```sh
gdb -batch -nx -ex 'break cJSON_Parse' example_firmware/esp32-c3_json/build-2/esp32-c3_json.ino.elf
```

Result (checked 2026-09-30, json ELF `f6cf61b7…`): Homebrew GDB exits with 139. Espressif's GDB
prints `Breakpoint 1 at 0x42001cf8: file …/cJSON.c, line 1208.` The check was run on the json ELF
only.

### Debug server and ROM symbols

Two more files are not installed by Arduino CLI:

- **OpenOCD:** Espressif's fork, release [`v0.12.0-esp32-20260831`][openocd-release]. The recorded
  runs unpacked its macOS arm64 archive to `~/.espressif/openocd-esp32/`. The Arduino core bundles
  an older build (`v0.12.0-esp32-20260424`); it was not used. Check with
  `~/.espressif/openocd-esp32/bin/openocd --version`.
- **ROM symbol file:** [`esp-rom-elfs`
  20241011](https://github.com/espressif/esp-rom-elfs/releases/tag/20241011) (installed here by the
  ESP-IDF tools to `~/.espressif/tools/esp-rom-elfs/20241011/`). Choose the file by chip revision.
  `arduino-cli upload` prints it, for example `ESP32-C3 AZ (QFN32) (revision v1.1)`; v1.1 needs
  `esp32c3_rev101_rom.elf`. Symbols for another revision can assign incorrect names to addresses and
  make `ignore_functions_regex` matches unreliable.

### Values to change on another machine

The three `configuration.2-cables.toml` and three `configuration.1-cable.toml` files hold paths and
device names from the recording Mac. Change these in each:

| Table and key           | Value to change                                                  |
| ----------------------- | ---------------------------------------------------------------- |
| `[Connection] port`     | Two cables: UART device, such as `/dev/cu.usbserial-<n>`.        |
|                         | One cable: native USB serial port, `/dev/cu.usbmodem<n>`.        |
| `[GDB] gdb_path`        | Espressif `riscv32-esp-elf-gdb` from the Arduino core.           |
| `[GDB.esp32c3] rom_elf` | ROM symbol file matching the chip revision.                      |
| `[GDB] gdb_server_path` | OpenOCD executable and scripts folder; keep all placeholders.    |

### Debug register values

[`esp32c3_debug.py`][c3-debug-values] defines the enums used by the C3 backend. Their register
encodings come from [Espressif OpenOCD's `debug_defines.h`][debug-defines], pinned to the release
above. The enum names follow the header's macros so each value can be checked against its source.
The `MControlFlag` source entries omit the `CSR_MCONTROL_` prefix, except for the trigger type.

| Python definition | OpenOCD definition | Value |
| --- | --- | --- |
| `DCSRCause.TRIGGER` | `CSR_DCSR_CAUSE_TRIGGER` | `2` |
| `DCSRCause.STEP` | `CSR_DCSR_CAUSE_STEP` | `4` |
| `DCSRMask.CAUSE` | `CSR_DCSR_CAUSE` | `0x1c0`, bits 8:6 |
| `DCSR_CAUSE_OFFSET` | `CSR_DCSR_CAUSE_OFFSET` | `6` |
| `DCSRMask.STEPIE` | `CSR_DCSR_STEPIE` | `1 << 11` |
| `MControlFlag.LOAD`, `.STORE`, `.EXECUTE` | `LOAD`, `STORE`, `EXECUTE` | `1`, `2`, `4` |
| `MControlFlag.M` | `M` | `1 << 6` |
| `MControlFlag.ACTION_DEBUG_MODE` | `ACTION_DEBUG_MODE << ACTION_OFFSET` | `1 << 12` |
| `MControlFlag.HIT` | `HIT` | `1 << 20` |
| `MControlFlag.DMODE` | `DMODE(32)` | `1 << 27` |
| `MControlFlag.TYPE_MCONTROL` | `CSR_TDATA1_TYPE_MCONTROL` shifted to bits 31:28 | `2 << 28` |

The read-trigger control word combines `TYPE_MCONTROL`, `DMODE`, `ACTION_DEBUG_MODE`, `M` and
`LOAD`, producing `0x28001041`. The access mask combines `LOAD`, `STORE` and `EXECUTE`, producing
`0x7`. Readback validation ignores `CSR_MCONTROL_MASKMAX(32)`, bits 26:21, with the mask
`0xf81fffff`. `HARDWARE_TRIGGER_COUNT = 8` follows the [C3 hardware limits][c3-debug-limits]; both
the backend and TOML validator use it.

All enums use `@unique`. `DCSRCause` uses `auto()` after the explicit `EBREAK = 1` because the
header defines consecutive causes 1 through 7. `MControlFlag` uses `auto()` for its first three
single-bit flags. Sparse register bits and field masks keep explicit encodings. See Python's
[`auto()` rules][python-enum-auto]. The host checks pin the numeric encodings independently, so
reordering an `auto()` member fails validation.

A step onto a managed hardware instruction breakpoint has `DCSRCause.TRIGGER`, just like a read
trigger. With no owned read-trigger hits, the C3 backend forwards `breakpoint-hit` to the shared
tracer, which validates the configured exit breakpoint number. Unlabelled trigger stops and
unexpected breakpoint numbers still fail closed.

### Target settings in TOML

Shared debugger settings, including `watchpoint_count` and `watchpoint_type`, stay in `[GDB]`;
see the [shared configuration reference](../README.md#writing-up-configuration-tomls).
Set `instance = "esp32c3"` from the [`GDBInstance` enum][gdb-instance] and `input_channel` from
the [`InputChannel` enum][input-channel]: `"esp32-uart"` for two cables, `"esp32-usb-serial-jtag"`
for one. C3 settings live in `[GDB.esp32c3]`:

| Table | Field | Type and meaning |
| --- | --- | --- |
| `GDB.esp32c3` | `rom_elf` | optional str, ROM symbol ELF matching the chip revision. |
| `GDB.esp32c3` | `hardware_trigger_slot` | int, first read-trigger slot, in 0-7. |
| `GDB.esp32c3` | `reset_on_connect` | optional bool, reset after attach; defaults to `true`. |
| `GDB.esp32c3` | `breakpoint_always_inserted` | optional bool, defaults to `false`. |
| `GDB.esp32c3` | `startup_retry_interval` | optional positive finite seconds, default `0.2`. |
| `Connection` | `dtr` | optional bool, defaults to `false`. |
| `Connection` | `rts` | optional bool, defaults to `true`. |
| `Connection` | `reset_pulse` | optional bool, defaults to `true`. |
| `Connection` | `reset_pulse_sec` | optional positive finite seconds, default `0.05`. |
| `Connection` | `quiet_sec` | optional positive finite seconds, default `0.2`. |
| `Connection` | `grace_sec` | optional positive finite seconds, default `1.0`. |
| `Connection` | `baud_rate` | `esp32-uart`: positive int, the firmware's 9600; USB: rejected. |
| `Connection` | `write_gap_sec` | USB only: optional positive finite seconds, default `0.002`. |

After the UART EN reset (two cables), native USB/JTAG can disappear briefly. The C3 backend starts
OpenOCD with an explicit `init`, checks the target's `was_examined` state, then emits a readiness
marker. `init` can return after examination fails; the state check makes that attempt exit instead
of accepting a GDB connection against an unexamined target. It retries exited startup
attempts at `startup_retry_interval` until `GDB.timeout` expires; GDB attaches only after
successful initialization. Timeout or initialization failure closes the serial worker and
terminates/reaps only the OpenOCD/GDB processes owned by that instance. A stalled OpenOCD
is terminated at the deadline, with a five-second termination grace before forced kill.
This replaces the inherited fixed post-spawn sleep, not the STM32 startup path.

The serial timing settings apply to both ESP32 channels. `reset_pulse_sec` holds RTS asserted
before release when `reset_pulse = true`. `quiet_sec` is the silence required after the
latest firmware ready marker during initial/reboot synchronization. `grace_sec`, plus
packet transfer time at the configured baud rate (none on the USB-Serial/JTAG port), is how
long to wait for a result after a reboot marker before resending a lost packet. The serial
read timeout can add up to two seconds to that grace wait. Normal traced responses have no
deadline because GDB can hold the parser halted. All timings reject booleans, zero, negative,
infinite and NaN values. Omitted settings preserve the prior UART timing defaults.

The USB-Serial/JTAG port differs from the UART in three ways, all handled by
`ESP32USBSerialJTAGConnection`:

- **Reset.** The peripheral maps RTS and DTR like the bridge's auto-program circuit: RTS asserted
  with DTR released resets the chip, and it boots from flash once RTS is released (TRM Tables 30.3-2
  and 30.4-2). The same `rts`, `dtr` and `reset_pulse` settings therefore apply. On the recording
  Mac, every open of the port reset the chip anyway, and the reset did not drop the USB device:
  the port and OpenOCD's JTAG connection stayed up, so OpenOCD needed no start-up retry.
- **No baud rate.** The peripheral ignores the CDC line coding (TRM Table 30.3-1); data moves at USB
  full speed. For the xml evaluation inputs measured here (26 bytes on average), a query took about
  1 ms instead of about 35 ms at 9,600 baud; a 2,048-byte input took about 100 ms.
- **No software-queue backpressure.** The Arduino `HWCDC` driver copies each received USB packet
  into a 256-byte queue and drops what does not fit; the controller holds the host back only while
  its own one-packet buffer is not drained, for example while the core is halted. Inputs longer
  than 252 bytes lost bytes when written at once, and the wrapper then waited forever. The adapter
  writes 64-byte chunks, `write_gap_sec` apart. The 2 ms default lost nothing in the recorded
  checks, up to 2,048-byte inputs; this is open-loop pacing, so a shorter gap leaves the tested
  range.

For JSON:

```toml
[GDB.esp32c3]
rom_elf = "/path/to/esp32c3_rev101_rom.elf"
hardware_trigger_slot = 2
reset_on_connect = false
```

The six JSON watchpoints occupy slots 2-7. CGI starts at slot 0 with eight watchpoints; XML starts
at slot 1 with seven. XML also sets `breakpoint_always_inserted = true` in this table to keep its
exit breakpoint inserted across steps, as in the measured run.

`reset_on_connect = false` avoids a second reset after the serial adapter's reset pulse. It also
leaves reconnect recovery to that adapter. Keep the serial control-line and reset settings in
`[Connection]`. The adapter waits for
the firmware's ready marker, so no `boot_delay` setting is needed. If you disable `reset_pulse`,
also set `rts = false` so EN is released.

ARM DWT registers and `dwt_watchpoint_workaround` belong only in `[GDB.stm32]`. The C3 uses RISC-V
read triggers and requires no DWT placeholder or workaround flag. The loader rejects unknown or
misplaced C3 fields, obsolete connection settings, the generic serial channel, a baud rate on the
USB-Serial/JTAG channel, DWT settings on the C3, non-bool flags and trigger windows outside slots
0-7 before starting the debugger or serial worker.

### Running the evaluation

Flash the target's firmware, then run the authors' three stages with the target's TOML, in this
order:

```sh
TARGET=esp32-c3_json
CONFIG=example_firmware/$TARGET/configuration/configuration.2-cables.toml  # or .1-cable.toml
BOARD=(--adapter-serial A0:F2:62:01:70:28)  # add --port and --gdb-port as needed
PYTHONPATH=src .venv/bin/python src/tracer/trace.py --config "$CONFIG" "${BOARD[@]}"
PYTHONPATH=src .venv/bin/python src/miner/mine.py --config "$CONFIG" "${BOARD[@]}"
PYTHONPATH=src .venv/bin/python src/eval/precision_recall.py \
  --config "$CONFIG" "${BOARD[@]}" --out evaluation.json
```

All three stages start OpenOCD and run inputs on the board, so pass them the same flags. Besides
`--adapter-serial`, each accepts `--port` (replaces `[Connection] port`, which changes when you plug
into another socket) and `--gdb-port` (replaces `[GDB] gdb_port`, the port that fills `{gdb_port}`
in `gdb_server_path` and that GDB connects to). To run two boards in parallel, give each its own
`--adapter-serial`, `--port` and `--gdb-port`, for example `--gdb-port 3334` for the second. Two
runs of the same target share `BASIC.output_directory`, and mining and evaluation read its newest
`trial-<n>`, so such runs still need a second file with its own output directory. Omit `gdb_port`
from the configuration file to make `--gdb-port` required. Each value taken from a flag
is logged to `out.log`. Omit `Connection.port` or leave it empty to require `--port`. Each value
that replaces a different value from the file produces a warning. A flag whose placeholder is not
in `gdb_server_path`, an invalid or missing GDB port, or an
`{adapter_serial}` without `--adapter-serial` stops the stage before any server starts.

The configurations use `-c "telnet port {telnet_port}"` and `-c "tcl port {tcl_port}"`. Each
placeholder becomes `disabled` unless you pass `--telnet-port` or `--tcl-port`, so parallel
OpenOCD instances do not clash on the default console ports, 4444 and 6666. The tracer reaches
OpenOCD through GDB's `monitor` command and needs neither console. To inspect a running trace,
append `--telnet-port 4444 --tcl-port 6666` to the Python command, then connect from another
terminal:

```sh
telnet localhost 4444
```

Telnet provides an interactive console; Tcl provides the scripting/RPC interface. Enable either
independently. Give each parallel instance its own numbers, as with `--gdb-port`. Enabled console
ports must be in 1-65535 and differ from each other and the GDB port. `poll` shows target state,
and `reg` reads registers while halted. Commands such as `halt`, `resume` and `reset`
interfere with the tracer's control of execution.

`trace.py` resolves and validates machine overrides before creating the next free
`output/<target>/trial-<n>/`; invalid overrides leave no trial behind. `mine.py` and
`precision_recall.py` use the newest `trial-<n>`, and `mine.py` pairs traces with seeds by sorted
file name. Mine only after a trace run has written a trace for every seed. A failed or stopped trace
run still leaves its `trial-<n>`, which mining would then select. Pass `--out` to keep the scores;
without it, they are only in the log. Before each stage, check for a process holding the input port.
`lsof /dev/cu.usbserial-<n>` or `lsof /dev/cu.usbmodem<n>` lists them. Stopping `trace.py` or
`mine.py` can leave a serial worker running, which also blocks esptool with one cable. The
one-cable traces go to `output/<target>-1-cable/`, so a trial never mixes the two builds.

### Tracing: the paper replica method

Each target's TOML follows the paper's embedded setup (Eisele et al. 2025, §4.1 and §5.4) and the
configuration of its STM32 reference: same entry point and the same `ignore_functions_regex`,
skipped with GDB `finish`. The only name change is `__aeabi_dadd`, the ARM
EABI alias of libgcc `__adddf3`. `strlen`, `memset` and the soft-float helpers run from the chip's
mask ROM. The adapter loads `GDB.esp32c3.rom_elf` with GDB's `add-symbol-file`, alongside the
firmware ELF. It describes code already built into the chip and is never flashed. Its symbols let
the ignore regex match ROM function names. GDB's `finish` also depends on available unwind
information and debugger support; symbols alone do not guarantee it can return from a ROM call. The
recorded runs used `finish` successfully. The earlier `esp32c3_rom.gdb` rules and
`configuration.hw-eval.ini`, which stepped through those routines, have been removed.

The C3 has eight trigger slots shared by breakpoints and watchpoints. GDB's `finish` inserts two
hardware breakpoints (return address and the C++ exception hook `_Unwind_DebugHook`), so two slots
must stay free wherever `finish` runs. The adapter reserves its trigger window in OpenOCD after the
temporary entry breakpoint fires. This lets CGI reach its parser before reserving all eight slots.
`GDB.watchpoint_count` sets its size; `GDB.esp32c3.hardware_trigger_slot` sets its first slot.

| Target               | Skipped with `finish`                                                                         | Watchpoint slots                                  |
| -------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `esp32-c3_json`      | `malloc`, `free`, `_strtod_l`, `__adddf3`, `__floatdidf`, `__floatundidf`, `strlen`, `memset` | 6 (slots 2-7); slots 0-1 stay free                |
| `esp32-c3_cgidecode` | nothing                                                                                       | 8 (slots 0-7)                                     |
| `esp32-c3_xml`       | list never fires                                                                              | 7 (slots 1-7); the exit breakpoint takes one slot |

[^arduino-cli]:
    Arduino CLI drives the build, but the compiler is still Espressif's GCC from the core package.
    The core's `platform.txt` defines the build: about 70 compiler and archiver calls, the link
    against Espressif's precompiled SDK libraries, and the image steps (`esptool elf2image`,
    `gen_esp32part.py`, `merge-bin`). Calling GCC directly would mean recreating all of that by
    hand. The package index also resolves core 3.3.12 to its matching compiler, SDK libraries and
    `esptool` as one set. That set is the reason for this migration: the earlier build mixed a
    manually chosen GCC 16.1 with an older prebuilt framework and needed `toolchain_stubs.c` to
    link. The STM32 reference targets also use the Arduino framework, so the wrapper keeps the
    structure of the paper's setup. Arduino CLI records its options in `build-2/build.options.json`,
    so one pinned command repeats the build.

[gdb-instance]: ../src/tracer/instance/sut_instance.py
[input-channel]: ../src/tracer/connection/sut_connection.py
[openocd-release]: https://github.com/espressif/openocd-esp32/releases/tag/v0.12.0-esp32-20260831
[c3-debug-values]: ../src/tracer/instance/esp32c3_debug.py
[debug-defines]: https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/debug_defines.h
[c3-debug-limits]: https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/jtag-debugging/tips-and-quirks.html#breakpoints-and-watchpoints-available
[python-enum-auto]: https://docs.python.org/3.12/library/enum.html#enum.auto
[parser-result]: ../src/tracer/connection/sut_connection.py
[json-wrapper]: esp32-c3_json/src/main.cpp
[cgi-wrapper]: esp32-c3_cgidecode/src/main.cpp
[xml-wrapper]: esp32-c3_xml/main.ino
[pyserial-api]: https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial
