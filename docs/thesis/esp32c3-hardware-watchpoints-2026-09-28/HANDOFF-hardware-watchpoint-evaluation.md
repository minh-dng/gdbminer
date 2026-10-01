# Handoff: ESP32-C3 hardware-watchpoint tracing and evaluation

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record plans the move from the input-access bitmap to raw hardware triggers; the bitmap path has since been removed. Do not run
> the commands below against the current checkout.

Prepared 2026-09-28. Status: implementation plan, not a completed hardware-watchpoint evaluation.

> [!note] Progress after this handoff (same day)
> Adapter + uninstrumented firmware are partially in place. Measured: fixture gates (repeated,
> nested, store-only, before-return, wide-load overlap) and one uninstrumented XML seed (`input.2`)
> with correct per-iteration load-PC attribution. Remaining: 20-seed trace/mine/evaluate, reference
> CGI/JSON library ports, multi-slot budget. See the dated README section “Implementation status”
> and `/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-hw-correction-2026-09-28/`.

## 1. Assignment and boundaries

Implement input-read observation in GDBMiner's existing ESP32-C3 adapter using real hardware triggers and stock,
version-pinned Espressif OpenOCD. Remove tracing-specific firmware instrumentation. Validate instruction attribution,
completion and merging before tracing all seeds. Then mine and evaluate fresh grammars on the board.

Work in `/Users/dan173/Documents/Uni/thesis/impl/gdbminer.esp32-c3`. Preserve existing work and evidence. Do not modify
the S3 worktree or the STM32 reference sources. Do not begin by patching OpenOCD, enabling a firmware GDB stub, adding
software breakpoints, or substituting disassembly-based guesses for hardware read observations.

There are two distinct experimental milestones:

1. **Tracing-method validation:** demonstrate correct hardware tracing on an uninstrumented C3 parser. XML is the
   smallest migration because it already uses LibYxml. A custom CGI/JSON diagnostic can also test the adapter, but must
   remain labelled as a custom target.
2. **Reference-target evaluation:** port the local STM32 reference parser libraries and acceptance wrappers to C3,
   preserving their semantics, then run the three-target evaluation. Replacing the current custom CGI/JSON parsers is
   an experimental-target correction, separate from implementing hardware tracing.

Removing the bitmap requires rebuilding firmware. “Uninstrumented” means the resulting parser executable contains no
tracing-specific bitmap, logging hook, or rewritten input-read helper. It does not mean retaining the old instrumented
ELF byte for byte. Debug symbols, `-O0`, and a documented board I/O wrapper are compatible with this porting experiment.
Keep the selected parser binary fixed across tracing, mining queries and evaluation; record its hash.

The final claim can be “an uninstrumented ESP32-C3 port following GDBMiner's embedded methodology.” It cannot yet be
“an exact reproduction of Table 8”: processor, platform, resolved libraries and historical seed provenance differ.

## 2. Snapshot and preservation

Line numbers below refer to the files inspected on 2026-09-28 at HEAD
`7d6c1e06ed61562f4851ef5aaab9cb8526876a0f`, **including uncommitted changes**. They are navigation hints, not stable
identifiers. See `handoff-source-sha256.json` beside this file for hashes of the referenced source snapshot. Re-read
each function before editing; do not apply patches to line numbers mechanically.

Tracked modifications already exist in `README.md`, `src/tracer/connection/sut_connection.py`,
`src/tracer/gdb_tracer.py`, `src/tracer/instance/stm32_instance.py` and `src/tracer/instance/sut_instance.py`.
The C3 firmware directories, C3 adapter, ESP32 serial adapter, focused tests and evidence directories are untracked.
Save both tracked diffs and relevant untracked sources before editing. A Git diff alone does not preserve this work.
Retain old ELF/bin files and resolved library sources before rebuilding `.pio` output.

Historical results and audit evidence are archived under
`/Users/dan173/Documents/Uni/thesis/experiments/esp32-methodology-audit-2026-09-27`.
Old outputs also originated in `gdbminer.codex-rp2350-setup/output/esp32_*/trial-0`; resolve actual paths before
copying.
Do not overwrite them or relabel them as hardware-watchpoint results.

