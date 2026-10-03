# ESP32-C3 serial connection simplification

## Scope

Compare [the ESP32 adapter](../../src/tracer/connection/esp32_serial_connection.py) with
[the generic adapter](../../src/tracer/connection/serial_connection.py), then validate the
simplifications on `/dev/cu.usbserial-110` at 9600 baud. No firmware was flashed.
The connected firmware returned the expected JSON acceptance decisions.

This follows the serial-recovery limitation recorded in
[the earlier implementation review](esp32c3-review-2026-10-01.md).

## 1. Keep firmware responsible for input capacity

Remove the optional host-side `max_input_size` limit. It was absent from the example INIs,
so its default disabled it. The firmware already drains packets above its 2048-byte capacity
and returns `0xFF`. Sending an empty substitute packet duplicated that responsibility and
could produce a trace of an input different from the candidate.

Live checks confirmed acceptance of a valid 2048-byte JSON string, rejection of 2049 bytes,
and acceptance of the next `{}` packet. The unit test checks the host's response handling;
it does not emulate or prove the firmware's buffer safety.

## 2. Replace the fixed boot delay with the existing readiness wait

The previous configuration slept for three seconds after releasing reset. Three live
reconnect cycles passed with that delay set to zero, including capacity-boundary packets.
Remove the sleep and the INI entries, including the equivalent sleeps in the standalone
oracle scripts. Those scripts already wait for the firmware's ready marker.

The final adapter's `connect()` took approximately 0.13 seconds on this machine, versus
approximately 3.14 seconds before removal. This measures port opening and reset release,
not complete firmware readiness: `send_input()` still waits for `'A'` and startup quiet.

Do not replace controlled opening with the generic adapter's constructor:

- PySerial's default asserted DTR/RTS produced no UART bytes during a four-second observation.
- Opening with DTR released and pulsing RTS produced boot noise followed by `'A'`.
- These lines control the board's boot/reset circuit, not just serial flow control.

Keep the control-line settings, reset pulse, readiness wait and conditional resend logic.
Do not copy the generic adapter's input-buffer clearing: it can discard the one ready marker
while the firmware is already waiting for the packet length.

## 3. Fix a boot-noise false acceptance found during testing

Force a reset after consuming readiness but immediately before writing an invalid `?` packet.
An instrumented run reproduced a false acceptance on cycle 24. The captured bytes were:

```text
0c bc f5 88 ed dd 4e ef 2e 00
```

The final `00` was boot noise, but `_read_result()` treated it as parser acceptance.
A regression test replayed this prefix and failed before the fix. Once an unexpected byte
reveals boot noise, the reader now ignores result-valued bytes until the next ready marker.

This is not full protocol framing. Noise starting with a valid result byte, or containing a
misleading ready marker, can still be ambiguous. A stronger guarantee would require a separate
protocol change; the current fix addresses the captured failure without claiming that guarantee.

## 4. Validation and limits

After the fix, all 42 forced-reset cycles passed. Each cycle first accepted `{}`, then reset
before sending `?`, checked rejection, and checked three subsequent alternating decisions.
The reset was injected by wrapping the first packet write, asserting RTS for 50 milliseconds,
releasing it, then waiting the listed delay before the write:

| Delay after reset release | Cycles | Writes for the interrupted packet |
| --- | --- | --- |
| 0 seconds | 1 | 2: lost packet resent |
| 0.35 seconds | 1 | 1: no duplicate |
| 0.15 seconds | 40 | 1: no duplicate |

These are UART/EN-reset checks, not GDB-attach tests. The attempted full trace was blocked by:

- OpenOCD could not open the configured USB-JTAG device.
- `example_firmware/esp32-c3_json/build/esp32-c3_json.ino.elf` was absent.

The generic and ESP32 adapters share their packet and acceptance protocol, but opening the
port and surviving resets are board-dependent. Keep the ESP32-specific behaviour until the
full debugger workflow can be checked with the matching ELF and JTAG connection.

Eight serial unit tests, Ruff lint/format checks and `git diff --check` passed. Re-run the
regression checks without hardware using:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_esp32_serial_connection.py
ruff check src/tracer/connection/esp32_serial_connection.py tests/test_esp32_serial_connection.py
ruff format --check src/tracer/connection/esp32_serial_connection.py \
    tests/test_esp32_serial_connection.py
```
