# ESP32-C3 hardware watchpoints during single-step

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record plans the move from the input-access bitmap to raw hardware triggers; the bitmap path has since been removed. Do not run
> the commands below against the current checkout.

Live experiment, 2026-09-28. The C3 has working hardware read watchpoints. Stock Espressif OpenOCD disables its managed
watchpoints during single-step. A manually configured trigger remained active during the same step and recorded the
access. The bitmap is therefore a workaround for the current debugger path, not an established hardware necessity.

## Results

The probe sends `<a/>` to the existing XML firmware and stops immediately before `lbu a5,0(a5)` at `0x42000064`. The
load address is `buf` at `0x3fc8d680`; the expected byte is 60, ASCII `<`. It uses hardware execution breakpoints and
hardware read triggers. It never reads the firmware bitmap as evidence.

| Test | Result |
| --- | --- |
| GDB `rwatch` plus `continue` | Hardware read watchpoint reported; subsequent stop at `0x42000068`, loaded value 60. Reproduced twice. |
| Same GDB `rwatch` plus `stepi` | Load completes at `0x42000068`, value 60, but zero hardware read-watchpoint events. Reproduced twice. |
| Raw trigger plus `stepi` | PC stays at `0x42000064`, before the load; trigger hit bit is set and `dcsr.cause=2`, hardware trigger. Reproduced twice. |
| Disable raw trigger, then `stepi` | PC advances to `0x42000068`, value 60. Verified in `raw-step-2`. |

The `continue` control also places a temporary hardware breakpoint at the successor instruction to bound the run. Its
GDB output reports both the read watchpoint and the later execution breakpoint. The OpenOCD log independently records a
watchpoint halt at the load PC. The raw-trigger test does not register a GDB watchpoint, so zero GDB watchpoint events
there is expected; CSR values are the evidence.

## Why ordinary stepping misses reads

The installed server is Espressif OpenOCD `v0.12.0-esp32-20260831`. In its matching tagged source,
`riscv_openocd_step_impl()` removes registered watchpoints before stepping, then restores them. It finally sets
`target->debug_reason = DBG_REASON_SINGLESTEP` without reporting a raw trigger cause from this test.

The live `stepi-2-openocd.log` shows:

```text
riscv.c:2844 disable_watchpoints(): Disabling triggers.
riscv.c:1802 riscv_remove_watchpoint(): Removing watchpoint @0x3fc8d680
riscv.c:2875 enable_watchpoints(): Watchpoint 2: needs to be re-enabled.
```

Source locations in archived `riscv.c`: watchpoint removal at lines 4298–4304, restoration at 4340–4344, and forced
single-step reason at line 4359. The `resume_prep()` comment explains the need to step past triggers that fire before an
instruction retires. Simply deleting all trigger-disabling code is not a sufficient fix: execution could repeatedly halt
on the same load.

## Raw trigger result

After releasing the temporary hardware execution breakpoint, the probe programs trigger slot 0 through OpenOCD's debug
register interface:

```text
monitor reg tselect 0
monitor reg tdata1 0
monitor reg tdata2 0x3fc8d680
monitor reg tdata1 0x28001041
stepi
monitor reg dcsr
monitor reg tdata1
```

`0x28001041` selects an RV32 type-2 mcontrol trigger with dmode, machine-mode load matching and debug-mode action. The
trigger reads back as `0x2be01041` before stepping and `0x2bf01041` after stepping. The difference is bit 20, the
hardware hit bit. `dcsr = 0x4003b087` gives `(dcsr >> 6) & 7 == 2`, the trigger halt cause. The PC has not advanced.
OpenOCD nevertheless labels the stop `debug_reason=00000004`, its single-step reason.

Clearing `tdata1` and issuing one more `stepi` completes the watched load. No instruction bytes were replaced. These CSR
writes change debugger configuration, not the firmware executable.

## Reproduce

Run from the `gdbminer.esp32-c3` worktree while no other process owns the board or debug ports. The probe is
intentionally specific to this ELF and board; it checks the ELF hash and live load opcode. Update it deliberately if the
firmware or UART port changes. It resets the board and sends one XML input.

```sh
.venv/bin/python docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/probe.py continue --trial repeat
.venv/bin/python docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/probe.py stepi --trial repeat
.venv/bin/python docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/probe.py raw-step --trial repeat
```

The `stepi` command intentionally exits with an assertion failure when the managed hardware watchpoint fails to fire.
The other two modes pass. Each writes its GDB command file, GDB transcript, and OpenOCD log. Do not run modes
concurrently. The evidence from the controlled repeat runs uses suffix `-2`.

