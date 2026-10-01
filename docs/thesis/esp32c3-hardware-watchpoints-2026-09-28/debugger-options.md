# ESP32-C3 debugger options

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record plans the move from the input-access bitmap to raw hardware triggers; the bitmap path has since been removed. Do not run
> the commands below against the current checkout.

Checked 2026-09-28. The Espressif `stable` documentation currently identifies itself as ESP-IDF v6.1.

OpenOCD is the server used by Espressif's documented JTAG workflow. It is not the only documented way to debug a C3:
the guide explicitly offers the firmware GDB stub over serial as an alternative. This does not establish that OpenOCD
is the only possible external debug server. [1]

## What can be swapped

| Layer | Documented options | Consequence |
| --- | --- | --- |
| Debugger frontend | Command-line GDB, Eclipse, VS Code | Changing the UI does not replace the debug server. [1] |
| JTAG adapter | Built-in USB Serial/JTAG, external ESP-Prog, compatible external adapters | Changing the probe does not itself replace OpenOCD or its stepping behaviour. [1][2] |
| External debug server | Espressif OpenOCD in this JTAG guide | The guide describes stock binaries on Linux, Windows and macOS. [1] |
| Firmware debug server | Built-in GDB stub, entered through `idf.py monitor` | Requires firmware configured with `CONFIG_ESP_SYSTEM_GDBSTUB_RUNTIME`. [3][4] |

The C3 uses JTAG, not SWD. The guide explicitly says STM32-specific ST-LINK adapters will not work. ESP-Prog and J-Link
appear as examples of adapter configuration in the OpenOCD documentation section. This does not document a separate
J-Link server workflow. [1][2]

The external-adapter instructions describe switching JTAG from built-in USB to GPIO4–GPIO7 by burning `DIS_USB_JTAG`.
That operation is irreversible. No such change was performed here or is needed for the proposed adapter. [5]

## Why the serial stub does not answer the thesis question

The runtime stub is a documented C3 option, distinct from entering a stub after a panic. It runs on the target and takes
over UART input. The v6.1 component includes a RISC-V implementation. Enabling it in firmware that does not already
contain it changes the executable, so it does not satisfy an experiment on an unchanged target binary. [3][4][6]

These sources do not establish that the runtime stub supports GDBMiner's complete watchpoint-and-single-step workflow.
This note makes no such claim and does not apply panic-only restrictions to the runtime stub.

## Recommended next experiment

Keep stock Espressif OpenOCD and implement C3 trigger handling in GDBMiner's existing target adapter. The local
[probe](README.md) already configured trigger registers through stock OpenOCD without rebuilding or flashing firmware.
OpenOCD documents register reads and writes through `reg`, including forced reads that bypass its register cache. [7]

Keep executable paths, connection details and target configuration in INI files. Record the tested OpenOCD version and
check the required register capabilities. This can make the setup repeatable on another host without distributing a
patched OpenOCD build. It remains an OpenOCD-specific C3 adapter, not a promise of compatibility with every GDB server.

The probe establishes one load access. Full tracing still needs to validate trigger ownership, before-execution stops,
advancing past hits, register caches and restoration, multiple windows, and instruction attribution. A source patch to
OpenOCD is an alternative if the existing command interface proves insufficient, not a prerequisite established so far.

## Sources

1. [Espressif C3 JTAG guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/jtag-debugging/), introduction, how it works, adapter selection and launching debugger.
2. [OpenOCD target configuration](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/jtag-debugging/tips-and-quirks.html#configuration-of-openocd-for-specific-target).
3. [Runtime GDB stub configuration](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/kconfig-reference.html#config-esp-system-gdbstub-runtime).
4. [IDF Monitor](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/tools/idf-monitor.html), GDB integration.
5. [Other JTAG interfaces](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/jtag-debugging/configure-other-jtag.html).
6. [ESP-IDF v6.1 GDB stub build](https://github.com/espressif/esp-idf/blob/v6.1/components/esp_gdbstub/CMakeLists.txt) and [configuration](https://github.com/espressif/esp-idf/blob/v6.1/components/esp_gdbstub/Kconfig).
7. [OpenOCD general commands](https://openocd.org/doc/html/General-Commands.html), `reg` command.