| Historical instrumented C3 target | Precision | Recall | Interpretation |
| --- | ---: | ---: | --- |
| Custom CGI | 0.988 | 0.971 | Instrumented adaptation; different parser from local STM32 reference. |
| Custom JSON | 1.000 | 0.801 | Instrumented adaptation; permissive handwritten parser. |
| LibYxml wrapper | 0.979 | 0.672 | Instrumented adaptation; wrapper omits end-of-document validation. |

These runs had 20 traces each. Their completion does not establish that firmware bitmap tracing follows the paper's
unchanged-parser observation method. The C3 mutation-fuzzer comparison was also missing.

## 3. Evidence already established

Read [the live experiment](README.md), [debugger options](debugger-options.md), `probe.py`, and the `*-2`/`*-3` logs
in this directory. The following are measured facts, not proposed adapter behaviour:

- Board: ESP32-C3 rev 1.1, native USB JTAG serial `A0:F2:62:01:70:28`.
- Tools: `/opt/homebrew/bin/gdb` 17.2 and
  `/Users/dan173/.espressif/openocd-esp32/bin/openocd`, `v0.12.0-esp32-20260831`.
- Connection: built-in USB JTAG, `board/esp32c3-builtin.cfg`, `ESP_RTOS none`, 1000 kHz.
  Probe ports were GDB 3334, telnet 4445, Tcl 6667. UART was `/dev/cu.usbserial-11110` at 115200 baud;
  native USB enumerated as `/dev/cu.usbmodem111201`. Rediscover ports before use.
- Existing XML ELF SHA-256: `fce044feb1e09ef205c33e59e4d414506313969d61c1b2b44ee53979f6075c16`.
  The experiment did not rebuild or flash it and did not read its bitmap for evidence.
- At `lbu a5,0(a5)`, PC `0x42000064`, address `0x3fc8d680`, input `<a/>`: ordinary GDB `rwatch` plus
  `continue` reports a read; the same watchpoint plus `stepi` misses it. Both were reproduced.
- A manually programmed trigger stays active during `stepi`. The CPU halts **before the load retires**, at the same PC.
  `tdata1` changes from `0x2be01041` to `0x2bf01041`; bit 20 is the hit bit. `dcsr=0x4003b087` gives
  `(dcsr >> 6) & 7 == 2`, the hardware-trigger cause. OpenOCD still reports a single-step stop.
- Disabling that raw trigger and stepping once retires the load: PC `0x42000068`, loaded value 60 (`<`).

Diagnostic command sequence, **specific to the archived ELF and a released slot 0**:

```text
monitor reg tselect 0
monitor reg tdata1 0
monitor reg tdata2 0x3fc8d680
monitor reg tdata1 0x28001041
stepi
monitor reg dcsr
monitor reg tdata1
```

Do not copy the address or slot assumption into the adapter. `0x28001041` is an RV32 type-2 mcontrol configuration
for machine-mode load matching with debug action and dmode. Readback contains implementation-specific supported bits;
validate relevant fields instead of demanding literal equality with the written value.

In the archived matching `riscv.c`, `riscv_openocd_step_impl()` disables managed watchpoints at lines 4298–4304,
restores them at 4340–4344 and forces `DBG_REASON_SINGLESTEP` at 4359. The missing event is therefore not evidence that
C3 hardware cannot observe reads during stepping. However, the raw probe proves only a controlled byte-load mechanism.
It does not yet prove complete tracing, multi-slot behaviour, stack attribution or operation on uninstrumented firmware.

## 4. Smallest implementation boundary

Use `ESP32C3Instance`, which already inherits the serial/server lifecycle from `STM32Instance`. Keep RISC-V trigger
handling in this subclass. Reuse the existing trace format and the normalized `offset` event path. Do not build a new
debugger framework or move RISC-V register logic into the STM32 DWT implementation.