## Setup and limits

- ESP32-C3 revision v1.1, native USB JTAG device `A0:F2:62:01:70:28`.
- CP2102N UART `/dev/cu.usbserial-11110`, 115200 baud. Native USB enumerated as `/dev/cu.usbmodem111201`.
- GNU GDB 17.2 at `/opt/homebrew/bin/gdb`; Espressif OpenOCD at `/Users/dan173/.espressif/openocd-esp32`.
- OpenOCD `board/esp32c3-builtin.cfg`, `ESP_RTOS none`, adapter 1000 kHz. Local ports 3334, 4445 and 6667.
- Existing XML ELF SHA-256: `fce044feb1e09ef205c33e59e4d414506313969d61c1b2b44ee53979f6075c16`.

No firmware was built or flashed. The existing firmware already contains bitmap instrumentation, but the measured event
is the actual input-byte load and all evidence comes from hardware watchpoint stops or debug CSRs. This is not yet a
demonstration on an uninstrumented parser. It establishes that the silicon can report a load match during a step when
the trigger remains enabled.

An initial identity check attempted to read mapped flash before the application had booted and the remote connection
closed. Early setup attempts also encountered a USB enumeration error and a stale UART ready marker. The final probe
opens UART before OpenOCD and clears stale input before continuing from reset. Those setup failures do not establish
watchpoint behaviour. The controlled continue/step/raw-trigger comparisons all reached the same verified load.

The final board check, after clearing triggers and restarting the existing application, sent `<a/>` and received `00
a5`, acceptance followed by ready. Debug processes were stopped.

## Implication for GDBMiner

A debugger-side implementation should retain triggers for observation, report trigger hits and their instruction
context, and deliberately disable the relevant trigger while advancing past a before-execution match. It must restore
triggers and avoid duplicate hits or infinite re-triggering. The raw probe proves the mechanism for one byte load; it
does not yet validate stores, every parser access, multiple watchpoint windows, stack attribution, or a full mining run.

The next experiment should implement that debugger handling and validate a small uninstrumented parser before attempting
the full C3 evaluation. Until then, keep the existing bitmap results labelled as instrumented adaptations. Do not claim
that the C3 intrinsically cannot use hardware watchpoints under single-step.

## Implementation status (2026-09-28, later)

The handoff implementation is partially complete. Evidence lives under
`/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-hw-correction-2026-09-28/`.

Measured after the handoff:

- Bitmap instrumentation was removed from all three C3 parser firmware trees. `nm` confirms neither
  `input_accessed` nor `tracked_read` remains. ELF hashes are in `firmware-SHA256SUMS.txt`.
- `ESP32C3Instance` owns one raw mcontrol slot, withholds before-load halts, retires the load,
  re-arms the trigger and emits a normalized read event before the successor stop.
- Standalone fixture (`fixture.cpp`, not parser firmware): repeated reads, nested-call read,
  store-only byte, and read-before-return all attribute correctly. A 32-bit load hits for every
  watched byte it overlaps (single-slot budget).
- Uninstrumented XML seed `input.2` (`<b/>`) completed four hardware-watchpoint windows against
  ELF `55ea69a2…`. Each window traced 1234 instructions with identical structure, one hit at
  `parse_xml` PC `0x42000066`, and instruction indices 8 / 256 / 566 / 894 for bytes 0..3.
  Caller stack at every hit: `0x42000256`, `0x420055be`. Completion: verified return.

Still required before a full evaluation claim:

- All 20 seeds, then mine/evaluate with board membership queries (handoff §8).
- Reference-library CGI/JSON ports (handoff §5) remain custom diagnostic parsers.
- Multi-slot watchpoint budget and multi-hit wide loads with more than one armed slot.
- Lifecycle stress (interrupted attempt, reconnect) beyond the adapter cleanup paths.

## Primary sources

- [Matching OpenOCD riscv.c](https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/riscv.c#L4264), archived here as `riscv.c`.
- [RISC-V debug CSR definitions in the same tag](https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/debug_defines.h): `CSR_DCSR_CAUSE_TRIGGER=2`, `CSR_MCONTROL_HIT=0x100000`.

## Implementation handoff

[Detailed adapter and evaluation handoff](HANDOFF-hardware-watchpoint-evaluation.md), prepared 2026-09-28.
It records the proposed changes, current source lines, validation gates and fresh evaluation requirements.
