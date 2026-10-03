# ESP32-C3: replicate the paper's embedded evaluation

Subsequent review: [October 1 implementation and paper alignment review](../esp32c3-review-2026-10-01.md).
The CGI output-buffer correction postdates these measurements. Retain the recorded ELF when reproducing this run.

## Goal and scope

Reproduce Section 5.4 of Eisele et al. (2025), *GDBMiner: Mining Precise Input Grammars on (Almost) Any System*,
on an ESP32-C3-DevKitM-1-N4X instead of the STM32 B-L475E-IOT01A. Keep the paper's method and each STM32 reference
configuration; change only what the chip requires, and record each change with its reason. Run order: json,
cgidecode, xml. Precision and recall measure grammar quality, not fuzzing effectiveness.

Paper reference values (STM32, four hardware watchpoints, one set of 20 seeds, 1,000 evaluation inputs):

| Program | Precision | Recall | Tracing time | Mining time |
| --- | --- | --- | --- | --- |
| cgidecode | 93.9% | 97.5% | 01:09:50 | 00:00:48 |
| json | 99.3% | 88.1% | 03:29:14 | 00:02:24 |
| xml | 99.4% | 93.5% | 33:35:21 | 01:12:37 |

## 1. What the paper does that the previous C3 runs did not

The paper traces from an entry function by single-stepping, and skips blacklisted functions "including any
subroutines using the GDB `finish` command" (Section 4.1). `stm32_arduinojson` skips
`malloc|free|_strtod_l|__aeabi_dadd|__floatdidf|__floatundidf|strlen|memset`.

The previous C3 runs rejected `finish` and stepped through every runtime function. On the C3, `strlen`, `memset`
and the soft-float helpers run from mask ROM without unwind information. GDB then reported truncated call stacks,
and the runs needed two custom debugger unwind rules (`src/tracer/instance/esp32c3_rom.gdb`). That diverged from the
paper and grew with each new ROM routine reached.

Decision: skip the same functions as the STM32 reference, with `finish`. The ROM unwind rules, their
`rom_unwinder` option and `configuration.hw-eval.ini` have been removed. The final versions are archived in
`experiments/esp32c3-paper-replica-2026-09-30/removed/`.

## 2. Trigger slots: why `finish` costs two slots on the C3

`finish` runs the target until the current function returns: GDB inserts a temporary breakpoint at the return address
and continues. Code runs from flash or ROM, so the breakpoint is a hardware breakpoint.

| | STM32L475 (paper) | ESP32-C3 |
| --- | --- | --- |
| Breakpoint comparators | 6 (FPB) | 8 trigger slots, each a breakpoint or a watchpoint |
| Watchpoint comparators | 4 (DWT), separate | Shared with breakpoints |

First hardware attempt (`smoke-empty-object/attempt-1-slot-clobber/`): with slot 0 left free, OpenOCD placed a
breakpoint at `0x420228ea` in slot 1 and overwrote a read trigger. The adapter's per-step slot check stopped the trace.
`0x420228ea` is `_Unwind_DebugHook`: during `finish`, GDB also inserts its C++ exception hook, to stop if an exception
unwinds past the frame. `finish_forward` calls `set_longjmp_breakpoint`, which clones the `longjmp` and exception
master breakpoints (GDB 17 `infcmd.c:1742`, `breakpoint.c:7776-7796`); the exception master is `_Unwind_DebugHook`
(`breakpoint.c:3942`). `longjmp` masters exist only if the architecture implements `get_longjmp_target`
(`breakpoint.c:3767`); on this RISC-V target only the two breakpoints were observed.

Changes:

- json uses slots 2-7 as read triggers (six watchpoints; the paper used four) and leaves 0-1 to GDB.
- The adapter reserves its trigger window in OpenOCD (`riscv reserve_trigger N on`). If GDB ever needs more
  breakpoints than the free slots, OpenOCD refuses to insert one and the trace stops with an error, instead of
  silently losing a watchpoint.

## 3. Reads inside a skipped function

`strlen` reads every input byte. With the read triggers armed during `finish`, such a read halts before the load. The
adapter retires the load: it executes it with that trigger disabled, re-arms the trigger, and the tracer issues the
next `finish`.