| File and current lines | Required work |
| --- | --- |
| `src/tracer/instance/esp32c3_instance.py:3–7,16–22` | Replace the bitmap-only explanation and implement raw trigger ownership, stepping, normalization and cleanup here. The current override only delegates reset. |
| `src/tracer/instance/sut_instance.py:86–105` | Override `set_watchpoint_and_get_id()` for C3; ordinary `rwatch` uses OpenOCD-managed watchpoints and reproduces the failure. |
| `src/tracer/instance/sut_instance.py:65–67` | C3 deletion must recognize adapter-owned watchpoint IDs and disable their trigger slots instead of sending fictitious IDs to GDB. Delegate real GDB breakpoint deletion. |
| `src/tracer/instance/sut_instance.py:53–63,81–84,107–122` | Existing step/finish/response seams. Use a bounded, correlated command path for register transactions without discarding unrelated MI events. |
| `src/tracer/instance/stm32_instance.py:18–37,40–76` | Reuse configuration/server/serial lifecycle. Reject an enabled bitmap or DWT mode for the new C3 hardware path. |
| `src/tracer/instance/stm32_instance.py:79–164` | Reuse the idea of withholding a stop until observation is complete; lines 135–159 already emit DWT hits before the successor. Do not run the bitmap or DWT poll for C3. |
| `src/tracer/instance/stm32_instance.py:166–228` | Reset, connection and shutdown hooks. Clear C3-owned triggers and pending state on completion, failure, reset and reconnect. Preserve existing serial retry fixes. |
| `src/tracer/gdb_tracer.py:82–93` | Factory already supports `esp32c3`; another factory or backend selector is unnecessary. |

### 4.1 Trigger ownership and command handling

At a verified halted parser entry, resolve each requested watch address through GDB symbols. Track an adapter-owned
ID, trigger slot, byte address and **local window offset**. The current caller constructs `&buf[i]` expressions;
evaluate them rather than parsing their text to infer an address. Slots may be non-contiguous, so slot number is not
the local byte offset.

Read and validate trigger capabilities and register accessibility before using a slot. Select `tselect` before each
slot transaction. Do not overwrite an active execution breakpoint or another owner's trigger. The probe released its
temporary hardware execution breakpoint before using slot 0; production setup needs the same ownership discipline.
OpenOCD reporting eight triggers does not establish eight freely usable byte-read watchpoints.

Start with **one verified data slot**. Determine whether additional slots support the required match semantics and
whether GDB/OpenOCD will reserve or overwrite them during later breakpoint insertion. If data and execution triggers
share resources, account for entry, exit and any `finish` breakpoint. A defensible initial implementation can release
the temporary entry breakpoint, allocate data slots, use verified return completion without an exit breakpoint, and
avoid `finish` by leaving `ignore_functions_regex` empty. It must still verify that OpenOCD preserves the raw slots.
Do not introduce dummy managed watchpoints merely to reserve slots without testing their step-time removal effects.

Use tokenized MI commands, such as `-interpreter-exec console "monitor reg ..."`, with explicit transaction state.
Match the result token, check `^error`, and retain unrelated notifications in order. Console stream output may be
untagged: serialize register commands and collect the stream belonging to the active transaction. Do not treat any
`^done` as the register response. Avoid recursive response polling inside normalization.

OpenOCD documents `reg <name> force` for fresh reads. Verify fresh `dcsr` and selected `tdata1`/`tdata2` access on this
version and the write/flush/readback behaviour before relying on it. Cached CSR values can turn a prior hit into a
false new hit or hide a new hit. A successfully acknowledged write alone does not prove the hardware value changed.
Use deadlines based on the configured timeout; include command, phase, PC and slot state in failure logs.

Reject unsupported capabilities clearly. Do not silently fall back to firmware bitmaps, software watchpoints or guessed
read events. Keep executable paths, ports, input symbols, server arguments and tested slot budget in INI configuration.
Architectural bit definitions belong in the adapter with source comments; they are not arbitrary user tuning knobs.

### 4.2 Required step/event contract

Before a logical step, `instruction_trace_list[-1]` represents the current instruction and its stack. The adapter must
emit all input-read offsets for that instruction **before exactly one completed successor stop**. The raw
before-execution trigger stop must not become a second trace entry at the same PC.

Recommended state flow, to be validated rather than copied as finished code:

```text
logical step requested:
    verify owned triggers are armed and stale hit state is cleared
    remember current instruction context; issue one instruction step

step stop received:
    withhold the stop from GDBTracer
    read fresh halt cause and all owned trigger match state
    if this is a verified ordinary completed step:
        expose the successor stop once
    elif this is a verified owned before-execution read-trigger stop:
        retain all observed local offsets for the current instruction
        disable owned data triggers needed to retire this instruction
        issue one recovery instruction step
        verify normal retirement; abort on unexplained stop/fault/timeout
        re-arm owned triggers with cleared hit state; verify readback
        expose each retained offset, then the completed successor stop once
    else:
        handle a known terminal stop or fail with diagnostic evidence
```

Do not infer completion solely from OpenOCD's `end-stepping-range` message; it masks the raw trigger halt in the probe.
Do not infer retirement solely from PC change either: a branch can legally return to the same PC. Inspect the debug
cause and instruction/stop context. Never use `PC += 4`; C3 supports compressed instructions and branches.

Before-execution recovery is not an unbounded retry loop. If the trigger remains active, the same load can halt forever.
If several armed triggers match one instruction, establish which hit bits are actually reported before disabling them.
A wide load might overlap more than one watched byte without setting every slot's hit bit. Validate that behaviour.
If necessary, use a verified replay strategy to obtain remaining hardware matches before final retirement; otherwise
fail unsupported cases explicitly. Do not fabricate missing byte events from address arithmetic or assume the byte-load
probe establishes wide-load support. This is a gate before increasing slot count or tracing library code.

The normalized event should reuse this existing shape:

```python
{
    "type": "notify",
    "message": "stopped",
    "payload": {"reason": "read-watchpoint-trigger", "offset": local_offset},
}
```

`gdb_tracer.py:271–274` adds the current window base and appends the hit without stepping again. In contrast,
the `hw-rwpt` branch at 256–269 calls `step_instruction()` itself. **Do not emit that branch's event after internally
retiring the instruction**, or the tracer can skip an instruction. Emit offsets in a deterministic order, and
deduplicate
within one instruction only; repeated reads in different instructions must remain separate observations.

Keep the pre-load PC and stack attribution. Stack responses for an earlier request must not be attached to a later
instruction during recovery. Validate this with nested calls. Record the policy for interrupts, exceptions and task
switches; do not quietly discard their instructions or mistake a changed stack for parser return.

### 4.3 Completion, merging and cleanup

- `gdb_tracer.py:141–152` accepts any breakpoint as entry. Verify the expected breakpoint identity/site and invocation.
- At `173–174` and `240–249`, track any configured exit breakpoint and accept only that expected exit. An unrelated
  breakpoint, panic, reset or raw trigger is not successful completion.
- With no explicit exitpoint, `203–216` currently treats a shallower stack as return. Validate unwinding and the
  expected
  caller context on C3. A corrupt/missing stack response must fail the attempt. Preserve the last real instruction's
  hits before popping the successor outside the parser.
- `merge_traces()` at `96–114` silently truncates unequal traces using `zip` and checks only addresses. Require equal
  lengths and compatible instruction/function/stack context before merging windows; report the first mismatch.
  Use explicit exceptions for data validity. Distinguish the initial empty accumulator from a failed empty trace.
  Compare stable context; avoid requiring equality of volatile argument values without justification.
- `trace_input()` at `116–133` requires a positive watchpoint count. Reject zero/negative counts. Each input longer
  than the real slot budget must be replayed across multiple windows. Preserve per-window evidence until validated.
- `trace.py:59–67` writes every returned trace. Ensure a failed/partial attempt cannot become an accepted `.trace`:
  raise on failure and retain diagnostics separately. Require the full expected seed set and successful completion
  metadata before mining. A small sidecar manifest or run validator is sufficient; keep the trace schema if possible.
- Clear owned data triggers before continuing beyond the parser or beginning membership queries. Clear pending events
  across windows and retries. Cleanup must run on exceptions and partial initialization too; leave no stale trigger
  to interrupt a later board user. Do not clear other owners' triggers indiscriminately.

Full input-byte coverage is useful evidence for a known fixture, but **coverage is not completion**. Nor must every
parser read every byte of every input: a legitimate early rejection or skipped byte is possible. Diagnose missing
observations against actual machine loads. Do not “repair” a trace by filling offsets or accepting a timeout after the
last byte was observed. The earlier S3 audit found truncated traces despite complete byte coverage.

