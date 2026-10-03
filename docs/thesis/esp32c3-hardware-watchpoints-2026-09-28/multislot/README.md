# ESP32-C3: eight-slot hardware-watchpoint validation

> Subsequent change: the JSON target has now been restored to Arduino_JSON. See the
> [reference-library port and tracing blocker](../../esp32c3-arduino-json-2026-09-28/README.md).
> This report and its timings remain measurements of the archived **custom** parser. Reproducing them requires that
> archived firmware/configuration, not the current JSON build.

Status: passed on the connected ESP32-C3, 2026-09-28. Eight simultaneous read triggers, complete JSON trace equivalence,
byte and wider-load fixtures, and interruption cleanup were validated. The JSON evaluation configuration now uses eight
slots. The full 20-seed evaluation has **not** been restarted.

## Question and boundary

The previous adapter deliberately used one raw trigger. OpenOCD reporting eight triggers did not establish that eight
simultaneous read triggers would work during instruction stepping. This experiment tests that capability rather than
removing the count guard on assumption.

This follows the [hardware-watchpoint handoff](../HANDOFF-hardware-watchpoint-evaluation.md). It does not reinstate the
firmware bitmap, patch OpenOCD, or change the parser source. The standalone `fixture.cpp` is a diagnostic target, not a
new dependency or instrumentation added to any parser.

## Preservation

At the user's request, the running JSON trace was stopped. Its seven completed trace files remain in
`output/esp32c3_hw_json_2026-09-28/trial-0/` (moved on 2026-10-01 to `~/Documents/Uni/thesis/experiments/esp32c3-superseded-output-2026-10-01/`), with an `INTERRUPTED.txt` marker. That trial is incomplete and must not be
used as a completed evaluation. Its slot-0 trigger was disabled and its debugger/server processes were shut down.

The pre-change adapter, host checks, tracer and evaluation configuration were copied to:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-multislot-2026-09-28/before/
```

Historical checksum manifests and firmware paths recorded in those manifests remain unchanged. Current firmware names
remain `example_firmware/esp32-c3_{cgidecode,json,xml}/`.

## Measured register gates

Board: ESP32-C3 revision 1.1, native USB JTAG serial `A0:F2:62:01:70:28`, UART `/dev/cu.usbserial-11110`.
Tools: GDB 17.2 and stock Espressif OpenOCD `v0.12.0-esp32-20260831`, 1000 kHz, `ESP_RTOS none`.

The existing, uninstrumented custom JSON ELF was used without rebuilding or flashing for these probes:

```text
25d45f4fd47e1aaab8fa0f1292d3ded97d96bcdc698a0c683ddada32765af17f
```

1. Halt at the temporary hardware parser-entry breakpoint; let GDB remove it.
2. Verify that each slot is inactive before claiming it.
3. Program all eight slots, then force-read every selected `tselect`, `tdata1` and `tdata2`.
4. Verify the exact-match, machine-mode load/debug-action fields, while ignoring supported implementation bits.
5. Step until a load match, examine fresh `dcsr` and every trigger's hit bit, recover, and restore the inactive slots.

| Probe | Observation |
| --- | --- |
| Eight distinct addresses, `buf[0]` through `buf[7]` | All eight retain the required configuration simultaneously. The first byte load hits only slot 0. |
| Eight slots aliased to `buf[0]` | All eight hit bits are reported together for the same load at `0x4200009e`. |
| Retirement after disabling observed matches | The load completes at `0x420000a2`. |
| Cleanup | Every claimed slot is restored to its previous inactive state, with forced readback. |

The alias result proves simultaneous match reporting for one byte load. It is not, by itself, proof of the semantics of
an aligned or unaligned wider load. Those are separate fixture checks.

## Adapter change

`src/tracer/instance/esp32c3_instance.py` now accepts a configured budget of 1–8 contiguous slots beginning at
`hardware_trigger_slot`. Every watchpoint owns a separate record: hardware slot, watched address, local window offset,
previous register state, and initialization state. Hardware slot numbers are not emitted as input offsets.

Each logical step:

1. Verifies all owned triggers, using one serialized, token-correlated register transaction for the window.
2. Withholds raw before-load stops from the tracer.
3. Records only hardware-reported matches and disables only those matched slots.
4. Steps again with unmatched slots still armed. Every further trigger stop must reveal a new match at the same PC.
5. Requires ordinary step retirement within at most `number of slots + 1` physical steps.
6. Rearms the disabled slots with fresh readback, then emits sorted offsets before exactly one successor stop.

This bounded recovery also covers a device that reports matching triggers in priority order. It never infers missing
read events from instruction width or address arithmetic. Cleanup attempts every owned slot even if releasing another
slot fails. Managed breakpoints and `finish` remain prohibited while raw slots are owned.

## Reproduction

Run from the repository root with exclusive board ownership and the ELF matching the flashed image:

```sh
PYTHONPATH=src .venv/bin/python \
  docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/multislot/probe_slots.py \
  --config example_firmware/esp32-c3_json/configuration/configuration.hw-eval.ini \
  --out /path/to/new-alias-evidence --alias

