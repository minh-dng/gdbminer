# ESP32-C3: restore the STM32 Arduino_JSON target

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record uses `configuration.hw-eval.ini`, `rom_unwinder` and ROM unwind rules, which were removed when runtime functions became skipped with `finish`. Do not run
> the commands below against the current checkout.

2026-09-28, updated 2026-09-29. **Firmware port built, flashed and functionally checked. Loading matching ROM symbols
restores the first failing caller chain. A debugger-only `memset` unwind rule now enables a complete `{}` trace,
matching eight-slot and one-slot runs, a mined smoke grammar and live evaluation. The full 20-seed run subsequently
stopped on another runtime unwind failure (`Unexpected parser return stack: ['0x00000007', '0x0']`). No full-corpus result
is claimed. The target is now migrating to a matched official Arduino-ESP32 build; see
[the current build instructions](../../../example_firmware/ESP32-C3%20DevKitM-1-N4X.README.md#arduino-build).**

This corrects parser identity after the [eight-slot hardware-watchpoint validation](../esp32c3-hardware-watchpoints-2026-09-28/multislot/README.md).
That earlier validation used the custom diagnostic JSON parser. Its measurements must not be relabelled as results for
Arduino_JSON.

## 1. What is now matched to STM32

The reference is `example_firmware/stm32_arduinojson/`, which remains unchanged.

| Property | C3 port |
| --- | --- |
| Parser library | `arduino-libraries/Arduino_JSON@0.2.0`, not the different ArduinoJson library |
| Bundled parser | cJSON 1.7.14, from the resolved Arduino_JSON package |
| Parser wrapper | Same `JSON.parse((const char*) input)` call and `JSON.typeof(myJSON) == "undefined"` rejection rule |
| Input capacity | 2,048 payload bytes |
| UART protocol | 9,600 baud; `'A'` ready byte; four-byte length, payload, then `00` accept or `ff` reject |
| Tracing entry | `cJSON_Parse`, matching the STM32 configuration |
| Seeds and recall corpus | All 20 seeds and all 1,000 evaluation files match the local STM32 copies by name and SHA-256 |

The parser function bodies match after removing whitespace and comments. The handwritten `parse_json`, `parse_value`,
`parse_string`, `parse_number`, and other custom parser helpers have been removed. ELF symbols confirm the library's
`cJSON_Parse` and the wrapper `parser`; no bitmap or `tracked_read` symbols are present.

The STM32 INI declares `Arduino_JSON@^0.2.0`. The C3 pins 0.2.0 exactly rather than retaining a floating range. A local
resolved STM32 library build was not available here, so this is a match to its declared library and base version, not a
claim that a historical STM32 ELF used this exact package resolution.

The existing Espressif platform/toolchain selection was not changed. Verbose build output confirms `-O0` for the wrapper,
`JSON.cpp`, `JSONVar.cpp`, and `cJSON.c`. Source and resolved library hashes are retained with the evidence.

## 2. Necessary differences, not parser instrumentation

### Board transport

“Transport” means delivering input bytes to the board and reading the result. It does not mean changing how JSON is
parsed. The earlier different baud rate and `0xa5` marker were not required by C3 hardware and have been removed.

The C3 still needs its actual UART device path and the existing `esp32-serial` host channel. That channel opens the
CP2102N UART with controlled DTR/RTS states so the board is not accidentally held in reset/download mode. The STM32
uses its own serial device and does not require that C3 reset-line handling.

The firmware yields with `delay(1)` while waiting for UART data, allowing the ESP32 runtime to run, and flushes outgoing
ready/result bytes. The C3 LED fallback is GPIO8 rather than the STM32 fallback of 13. These changes sit outside the
parser boundary; the parser/library contains no added input-tracking hooks.

### Safe termination at the intended capacity

The STM32 source declares:

```cpp
#define FUZZ_INPUT_SIZE 2048
uint8_t buf[FUZZ_INPUT_SIZE];
// ... only rejects response_length > FUZZ_INPUT_SIZE ...
buf[response_length] = 0;
```

An array of 2,048 bytes has valid indices 0–2,047. A length of exactly 2,048 passes the size check and fills those bytes,
then the terminator write accesses `buf[2048]`, one byte outside the array. This is undefined behavior: it can corrupt
adjacent data or appear to work. It is not a valid extra byte merely because the value being written is zero.

The C3 port keeps the intended 2,048-byte payload limit and allocates space for its terminator:

```cpp
uint8_t buf[FUZZ_INPUT_SIZE + 1];
```

For packets larger than 2,048 bytes, the C3 drains the declared payload and sends `ff`, then returns to the ready/input
exchange. The STM32 reference instead hangs in its oversized-input branch. This is a documented wrapper-safety
difference, not a replacement parser or a filter that discards inconvenient evaluation samples. The host sends the
actual oversized candidate; rejection occurs at the firmware wrapper.

No STM32 file was modified to fix its bug: it remains the read-only reference for the comparison.

## 3. Build and live oracle checks

The built and flashed ELF is:

```text
ba726aef31242a55a798183c1ba130740207f8e1fca407e94b20df3f81e4d8fc
```

The flash tool verified the written images. `check_oracle.py` ran the following bounded UART checks both before and
after the failed tracing smoke test:

| Input/check | Observed result |
| --- | --- |
| `{}` | Accept |
| `[1,true,"x"]` | Accept |
| Invalid escape `"\q"` | Reject |
| `?` | Reject |
| Empty input | Reject |
| `{}junk` | Accept |
| `{}` followed by NUL and `?` | Accept |
| Valid JSON string of exactly 2,048 bytes | Accept |
| Valid JSON string of 2,049 bytes | Wrapper rejection |
| `{}` immediately after the oversized packet | Accept; packet alignment retained |

The trailing-data and embedded-NUL results reflect the reference's C-string/cJSON prefix parsing. They were not made
stricter, because that would create a different acceptance oracle. These checks are not precision/recall measurements.
The existing 23 host checks, Ruff, and BasedPyright also pass.

Reproduce the oracle check with exclusive UART access and this firmware already flashed:

```sh
.venv/bin/python docs/thesis/esp32c3-arduino-json-2026-09-28/check_oracle.py \
  --config example_firmware/esp32-c3_json/configuration/configuration.hw-eval.ini \
  --out /path/to/new-oracle-evidence
```

## 4. Tracing gate: incomplete, not silently accepted

A smoke trace of `{}` entered `cJSON_Parse` using the configured eight-slot budget; this two-byte seed needs only two
active data slots. During allocation, execution reached `tlsf_ffs` inside `tlsf_malloc` at `0x403894b4`, then ROM
`__clzsi2` at `0x4000079c`. GDB supplied a shortened, repeating caller stack:

```text
['0x403894b8', '0x403894b8', '0x403894b8', '0x403894b8', '0x00000000', '0x0']
```

The validator raised `Unexpected parser return stack` rather than treating this as a successful return. The attempt is
recorded as incomplete, with zero completed windows. Both owned triggers were released and the debugger/server exited.
The subsequent oracle checks passed again.

The STM32 configuration ignores allocation and other runtime functions using `finish`. The current C3 adapter rejects
that strategy while it owns raw trigger slots: skipping calls and allocating managed return breakpoints require their
own correctness/ownership checks. The STM32 ignore list was therefore **not** copied blindly. No allocator substitute,
parser edit, guessed stack, or bitmap fallback was added to force a passing trace.

### 2026-09-29: restore ROM function boundaries

The failure reproduces without data triggers: continue from `cJSON_Parse` to a temporary hardware breakpoint at
`0x4000079c`, then request the stack. This isolates stack unwinding from the raw-trigger stepping implementation.
Flushing GDB's register cache leaves the truncated stack unchanged.

At that same halt, loading the installed `esp32c3_rev101_rom.elf` restores the stack through `cJSON_Parse` and all its
original callers. OpenOCD reports chip revision v1.1. The ROM ELF has symbols but reports no debugging symbols; the
result supports missing ROM function boundaries as the cause, not a claim that new DWARF unwind data was supplied.
The address `0x4000079c` is the `__call___clzsi2` trampoline, which jumps to `0x40054882`.

The C3 adapter now accepts optional `[GDB] rom_elf` and loads it after the firmware symbols, before target connection.
Both Arduino_JSON configurations select the installed revision-101 ELF. Match this file to the connected chip; do not
reuse it blindly for another revision. A missing file or rejected GDB command fails startup rather than being ignored.
Other targets and C3 configurations without `rom_elf` retain their existing startup path.

`check_rom_stack.py` exercises the real hardware call chain and asserts that the parser and its entry callers remain
present at the ROM halt. It failed before the change and passed with the configured ROM ELF. The probe uses the same
one-second post-continue delay as the tracer; an initial attempt without that delay timed out before parser entry.
The firmware, parser library, data-trigger logic and incomplete-trace rejection were not changed. No runtime call is
skipped, and no stack is fabricated.

```sh
printf '{}' > /tmp/c3-rom-stack.json
PYTHONPATH=src .venv/bin/python docs/thesis/esp32c3-arduino-json-2026-09-28/check_rom_stack.py \
  --config example_firmware/esp32-c3_json/configuration/configuration.hw-eval.ini \
  --input /tmp/c3-rom-stack.json --rom-address 0x4000079c
```

Use exclusive UART/JTAG access and the unchanged Arduino_JSON firmware. The full eight-versus-one-slot `{}` trace
comparison is a separate gate: a successful backtrace alone does not establish complete instruction/read tracing.
The 18 host hardware-contract checks, targeted Ruff lint/format checks and `.venv/bin/python -m basedpyright` pass.
`mise run typecheck` currently fails because the existing venv console script names an old checkout in its shebang;
the module invocation avoids that unrelated launcher problem.

New diagnostic logs and comparison artifacts are kept separately, preserving the original failure:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-rom-unwind-2026-09-29/
```

The existing `results.json` remains the historical 2026-09-28 record, including its pre-fix configuration hashes.

### Second failure: ROM memset's internal call

The full comparison with ROM symbols reaches `0x40058d56` in `memset`, then fails with
`Unexpected parser return stack: ['0x0']`. No watchpoint window completes, so the one-slot comparison never starts.
A direct breakpoint reproduces this independently of data triggers. Both Homebrew GDB and the locally installed
Espressif GDB 17.1_20260402 report only the `memset` frame, with a previous-frame-identical warning. Refreshing the
register cache does not repair it.

Live disassembly explains the unusual return-address state:

```text
0x40058d94: mv   t0,ra
0x40058d96: jalr -88(a3)    # internal call into the byte-store sequence
0x40058d9a: mv   ra,t0
```

At the failing stop, `ra = 0x40058d9a` points inside `memset`, while `t0 = 0x420007fe` holds the outer return address.
The ordinary leaf-frame assumption is insufficient during this internal call. This is evidence for a missing unwind
rule, not evidence of firmware stack corruption. The shared byte-store sequence can also run through another path;
a blanket replacement of `ra` with `t0` would be unsafe. No register or returned stack was changed to force success.

The regression command with `--rom-address 0x40058d56` reproduces this failure when `rom_unwinder` is unset.
Loading ROM names alone does not solve it; changing debugger builds alone did not solve it either.

After these probes, all ten UART oracle checks passed again. Debugger/server processes were closed. The source and
firmware identities, full-comparison result and evidence hashes are recorded in `rom-unwind-results.json`.

### Debugger-only repair and completed smoke trace

`src/tracer/instance/esp32c3_rom.gdb` supplies the missing unwind rule through GDB's Python unwinder API.
The adapter sources it only when `[GDB] rom_unwinder` is configured, after connecting to the halted target.
`rom_memset_address` selects the ROM body rather than the firmware's `memset` trampoline. Startup reads and hashes
all 168 live instruction bytes; an unknown implementation fails startup instead of applying an unverified rule.

The rule applies only in the shared byte stores/return, or at the RA-restoration instruction, with `ra` equal to the
known internal return address. It tells GDB that the caller PC is in `t0` and that SP and callee-saved registers are
unchanged. Other instruction locations and the ordinary return path use GDB's normal unwinder. This supplies actual
unwind metadata; it does not rewrite hardware registers or invent a caller chain after tracing.

No firmware rebuild or flash was needed. The ELF hash remains
`ba726aef31242a55a798183c1ba130740207f8e1fca407e94b20df3f81e4d8fc`.

Verification on the connected revision-v1.1 board:

- The formerly failing ROM-stack regression passes.
- `--rom-address 0x40058d00 --walk-memset` follows the first allocation's whole `memset` call for 43 steps. It checks
  the original parser callers at each instruction, unchanged PC/RA/SP/t0/s0 across stack requests, internal-call and
  ordinary execution states, and return to the original caller. This allocation does not use the ordinary shared
  byte-store tail; it uses the ordinary word-store loop after the internal alignment call.
- Full `{}` tracing passes with eight-slot and one-slot budgets. Both contain 1,039 instructions and 14 input reads:
  ten reads of byte 0 and four of byte 1. Instruction addresses, function names, stacks and per-instruction read offsets
  match exactly across the merged runs. Eight-slot time: 119.04 s; two one-slot windows: 237.46 s.
- These are two active slots for the two-byte seed, not an eight-byte capability test. The earlier dedicated
  [eight-slot fixture](../esp32c3-hardware-watchpoints-2026-09-28/multislot/README.md) covers that separate claim.

### Miner integration: inline frame depth

The completed real trace exposed a host miner assumption: `graph_utils.py` pushed one scope on a depth increase but
popped one scope per debug-frame decrease. The ESP32 runtime's inline debug frames can change depth by several levels
at one instruction, which emptied the scope stack and raised `IndexError`.

The fix records each observed scope's depth and pops scopes deeper than the new depth. Each trace starts with a fresh
scope stack. A regression with multi-level depth changes fails before the fix and passes afterward. No trace frames
or runtime instructions were dropped. The actual `{}` trace now passes `TreeBuilder` and the full miner, producing
`pipeline-smoke/output/trial-0/parsing_g.json` in the new evidence directory. Mining took 20.17 s.
This one-seed grammar is a pipeline smoke check, not the full reference-corpus result.

The normal evaluator completed with that grammar: 1,000 generated inputs checked on the C3 and the existing 1,000-file
recall corpus. Precision was 1.0, recall 0.001 and F1 0.001998. Only `{}` was used for training, so the low recall is
expected; these values establish that the real pipeline runs, not that it learns a useful JSON grammar from one seed.
The grammar reports five generalization queries. Results are in `pipeline-smoke/evaluation.json`.

The full 20-seed pipeline has now been launched with the normal tracing, mining and evaluation entry points, chained
with `&&` so a failed stage cannot silently proceed to the next. It needs 30 eight-slot windows over 168 seed bytes.
Full tracing uses `output/esp32c3_hw_arduino_json_8wp_2026-09-28/` (moved on 2026-10-01 to `~/Documents/Uni/thesis/experiments/esp32c3-superseded-output-2026-10-01/`); the new experiment directory holds `full-trace.log`,
`full-mine.log`, `full-eval.log`, `full-evaluation.json` and, when the process finishes, `full-pipeline.exit`.
A full-corpus result remains pending. Keep both UART and JTAG connected and do not start competing board sessions.

All 24 discovered host tests, targeted Ruff checks and module-invoked BasedPyright pass. On reconnection macOS renamed
this board's UART to `/dev/cu.usbserial-110`; both configurations now use that path, verified against the CP2102N serial
number. The native JTAG serial identity is unchanged.

## 5. Artifact separation and preserved evidence

The previous custom-parser project, including its ELF/bin and configuration, was archived before rebuilding:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-arduino-json-2026-09-28/before/custom-json-project.tgz
```

The same experiment directory contains build/flash logs, both oracle runs, the failed trace evidence, source/library/
corpus hashes, host checks and an exact diff against the STM32 wrapper. Historical manifests and custom-parser results
were not overwritten.

Fresh output roots prevent this new library ELF from being paired with custom-parser traces:

- `configuration.hw-eval.ini`: `output/esp32c3_hw_arduino_json_8wp_2026-09-28/`.
- `configuration.ini`: `output/esp32-c3_json/arduino-json-hardware-8/`.

The full pipeline described above stopped at the later runtime unwind failure. Its successful smoke results remain
historical evidence, not validation of the replacement framework/toolchain.
No new external research papers were used; the debugger repair was derived from live ROM disassembly and the locally
installed GDB Python unwinder API documentation.