Second attempt (`attempt-2-unlabelled-rom-finish/`): `finish` returned to the correct address, but GDB's stop record
had no `reason`. GDB labels a stop `function-finished` only when the finished function has debug information:
`finish_command_fsm::should_stop` requires `function != nullptr`, set by `find_pc_function` (GDB 17
`infcmd.c:1585-1624`, `1841`). ROM `strlen` has a symbol from the ROM ELF but no DWARF. Upstream GDBMiner accepts any
stop after `finish` and checks the stack depth. The adapter labels this one case, only when the halt was a hardware
trigger (`dcsr.cause=2`), no read trigger fired, and the stop is not the exception hook.

Whether a read inside a skipped function is *recorded* was first decided by interpretation (record it at the call
site) and then corrected against the authors' published STM32 traces; see section 7.

## 4. Equivalence check against full stepping

For `{}` (seed `input.8`, same ELF), the paper-mode trace equals the earlier full-stepping trace with the skipped
regions removed: 436 of 436 instructions, identical addresses, functions and stacks. All parser reads are identical.
In this initial v1 experiment, four `strlen` reads moved to the call instruction in `cJSON_ParseWithOpts`.
The final v2 adapter instead omits these reads to match the published STM32 traces, as explained in Section 7.
The upstream tracer does not record the instruction at a `finish` return address; this is reproduced.

## 5. Performance without changing traces

| Change | `{}` trace | Evidence |
| --- | --- | --- |
| Previous full stepping, 8 slots, 1 MHz JTAG | 135.7 s | `esp32c3-official-arduino-2026-09-29` |
| Paper skip list, 6 slots, 1 MHz | 49.7 s | `smoke-empty-object/` |
| JTAG 40 MHz (USB-JTAG base clock) | 42.0 s | `smoke-empty-object-40mhz/` |
| 1 ms host poll instead of 10 ms | 32.8 s | `profile-empty-object-1ms-poll/` |

- **JTAG clock:** OpenOCD reports a 40 MHz base clock with dividers 1-255; the previous 1 MHz came from an early probe
  script and was never measured.
- **Host polling:** pygdbmi keeps reading until its timeout expires even after output arrives, so the adapter's
  10 ms poll was a latency floor on every GDB transaction. Profiling showed `-exec-step-instruction` alone took
  14 ms to acknowledge.
- **Pre-step register read:** removed as redundant: each step, `finish` and re-arm already read back every trigger,
  and stack requests do not write trigger registers.

The three paper-mode variants (skip list at 1 MHz, 40 MHz, 1 ms poll) produced identical addresses, functions, stacks
and read hits. The full-stepping trace differs by design, as Section 4 describes. Only `function_args` differ, in one
prologue where GDB reads argument slots before they are stored; the miner and evaluator do not use that field.
The remaining cost per instruction (about 34 ms stepping, 16 ms stack request) is GDB and OpenOCD over USB full-speed.

## 6. cgidecode and xml ports

The earlier C3 cgidecode and xml targets were custom adapters (115,200 baud, 128-byte buffer, `0xa5` ready byte,
toolchain stubs); cgidecode also used a custom parser instead of `percent_encode`. Both are replaced by ports of the
STM32 wrappers, built like json with Arduino-ESP32 3.3.12 and its matched GCC 14.2 toolchain, without stubs:

- cgidecode: `percent_encode@2.0.1`, entry `percent::decode`, no skipping, all eight slots as watchpoints.
- xml: `LibYxml@1.0.2`, entry `main.ino:46`, exit `main.ino:53`, seven watchpoints and one slot for the exit
  breakpoint. `yxml_parse` reaches only LibYxml functions, so its ignore list never fires.

Seeds and evaluation corpora are byte-identical to the STM32 copies. `check_corpus.py` requires the flashed port to
accept every seed and all 1,000 evaluation inputs, reject given invalid inputs, accept 2,048 bytes, reject 2,049 and
stay aligned for the next packet.

## 7. json: first runs, and comparison with the authors' artefacts

The repository contains the authors' STM32 json artefacts (`evaluation/stm32_applications/stm32_arduinojson/`):
20 traces, derivation trees and the mined grammar. Their grammar, evaluated with the repository evaluator and a host
oracle (below), scores 100.0% precision and 88.1% recall; the paper reports 99.3% and 88.1%. This reproduces recall
and gives similar precision, but does not establish oracle equivalence on every possible query.

Two C3 trace variants were run:

- v1 (`json-full/`): reads made inside a skipped function (by `strlen`) recorded at the call site.
- v2 (`json-full-v2/`): such reads retired but not recorded. In the STM32 traces no read is recorded at the `strlen`
  call site, and bytes read only by `strlen` (trailing whitespace) have no read at all, so v2 matches the reference.