PYTHONPATH=src .venv/bin/python \
  docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/multislot/compare_windows.py \
  --config example_firmware/esp32-c3_json/configuration/configuration.hw-eval.ini \
  --input /path/to/nine-byte.json --out /path/to/new-comparison
```

The comparison fixture contains the nine bytes `"abcdefg"`. Eight-slot tracing therefore needs a full eight-byte
window and a one-byte tail. One-slot tracing needs nine windows. The comparison requires identical completed
instruction/function/stack sequences **and** identical per-instruction read offsets. It retains each window separately
and writes diagnostic JSON rather than mining-ready `.trace` files.

## Completed trace comparison and timing

For the nine-byte JSON value `"abcdefg"`, both budgets produced the same 326 instruction/function/stack entries and the
same 26 per-instruction input-read observations. The comparison checked every entry, not just total byte coverage.

| Budget | Full parser replays | End-to-end tracing time |
| --- | ---: | ---: |
| One slot | 9 | 354.59 s |
| Eight slots | 2 (eight bytes, then one byte) | 89.46 s |

This is a measured **3.96× speedup** for this seed, including debugger/server and UART setup. It is not an eightfold
speedup claim for the full corpus: more registers must be polled per instruction. A 33-byte seed now requires five
parser replays rather than 33, but its actual wall time remains to be measured.

## Instruction-shape and lifecycle gates

The separate fixture ELF hash is:

```text
44918dc84643750999e884a3f20107312f5cd49990db373bd646a421eca7c42b
```

The fixture was built and temporarily flashed only for these checks. It contains ordinary volatile reads/stores and a
UART wrapper, not input-tracking instrumentation. The generated instructions are retained in the disassembly files.

| Gate | Measured result |
| --- | --- |
| Byte reads, eight slots plus tail | Two complete, matching 230-instruction windows; 10 reads: byte 0 twice and bytes 1–8 once each. |
| Nested calls | Slots 1–7 report `nested_read` at `0x42000030`, with caller stacks retained. |
| Store exclusion | `sb` at `0x420000a4` produces no read observation; the earlier read of that byte remains correctly attributed. |
| Last input read | Byte 8 reports at `0x420000c0` before return, in the partial final window. |
| Compressed aligned word load | `c.lw` at `0x420000e6` reports offsets 0, 1, 2, 3 at that one instruction. Its seven-instruction trace completes. |
| Unaligned word load | `lw` at `0x42000102` reports offsets 1, 2, 3, 4 at that one instruction. Its nine-instruction trace completes. |
| No-read controls | The byte-8 tail window for each wider-load fixture completes with zero input-read events. |
| Deliberate interruption | Aborting with eight armed slots, and with two slots temporarily disabled, releases all owned slots with verified readback. |
| Reconnect | All eight trigger slots read inactive. |

The aligned and unaligned loads each reported all four matching slots on the same before-load halt. Priority-ordered
matches are additionally covered by a host regression; that alternative reporting pattern was not observed on this
board. These cases do not establish support for every possible instruction, exception or interrupt pattern.

The 23 host checks pass, including multiple hits before one successor, bounded recovery, foreign-slot protection,
slot/offset separation, partial initialization, and cleanup continuing after an individual slot failure. Ruff and
BasedPyright also pass for the changed Python code.

## Evidence and remaining gates

Small register-probe results and disassembly are retained alongside this note. Larger build, flash and trace logs live
under `experiments/esp32c3-multislot-2026-09-28/` outside the repository.

The original JSON firmware was restored after the fixture tests. Its ELF hash is unchanged; the flash tool verified
the written images. A bounded UART check then accepted `"abcdefg"` (`00`) and rejected `?` (`ff`). No debugger/server
process remains running.

Both JSON configurations now set `watchpoint_count = 8` and `hardware_trigger_slot = 0`. Their output bases are fresh:

- `configuration.hw-eval.ini`: `output/esp32c3_hw_json_8wp_2026-09-28/`.
- `configuration.ini`: `output/esp32-c3_json/hardware-8/`.

CGI and XML configurations remain at one slot; their target-specific eight-slot smoke checks were not performed here.
The adapter accepts 1–8 slots, but rejects out-of-range budgets, active foreign slots, ignored functions, and configured
exit breakpoints. Entry breakpoints are released before data-slot allocation. Interrupts remain masked during stepping
(`dcsr.stepie = 0`).

To start a fresh JSON trace run, with exclusive board access:

```sh
PYTHONPATH=src .venv/bin/python src/tracer/trace.py \
  --config example_firmware/esp32-c3_json/configuration/configuration.hw-eval.ini
```

Verify the complete expected seed set and successful trace/window completion before mining. No new precision, recall
or mutation-baseline result is claimed here. The current CGI/JSON targets remain custom diagnostic parsers, not
restored STM32 reference libraries. No new external papers were used; the sources are those already in the handoff.
