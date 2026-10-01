# ESP32-C3 onboard cgi_decode / json — 2026-09-24

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record describes the firmware input-access bitmap and custom parsers, which were rejected as off-method; the tracer no longer supports the bitmap. Do not run
> the commands below against the current checkout.

Board: ESP32-C3-DevKitM-1-N4X (ESP32-C3 AZ rev 1.1, 4MB XMC flash), serial `/dev/cu.usbserial-11130` (CP2102N).

## Serial / parser

| Target | Seeds | Eval | Total |
| --- | --- | --- | --- |
| esp32-c3_cgidecode (`cgi_decode`) | 20/20 | 1000/1000 | 1020/1020 |
| esp32-c3_json (`parse_json`) | 20/20 | 1000/1000 | 1020/1020 |

json required rejecting leading zeros in `parse_number` (RFC 8259) to match the Python oracle.

## GDB

Espressif OpenOCD `board/esp32c3-builtin.cfg` and `board/esp32c3-ftdi.cfg` both fail: no USB-JTAG and no FTDI probe. Only CP2102N UART is attached.

## Strategy

Input-access bitmap (`input_accessed`) polled after single-step, same as rp2350_riscv. Hardware watchpoints are not used because audited Espressif OpenOCD disables triggers around step.

## Symbols

`cgi_decode`, `parse_json`, `tracked_read`, `buf`, `input_accessed` (C linkage).