## 5. Firmware migration and parser identity

Archive the old builds first. Begin with XML and the minimal fixture; migrate the reference suite after the adapter
passes the gates below. Avoid changing parser semantics while debugging event order.

| Current C3 file | Concrete edit |
| --- | --- |
| `example_firmware/esp32-c3_xml/src/main.cpp:20,23–29,38,83–85` | Delete `input_accessed`, `tracked_read` and bitmap clearing. Change `yxml_parse(&x, tracked_read(&input[i]))` to the direct `input[i]` read. Preserve parser control flow at 33–45. |
| `example_firmware/esp32-c3_cgidecode/src/main.cpp:18,51–57,62,72–73,128–130` | For a diagnostic-only custom CGI build, remove bitmap/helper/clear and restore direct reads. Preserve the `input_length` bound check at 69–71; it is also used for safety and is not merely bitmap state. |
| `example_firmware/esp32-c3_json/src/main.cpp:19,21–27,29–214,264–266` | Removing bitmap/helper/clear yields an uninstrumented custom parser only. The final reference-target run should replace this handwritten parser with the library below. |

Reference sources are read-only inputs to the port:

- **CGI:** `example_firmware/stm32_cgidecode/platformio.ini:32` selects
  `dojyorin/percent_encode@^2.0.1`; `example_firmware/stm32_cgidecode/src/main.cpp:118–138` includes
`arduino_percent.hpp`, calls `percent::decode`
  at 127, then applies a result-byte acceptance check at 129–138. Use the active library call, not the dead custom
  `cgi_decode` function elsewhere in the same file. Check `char` signedness and high-byte acceptance on both builds;
  copying the source does not guarantee identical observable semantics across architectures.
- **JSON:** `example_firmware/stm32_arduinojson/platformio.ini:32` selects
  `arduino-libraries/Arduino_JSON@^0.2.0`. Its `example_firmware/stm32_arduinojson/src/main.cpp:39–51` uses `JSON.parse`
and rejects `undefined`.
  This is **Arduino_JSON**, not the different ArduinoJson library. Replace the custom C3 parser for the reference suite.
  The existing C3 string parser at 39–62 permits invalid escapes and skips the escaped byte after a backslash.
  Fixing that handwritten parser would create another target; it would not restore library identity.
- **XML:** `example_firmware/stm32_libyxml/platformio.ini:31` selects `julstrat/LibYxml@^1.0.2`;
  `example_firmware/stm32_libyxml/src/main.ino:41–54` initializes and feeds Yxml without calling `yxml_eof`. Preserve
that acceptance policy for the
  reference-matched run. A stricter EOF check is a separate oracle variant and needs separate results.

Pin the **resolved** library/platform/toolchain versions and source hashes. The current `^` constraints are not exact
pins. In all C3 `platformio.ini` files, line 5 is unpinned `espressif32`, lines 6–7 use a machine-local toolchain path,
and lines 12–24 request debug/`-O0`. Capture verbose compilation to verify actual flags for parser libraries too.
Document portable installation of the tested toolchain; do not assume another host has this absolute package path.

Keep the serial ready/result protocol and bounded input buffer. Record the capacity, terminator policy, empty-input
policy, embedded-NUL behaviour and oversized-input rejection. The current C3 capacity is 128 bytes, whereas local
STM32 wrappers use larger buffers. Match the intended reference capacity where practical, with a safe terminator
allocation; do not copy the STM32 JSON receive-loop overflow/off-by-one behaviour. Any retained size restriction is
part of the measured oracle and must be reported. Never discard oversized generated cases to improve precision.

Confirm bitmap/helper symbols are gone with the ELF symbol table and disassembly. Check direct parser loads in the
disassembly. Firmware hash, source hash and the actual flashed image must agree. Reading debug CSRs changes debug
configuration, not parser code. Ensure GDB inserts hardware execution breakpoints rather than patching instructions.

## 6. Configuration changes

Create separate hardware-evaluation configs/output roots after archiving the old configs. Do not mix old traces with
new ELF files. Current locations to edit:

| Configuration | Relevant lines |
| --- | --- |
| `example_firmware/esp32-c3_cgidecode/configuration/configuration.ini` | Paths 5–8; UART 12; GDB/server 20–25; tracing 27–38. |
| `example_firmware/esp32-c3_json/configuration/configuration.ini` | Paths 5–8; UART 12; GDB/server 20–24; tracing 26–37. |
| `example_firmware/esp32-c3_xml/configuration/configuration.ini` | Paths 5–8; UART 13; GDB/server 21–25; tracing 27–39. |

Required settings, adapting paths and symbols to the final build:

```ini
[GDB]
instance = esp32c3
watchpoint_type = (char*)
watchpoint_count = 1
dwt_watchpoint_workaround = false
dwt_function_reg = 0
ignore_functions_regex =
input_buffer = buf
```

`watchpoint_count = 1` is the conservative initial validation budget, not a measured maximum. Increase only after slot
and multi-match validation. Remove `input_access_bitmap` and `input_access_bitmap_size`; do not set them to a new
symbol. The dummy DWT address is currently required by the inherited constructor, even when the workaround is off;
retain it or make the smallest compatible optional-config change.

Update entry symbols when switching libraries. Choose an entry boundary that includes every parser input read and
excludes UART reception; compare with the local STM32 entry configuration. Verify the actual resolved PC and return
boundary. Do not blindly retain `cgi_decode` after moving to `percent::decode`.

Empty `ignore_functions_regex` initially avoids `finish` at `gdb_tracer.py:290–295`, which can allocate a breakpoint
and skip read observation. Add ignores only after proving they skip no relevant input access and do not conflict with
raw triggers. Keep the actual UART/device/server settings in config; the checked-in `/dev/cu.usbserial-21130` is stale
relative to the last probe. Revalidate reset/ready behaviour instead of changing `reset_on_connect` blindly.

## 7. Validation gates before a full run

Use Python 3.12 and the repository's existing lint/type tooling. Preserve the serial regression tests already present.
Debugger behaviour cannot be validated with lint alone. Add a small runnable regression for event ordering and merge
rejection, plus live checks of the implemented adapter. Avoid a new test framework.

1. **Command/ownership gate:** verify forced CSR reads, write visibility, supported fields, slot isolation and cleanup
   with stock OpenOCD. Check another hardware execution breakpoint does not overwrite the data slot. Unsupported
   capability or command errors must terminate with evidence, not hang or silently switch modes.
2. **Uninstrumented fixture gate:** use a tiny ordinary function with known input reads and known expected output,
   compiled for this board. Verify actual instructions in disassembly. No bitmap or target-side read logging. Exercise
   a read, a no-read control, a write-only control, repeated reads, a read in a nested call and a read immediately
   before
   return. Read-only triggers must not report the store as an input read.
3. **Instruction-shape gate:** cover compressed instructions/branches around a read, and wider/unaligned accesses that
   the final parser/compiler can produce. Establish overlapping-slot behaviour. Log any unsupported access pattern;
   do not proceed with a parser that exercises it. Test the last watched byte and the boundary between windows.
4. **Event-order gate:** feed recorded or minimal synthetic MI sequences through normalization. Assert all hit events
   precede one successor, that the raw pre-load stop is withheld, and that an error/timeout cannot look like successful
   completion. Verify hit-clear/re-arm and no duplicate events across repeated reads or successive windows.
5. **Replay gate:** force an input longer than the slot budget through at least two windows. Require identical stable
   instruction/stack sequences before unioning hits. Reject unequal lengths and the first divergent instruction.
   Repeat one input to check deterministic replay. If task/interrupt activity breaks this, diagnose and document the
   execution policy before increasing the workload.
6. **Lifecycle gate:** test normal return, a deliberately interrupted attempt, reconnect and the next input. Confirm
   no stale trigger/event survives. Verify a serial timeout or ready-marker reset is distinguishable from rejection.
7. **Real-parser gate:** complete one seed through trace, mine and board queries using uninstrumented XML. Inspect
   load-PC attribution and caller stacks. Only then trace all 20 seeds and migrate/run the remaining parser libraries.

