# GDBMiner on STM32 B-L4S5I-IOT01A

The B-L4S5I-IOT01A uses its on-board ST-Link debugger to expose the MCU through a GDB server
started by `st-util`. Its default port is 4242; the example configuration below selects 4243.
GDBMiner starts the configured server, so do not run another server on the same port.

Install GDBMiner's Python environment using the [repository README][readme]. Run the commands
below from the repository root.

## Install and connect

- Install the [ST-Link driver][stlink-driver] where required by your host operating system.
- Connect the board to the PC using the USB connector labelled **USB STLINK**.
- Install [PlatformIO (`pio`)][platformio].

On Debian or Ubuntu, install the debugger and USB tools:

```sh
sudo apt-get install stlink-tools gdb-multiarch libusb-dev
```

If flashing fails with `LIBUSB_ERROR_ACCESS`, put this rule in
`/etc/udev/rules.d/90-stm32.rules`:

```udev
# STLink v2
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="664", GROUP="plugdev"
```

Run `sudo udevadm control --reload` and ensure your user belongs to the `plugdev` group.
Reconnect the board after reloading the rules; log in again if you changed group membership.

## Build and flash

For example, build and flash the JSON firmware:

```sh
pio run --project-dir ./example_firmware/stm32_arduinojson/ --target upload
```

This is equivalent to running `pio run --target upload` inside
`example_firmware/stm32_arduinojson/`. PlatformIO stores the firmware ELF at:

```text
example_firmware/stm32_arduinojson/.pio/build/disco_l4s5i_iot01a/firmware.elf
```

Keep debug symbols and disable compiler optimisations, as required by GDBMiner. The configured
ELF and the flashed firmware must come from the same build.

## STM32 configuration

Start with [the JSON target's configuration][json-config]. The [shared configuration
reference][configuration] describes the common fields, path resolution and TOML syntax.
Set `GDB.instance = "stm32"`; supported instance values are defined by [the `GDBInstance`
enum][gdb-instance], rather than by this guide.

Set `input_channel = "serial"` from the [`InputChannel` enum][input-channel]. The STM32-specific
fields are:

| Table | Field | Type and meaning |
| --- | --- | --- |
| `GDB.stm32` | `dwt_watchpoint_workaround` | optional bool, defaults to `true`; see below. |
| `GDB.stm32` | `dwt_function_reg` | optional str, first DWT function register; see below. |

The workaround reads DWT registers while single-stepping because ARMv7 DWT watchpoints do not
interrupt single-step execution. `dwt_function_reg` is required when the workaround is enabled
(including its default). Use a quoted hexadecimal address, such as `"0xe0001028"` for this board.
If the workaround is disabled, the register field may be omitted; if supplied, it must be a `str`.
The `[GDB.stm32]` table itself is required. These two fields belong there, not directly in `[GDB]`
or in a top-level `[stm32]` table. See [configuration validation][validation] for the exact rules.

Update the existing `[GDB]` table with these values, then add the target and connection tables.
This is a fragment, not a complete configuration; retain the shared fields from your target TOML
and do not declare `[GDB]` twice.

```toml
[GDB]
instance = "stm32"
gdb_server_path = "st-util -p 4243"
gdb_port = 4243

[GDB.stm32]
dwt_function_reg = "0xe0001028"
dwt_watchpoint_workaround = true

[Connection]
input_channel = "serial"
port = "/dev/ttyACM0"
baud_rate = 9600
```

Choose `BASIC.binary_file`, `GDB.gdb_path`, `GDB.entrypoint` and `GDB.input_buffer` for your
firmware and host. The installed `gdb-multiarch` is an Arm-compatible debugger; the checked-in
PlatformIO GDB path is machine-specific. Choose `GDB.watchpoint_count` within the MCU's hardware
limit; the STM32 examples use four. Check the serial device path before each run.

## Trace and mine

Check `example_firmware/stm32_arduinojson/configuration/configuration.toml`, then run:

```sh
CONFIG=./example_firmware/stm32_arduinojson/configuration/configuration.toml
uv run src/tracer/trace.py --config "$CONFIG"
uv run src/miner/mine.py --config "$CONFIG"
```

Keep the board connected and release the serial port from other applications before tracing.
Mine after all seed traces have completed. Output is written under the configured
`BASIC.output_directory`; see the [shared run workflow][run] for trace and grammar outputs.

[readme]: ../README.md
[configuration]: ../README.md#writing-up-configuration-tomls
[run]: ../README.md#run-local
[json-config]: stm32_arduinojson/configuration/configuration.toml
[gdb-instance]: ../src/tracer/instance/sut_instance.py
[input-channel]: ../src/tracer/connection/sut_connection.py
[validation]: ../src/util/config.py
[stlink-driver]: https://www.st.com/en/development-tools/stsw-link009.html
[platformio]: https://docs.platformio.org/en/latest/core/installation.html#super-quick-mac-linux