Trace comparison with the STM32 traces, seed by seed: instruction counts nearly match (for example 658 vs 662,
2,043 vs 2,034), and v2 consumes every byte in the same function, except:

- The published traces of `input.2`, `input.7` and `input.13` were made from CRLF versions of the seeds
  (`\r\n[]` instead of the repository's `\n[]\n`). The C3 runs use the repository seeds.
- The C3 ROM `strncmp` loads 4 bytes at a time, so it reads up to 3 bytes past a keyword mismatch (byte 3 of
  `input.9`, byte 7 of `input.15`). This is the chip's ROM library, not the tracer.

The derivation trees of both platforms have the same structure; only address-derived name suffixes differ.

Board results of these first runs were poor: v1 84.8% precision, 99.7% recall; v2 84.6%, 96.4%. Most rejected
inputs were a bare `{` (144 of 152 in v1). The cause was not the traces but the oracle during mining (section 8).
Mined on the host with a correct oracle, both variants give the same grammar quality:

| Traces | Precision (5 × 1,000) | Recall | F1 |
| --- | --- | --- | --- |
| v1, host-mined | 100.0% | 93.6% | 96.7% |
| v2, host-mined | 99.5-99.6% | 93.6% | 96.5% |
| Authors' STM32 grammar | 100.0% | 88.1% | 93.7% |

Recording reads inside skipped functions therefore has no material effect here. v2 is kept because it matches the
reference traces.

## 8. Oracle desynchronisation during mining

Mining asks the board whether candidate inputs are accepted (about 4,000 queries for json). A host oracle built from
the same cJSON 1.7.14 source (`analysis/host_eval.py`, `analysis/host_mine.py`) made the diagnosis possible:

1. The host oracle agrees with the board on all 1,020 corpus inputs and on all 152 inputs the board rejected
   during evaluation.
2. Mining the v2 traces with the host oracle gives 99.6% precision (two runs); mining them on the board gives
   83.9-84.6% (three runs). The miner has no time-dependent logic.
3. Replaying the host run's 4,057 queries on the board, in one session, gives 0 disagreements.
4. Logging every board answer during board mining (`analysis/board_mine_logged.py`): 174-176 answers disagree,
   all in the loop-generalisation phase. From query #1251 to the end of that phase, all 701 answers equal the
   correct answer to the *previous* query. The method and token phases are fully correct.
5. A raw serial log of that phase shows the cause. Each mining phase opens a new connection: the EN pulse reboots
   the chip, and the connection process reads the firmware's ready marker `A`. When GDB attaches, OpenOCD then resets
   the core again ("Memory protection is enabled. Reset target to disable it"), so the firmware prints boot noise
   and a second `A`. The adapter (`esp32_serial_connection.py`, written in an earlier session) had sent the first
   packet and, on seeing that second `A`, resent it. If the first packet had arrived after the rebooted firmware set
   up its UART, the firmware answered it twice, and every later answer belonged to the previous query. Whether the
   first packet is lost or buffered depends on the miner's timing, so only some phases were affected. Aggregate
   precision hardly changes under such a shift, which is why evaluation looked plausible.

The STM32 reference is not affected: st-util does not reset the target on attach, and `SerialConnection` clears the
input buffer after opening the port.

Fix (`esp32_serial_connection.py`): the ready check moves to just before each packet. After a connection (or a
detected restart), the host waits until the last byte received is the marker and the line has been quiet for
0.2 s. If a marker arrives before the result, the host waits for a result for 1 s plus the packet's transfer time,
and resends only if none comes. In steady state the marker right after each result is accepted without the quiet
wait. Validation: two board mining runs with every answer logged, 4,059 and 4,150 answers, 0 disagreements with the
host oracle; both grammars score 99.6% precision and 93.6% recall.

All earlier board mining and evaluation results (json v1, v2, cgidecode) used the faulty exchange. Traces are
unaffected: tracing does not use the oracle answer.

## 9. cgidecode

The C3 traces match the authors' STM32 traces (`evaluation/stm32_applications/stm32_cgidecode/`) at the level the
miner uses: for all 20 seeds, every input byte is last read by the same function. Instruction counts differ by 3-9
per seed, mostly 3 (5,655 vs 5,736 in total). The published traces were made from the same seed files.

The reference library's decode line, `(indexOf(*++input) << 4) + indexOf(*++input)`, has undefined behaviour
(two unsequenced increments); the decoded byte, and so acceptance, depends on the compiler's evaluation order. GCC
on the C3 and Clang on the host both evaluate the high nibble first: 630 golden inputs contain an order-sensitive
`%XY`, and both accept all of them.

| cgidecode | Precision | Recall | F1 | Tracing | Mining |
| --- | --- | --- | --- | --- | --- |
| C3 replica (board, re-mined with the fix) | 98.7% | 97.1% | 97.9% | 00:10:16 | 00:00:56 |
| Paper (STM32) | 93.9% | 97.5% | 95.6% | 01:09:50 | 00:00:48 |

Host evaluation (host oracle agrees with the C3 on all 1,020 corpus inputs and all 13 C3 rejections):

| Grammar | Precision (5 × 1,000) | Recall | F1 |
| --- | --- | --- | --- |
| Authors' STM32 grammar | 93.7% | 99.3% | 96.4% |
| C3 replica | 98.3% | 97.1% | 97.7% |

The authors' grammar reproduces the paper's precision; its recall on the repository corpus is 1.8 points above the
paper's figure. The 13 inputs the C3 rejected all contain `%` followed by a non-hex character, which `indexOf` maps to
`0xFF`, so the decoded byte exceeds 127.

## 10. xml

First A/B attempt (`xml-ab-*/failed-step-stop/`): both traces failed at the end of the first window. A step that
lands on the exit breakpoint (`main.ino:53`) is reported by GDB as `breakpoint-hit`, not `end-stepping-range`; the
C3 step code rejected it. The upstream tracer expects exactly this stop to end a window, and checks the breakpoint
number. The adapter now passes it through.

By default GDB removes every breakpoint after each stop and re-inserts it before the next `stepi`
(`infrun.c` `maybe_remove_breakpoints`); with the exit breakpoint present, that is two extra OpenOCD trigger writes
per step. `breakpoint_always_inserted = true` keeps the same breakpoint inserted. A/B on `input.9` (8 bytes, two
windows): identical traces (2,189 entries), 271 s with the GDB default and 244 s with the breakpoint kept inserted.
The full run uses the latter.

The first xml trace matches the authors' STM32 trace at the consumption level: every byte is last read in
`parser()`, on both platforms (`yxml_parse` receives each byte by value). The C3 steps about three times as many
instructions inside `yxml_parse` (1,818 vs 592 for `input.9`), which affects tracing time only.

Full run (`xml-full/`, now `output/esp32-c3_xml/trial-0/`): 17 of 20 seeds traced between 04:16 and 09:23. The USB-JTAG link (USB-C breakout on
GPIO18/19) then dropped during `input.11` (`LIBUSB_ERROR_NO_DEVICE`, `esp_usb_jtag: device not found`); the tracer
stopped with an error and did not hang. The same link dropped on 2026-09-29. The 17 saved traces are kept; the three
missing seeds (`input.11`, `input.18`, `input.20`) are traced separately (`xml-resume/`, now that folder's `resume/`) with the same configuration
and firmware and added before mining. The miner pairs traces and seeds by sorted file name.

Tracing time: 04:22:12 for the first 17 seeds, 03:06:53 for the remaining three, 07:29:05 in total (the lost part
of `input.11` and the wait for the link excluded). All 20 traces consume every byte in the same function as the
authors' STM32 traces (`parser()`), and the derivation trees have the same structure.

Mining took 01:21:42 with 100,673 board queries (18,908 method, 81,175 loop, 590 token). Board result: precision
98.4%, recall 67.2%, F1 79.9% (paper: 99.4%, 93.5%, 96.4%). There were no parse timeouts; every golden input that
fails is nested (more than one element), against 25% of those that parse. The grammar has no element recursion.

Where the xml gap comes from (host oracle, `analysis/`):

| Grammar | Size | Precision | Recall |
| --- | --- | --- | --- |
| C3 traces, board-mined (the result above) | 96 nonterminals, 296 rules | 98.1% | 67.2% |
| C3 traces, host-mined, three hash seeds | 96, 296 | 98.1% | 67.2% |
| Authors' STM32 traces, this repository's miner | 96, 296 | 98.1% | 67.2% |
| Authors' STM32 traces, upstream miner (`7de31185`, clean import) | 96, 296 | 98.1% | 67.2% |
| Authors' published grammar | 113, 431 | 99.1% | 100.0% |
| Today's grammar stages run on the authors' loop trees | 113, 432 | 99.2% | 100.0% |
| Today's grammar stages run on our loop trees, "deletable" markers removed | 113, 431 | 99.1% | 100.0% |

The C3 replica therefore reproduces exactly what the published miner makes of the published traces with a correct
oracle. The whole difference to the published grammar is one class of decision: method generalisation marks a node
"deletable" (name suffix `-`) when the oracle still accepts the input with that node's content removed. yxml without
an end-of-file check accepts many such inputs, so a correct oracle marks 490 nodes deletable; the authors' loop trees
contain none. Their json run did mark nodes deletable (127, C3: 131), their cgidecode run none (C3: 116). A correct
oracle cannot reject every shortened cgidecode string, so the authors' cgidecode and xml runs either used a miner
without this step or had an oracle that rejected shortened inputs. The artefacts do not show which. For cgidecode,
removing the markers alone does not reproduce the authors' grammar (10 vs 13 nonterminals), so other decisions
differed there too.

### What the markers change, and why the published recall is inflated

The markers are correct decisions, but they change the test input of token generalisation. Evidence:
`analysis/xml_recall_mechanism.py`, output in `analysis/xml-recall-mechanism.log` (host oracle, no board).

1. Only one marker matters: byte class 6, the characters of element text and attribute values (`R`, `G`, `y` in
   `input.20`). Removing this marker alone gives 100.0% recall. Removing the markers of classes 9 and 10, or of
   `parser`, changes nothing.
2. `check_empty_rules` removes all nullable symbols from a rule at once and drops the rule if nothing remains. With
   text nullable, `W57 → B6 W57` (a text character, then the rest of the loop) yields no shorter rule, so
   `W57 → B6` (the input ends after a text character) is lost. Ten such rules are lost. Textbook ε-removal keeps
   them.
3. The token generaliser tests each character in the shortest input the grammar derives. Without the marker, this
   input ends at the text character: `<b>R`. The acceptance rule has no end-of-input check (`parser()` in `main.ino`
   never calls `yxml_eof`, as in the STM32 wrapper), so `<b>` followed by any printable character is unfinished but
   free of errors. Text is widened to `[__ASCII_PRINTABLE__]+`.
4. With the marker, the shortest input continues: `<b>R<`. Replacing `R` with `<` gives `<b><<`, which yxml
   rejects. Text stays `[__ASCII_ALPHANUM__]+`.

Text that may contain `<`, `/` and `>` matches any nested markup, so nested elements are parsed as text. This is
the source of the published grammar's 100.0% recall. The same grammar accepts invalid XML:

| Input | Oracle | C3 grammar | Markers removed | Authors' published |
| --- | --- | --- | --- | --- |
| `<a><b>y</b></a>` | accept | reject | accept | accept |
| `<a><</a>` | reject | reject | accept | accept |
| `<a>&</a>` | reject | reject | accept | accept |
| `<a></b></a>` | reject | reject | accept | accept |
| `<a>x</a></a>` | reject | reject | accept | accept |

Counterfactual: the trees as mined, with textbook ε-removal in place of `check_empty_rules`, also give printable
text and 100.0% recall. The deletable decision is therefore not the cause. The cause is the combination of an
acceptance rule without an end-of-input check, a test input that ends at the widened character, and the ε-removal
that decides whether it ends there. Precision does not reveal the over-generalisation: the grammar with printable
text scores 99.1%, the C3 grammar 98.1%.

### Why the grammar does not learn nesting

The evaluation XML is context-free. Full XML is not, because opening and closing tags of arbitrary length must
match, but the paper restricts tags to `a`-`d` (page 15). The 1,000 golden inputs use only these four names, with
elements nested up to five deep (385 inputs at depth 2 or more). One rule per tag name matches every closing tag,
so a complete grammar exists.

The limit is the parser design. GDBMiner derives grammar structure from the call stack of a recursive descent
parser (Section 3). yxml is a state machine: `parser()` calls `yxml_parse` once per byte, and yxml stores the open
elements in a data buffer (`xmlbuf`), not on the call stack. Every byte is consumed at the same stack depth, so each
derivation tree is a flat chain of `parser()` loop iterations. The mined grammar is a finite-state approximation
over loop classes and repeats only the nesting patterns of the seeds. Three of 20 seeds contain a child element with
its own closing tag, all inside an element with attributes. The C3 grammar accepts `<a><b/></a>` but rejects
`<a><b></b></a>`.

Neither grammar models element nesting. The C3's 67.2% recall measures what the miner learned from the seeds; the
published 100.0% is an artefact of the text generalisation.

## Results

Final runs use the fixed serial exchange (section 8): json from the v2 traces (`json-final/`, now in this worktree at
`output/esp32-c3_json/trial-0/`), cgidecode from its traces (`cgidecode-final/`,
now `output/esp32-c3_cgidecode/trial-0/`). One run per program, as in the paper's Section 5.4.

| Program | Precision | Recall | F1 | Tracing | Mining |
| --- | --- | --- | --- | --- | --- |
| json, C3 | 99.1% | 93.6% | 96.3% | 00:44:38 | 00:01:56 |
| json, paper | 99.3% | 88.1% | 93.4% | 03:29:14 | 00:02:24 |
| cgidecode, C3 | 98.7% | 97.1% | 97.9% | 00:10:16 | 00:00:56 |
| cgidecode, paper | 93.9% | 97.5% | 95.6% | 01:09:50 | 00:00:48 |
| xml, C3 | 98.4% | 67.2% | 79.9% | 07:29:05 | 01:21:42 |
| xml, paper | 99.4% | 93.5% | 96.4% | 33:35:21 | 01:12:37 |

cgidecode re-mined with the fix gives the same grammar quality and query count (2,186) as its first run. These
aggregate measurements show no effect of the desynchronisation on the first run. Its individual answers were not
logged, so an effect on single queries cannot be excluded.

The retained successful tracing times are 4.5-6.8 times shorter than the paper's reported times. The host, transport,
compiler and watchpoint counts differ, and XML recovery time is excluded, so these ratios do not isolate an
architecture speedup. JSON and cgidecode scores are close to or above the paper's values, except for slightly lower
JSON precision and cgidecode recall. XML has similar precision; its recall gap is reproduced by the published miner on the authors' own traces,
so it does not come from the C3 port. The correct "deletable" decisions prevent text from being widened to any
printable character, the artefact behind the published 100.0% recall (section 10).

## Sources

- GDB `gdb-17-branch`: `gdb/infcmd.c` (`finish_command_fsm::should_stop`, `finish_forward`) and `gdb/breakpoint.c`
  (`set_longjmp_breakpoint`, exception master on `_Unwind_DebugHook`),
  <https://sourceware.org/git/?p=binutils-gdb.git;a=tree;f=gdb;hb=refs/heads/gdb-17-branch>.
- Espressif OpenOCD `v0.12.0-esp32-20260831`: `riscv reserve_trigger`, which must follow `init` (observed).
- pygdbmi `IoManager._get_responses_unix`: reads until the timeout expires even after output arrives.

## Evidence

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-paper-replica-2026-09-30/
```

The three final runs were moved into this worktree's git-ignored `output/` directory. Everything else stays in
the evidence root.

| Run | Evidence-root folder | Worktree location | Build log moved in as `build.log` |
| --- | --- | --- | --- |
| json | `json-final/` | `output/esp32-c3_json/trial-0/` | 2026-09-29 root, `build-native-corrected.log` |
| cgidecode | `cgidecode-final/` | `output/esp32-c3_cgidecode/trial-0/` | `cgidecode-build.log` |
| xml | `xml-full/`, with `xml-resume/` as `resume/` | `output/esp32-c3_xml/trial-0/` | `xml-build.log` |

Each `trial-0/` holds the traces and mined grammars, plus the run's configuration, logs, source snapshot and
`evaluation.json`. The miner reads only `trial-0/*.trace`, so these records do not affect mining. The recorded
`configuration.ini` files still name the old absolute output paths. Each target INI writes to
`output/esp32-c3_<target>/`, so mining and evaluation select `trial-0/` until a new trace creates `trial-1/`. The
flashed firmware stays in `example_firmware/esp32-c3_<target>/build/`, where `binary_file` points; each ELF's
timestamp matches its build log. `analysis/run-xml-host-analysis.sh`, `analysis/run-xml-variance.sh` and
`analysis/xml_recall_mechanism.py` read the xml run from its worktree location.

Earlier C3 outputs, made before this method or incomplete, were moved from `output/` to
`~/Documents/Uni/thesis/experiments/esp32c3-superseded-output-2026-10-01/` under their original names.