The success criterion is a faithful trace, not matching the old bitmap grammar or obtaining a high score. The grammar
may change when instrumentation disappears or the actual parser library is restored. Retain that difference as evidence.

## 8. Evaluation rerun

Follow the embedded experiment in the paper: one documented set of 20 high-quality seeds per target, hardware
watchpoint windows merged into complete traces, mining with board membership queries, precision on 1,000 generated
inputs, recall on 1,000 golden-grammar inputs, and mutation-fuzzer acceptance comparison. Record tracing/mining times.
The paper's 50-trial Linux evaluation is not a requirement to claim one embedded run.

### 8.1 Inputs and oracle

Archive exact seed and recall-corpus bytes with hashes before the run. Existing C3 corpora match the local STM32
corpora, but exact historical-paper provenance is not established. Keep that distinction in the report. Do not silently
replace seeds, add convenient seeds after seeing results, or drop golden inputs rejected by the actual target.

Separately measure golden-corpus disagreement with the board oracle. This explains parser/corpus mismatch; it must not
be used to redefine recall after the fact. Preserve the XML no-EOF acceptance policy when making the comparison.

`src/tracer/connection/esp32_serial_connection.py:51–59` can send an empty packet for a configured oversized input
and force rejection. If used, record this as wrapper rejection, not execution of the original candidate by the parser.
Lines 62–77 wait for `00`/`FF` and resend after ready; missing replies are not valid acceptance decisions. Keep
transport failures separate, bound retries at the workflow level, and do not silently count failures as parser
rejection.
If touching packet encoding at line 57, use explicit little-endian `<I` to match the board protocol across hosts.
Preserve the process/queue cleanup fixes in `sut_connection.py:30–59,64–76` and their existing focused tests.

### 8.2 Artifact isolation and commands

Use a fresh, target-specific output base, for example `output/esp32c3_hw_xml_<run-id>`. `trace.py:17–27` creates a
trial subdirectory; `mine.py:235–243` selects the latest trial and sorts traces/seeds. Before mining, verify there are
exactly the intended 20 complete traces, paired by seed identity, all built from this ELF and configuration. Do not
leave a later failed trial in the same base and let “latest” select it accidentally.

Command template after implementation, configuration, build, flashing and validation gates are complete:

```sh
cd /Users/dan173/Documents/Uni/thesis/impl/gdbminer.esp32-c3

# Set these to the new config, its actual completed trial, and an existing evidence directory.
c3_config='path/to/new-hardware-evaluation.ini'
c3_trial='output/esp32c3_hw_xml_RUN/trial-0'
c3_evidence='path/to/run-evidence'

PYTHONPATH=src .venv/bin/python src/tracer/trace.py --config "$c3_config" \
  > "$c3_evidence/trace.log" 2>&1

# Run the completion/window/seed validator here. Stop if it fails.
PYTHONPATH=src .venv/bin/python src/miner/mine.py --config "$c3_config" \
  > "$c3_evidence/mine.log" 2>&1

PRECISION_SET_SIZE=1000 PYTHONPATH=src .venv/bin/python src/eval/precision_recall.py \
  --config "$c3_config" --grammar "$c3_trial/parsing_g.json" \
  --out "$c3_evidence/precision-recall.json" > "$c3_evidence/precision-recall.log" 2>&1

PRECISION_SET_SIZE=1000 PYTHONPATH=src .venv/bin/python src/eval/compare_fuzzers.py \
  --config "$c3_config" --grammar "$c3_trial/parsing_g.json" \
  > "$c3_evidence/compare-fuzzers.log" 2>&1
```

These are individual stages, not an unattended paste-and-run script. Check each exit status and artifact gate before
starting the next. Run targets sequentially with exclusive board ownership; verify the flashed image before each one.

### 8.3 Preserve denominators and fuzzer identity

`precision_recall.py:19,58,61–70` uses `PRECISION_SET_SIZE` and the bundled `LimitFuzzer` for precision.
Recall at 78–93 iterates all files in `eval_directory`; setting the environment variable does **not** ensure 1,000
recall inputs. Verify the corpus count separately. Earley parsing uses a 10-second timeout; report timeouts separately
from ordinary parse rejection. The `no_tested_inputs` field at 98–99 is the miner's membership-query count, not the
precision sample count.

`compare_fuzzers.py:46–54,63,69–87` uses local `MutationFuzzer` and `CoverageFuzzer` and currently logs accepted
counts. `src/eval/grammar.py:180,204` contains the mutation implementation and seed-first behaviour. The paper describes
a fuzzingbook mutation baseline. Verify the intended version, algorithm, mutation parameters, seed ordering and
treatment
of initial seeds; use the matching baseline or explicitly label the local implementation as a deviation. Do not claim
equivalence from the class name. Also document that the comparison's grammar generator differs from `LimitFuzzer`.

Save all generated candidates and decisions, including accepted ones. Current logs alone do not do that. Add the
smallest output capture needed around these evaluation loops; record PRNG seed/state and package versions. Preserve
1,000 attempted samples per precision/baseline arm with clear accepted/rejected/transport-failed counts. Do not filter
by length, uniqueness or successful response without reporting the changed sampling procedure and denominator.

## 9. Deliverables and completion criteria

The next agent should leave:

- A small C3 adapter implementation, the necessary shared trace-validity fixes, and focused runnable checks.
- Uninstrumented C3 firmware sources, resolved parser/toolchain versions, build logs, ELF/bin hashes and flash identity.
- Separate configs and retained old bitmap evidence; no old trace paired with a rebuilt ELF.
- One live instruction-level evidence package showing hardware hits, recovery, correct PC/stack attribution and cleanup.
- For each final target: 20 completed seed traces with per-window validation, a fresh grammar, mining-query count,
  tracing/mining times, 1,000 precision decisions, 1,000 recall outcomes and the documented mutation comparison.
- A run manifest containing Git HEAD plus dirty-source snapshot, Python/dependency/tool versions, board identity,
  debugger arguments, actual slot budget, input policy, seed/corpus hashes, commands, retries, failures and output
hashes.
- Updated Obsidian methodology/results notes distinguishing the archived instrumented results, the diagnostic hardware
  milestone, and the reference-library hardware evaluation. Leave S3 results and limitations separate.

If a gate fails, report the exact instruction/access pattern and smallest reproducer, retain its logs, and mark the run
incomplete. A well-supported limitation is a valid thesis result; fabricated completeness is not. A patched OpenOCD
build is a fallback only if a demonstrated limitation of the stock register interface prevents correct adapter handling.

Suggested commit boundaries, once changes are ready: C3 trigger handling and its check; trace completion/merge guards;
uninstrumented/reference-library firmware and configs; evaluation evidence/reporting. Use conventional commit titles
and preserve unrelated dirty changes. Do not commit massive generated artifacts unless intentionally selected.

## 10. Sources and related records

- Eisele et al., *GDBMiner: Mining Precise Input Grammars on (Almost) Any System*, 2025,
  [DOI 10.4230/LITES.10.1.1](https://doi.org/10.4230/LITES.10.1.1): §4.1 (PDF p. 14), ARM DWT polling during
  stepping; §5 (p. 15), precision/recall definitions; §5.4 (pp. 20–22), embedded watchpoint windows and 20-seed run.
  Local STM32 configuration uses `st-util` with ST-Link/SWD; C3 uses JTAG and a different debug-register implementation.
- [Matching Espressif OpenOCD source](https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/riscv.c#L4264), also archived as `riscv.c` here.
- [Debug CSR definitions](https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/debug_defines.h), including trigger halt cause and mcontrol hit bit.
- [Espressif C3 JTAG guide, v6.1](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32c3/api-guides/jtag-debugging/index.html).
- [OpenOCD register commands](https://openocd.org/doc/html/General-Commands.html). This adapter is specific to the
  tested C3/OpenOCD interface. Configurable paths make it deployable on another supported host; they do not make
  `monitor reg` universal across GDB servers.
- Obsidian, `Uni/Thesis/Replication/ESP32-C3 hardware watchpoints during single-step 2026-09-28.md` and
  `ESP32-C3 and S3 methodology audit 2026-09-27.md`.

This handoff changes documentation only. No adapter implementation, rebuild, flash or evaluation was performed while
writing it.
