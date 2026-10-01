# ESP32-C3: second review and evaluation trials 1 and 2

Previous step: [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md), which produced trial-0 of
each target, and the [October 1 review](../esp32c3-review-2026-10-01.md).

## Goal and scope

1. Have a second model review the C3 tracing and mining port, including its documentation, against the paper
   (Eisele et al. 2025, §3, §4.1, §5.4) and the authors' STM32 code and artefacts. Accept only findings that keep
   the method; reject workarounds.
2. Repeat the paper's embedded evaluation twice per target (trial-1, trial-2) with the configuration of trial-0,
   using the authors' three stages: `trace.py`, `mine.py`, `precision_recall.py`.

These trials reproduce the grammar-quality part of §5.4 (precision, recall, tracing and mining time). They do not
include the mutation-fuzzer acceptance of Table 8.

## 1. Review process

Reviewer: `gpt-6.1-sol` (reasoning `xhigh`) through the `pi` agent (`codex-proxy` provider), read-only tools
(`read`, `grep`, `find`, `ls`), no hardware access. The brief gave the paper text, the repository's upstream code,
the STM32 reference firmware and configurations, and the authors' published traces and grammars as ground truth. It
stated the method constraint: the firmware under test stays unmodified, so firmware-side workarounds are off-method.

Round 1 returned 16 findings. Each was checked against the code, the paper and the artefacts before acting. Round 2
gave the reviewer the changes and the reasons for each rejection, and asked it to check the fixes and challenge the
rejections.

## 2. Findings and decisions

| # | Finding (severity) | Decision | Reason |
| --- | --- | --- | --- |
| 1 | Serial resend after a ready marker can duplicate a packet (high) | Resend kept; one race fixed in round 2 | See [below](#finding-1-serial-resend). |
| 2 | CGI `build/` predates the output-buffer fix (high) | Accepted | All three firmwares rebuilt (Section 4). |
| 3 | Mining an incomplete trial pairs traces and seeds wrongly (high) | Accepted in the runner | Upstream miner unchanged; the runner mines only if trace names equal seed names. |
| 4 | Membership-query retries are unbounded (medium) | Accepted in the runner (round 2) | Upstream code unchanged; each stage has a deadline. See [Section 6](#6-round-2-review). |
| 5 | Hardware-only temporary breakpoints imposed on all targets (medium) | Accepted | Base class restored; the C3 override already requests hardware breakpoints. |
| 6 | Rejected bitmap observation still in shared code (medium) | Accepted | Removed from `gdb_tracer.py` and `stm32_instance.py`. |
| 7 | STM32 DWT polling rewrite is not a C3 requirement (medium) | Accepted | Reverted here. The rewrite came from the RP2350 work and remains in that worktree. |
| 8 | Use four watchpoints to match the paper (medium) | Rejected for these trials | See [below](#finding-8-watchpoint-count). |
| 9 | Too little provenance per trial (medium) | Accepted in the runner | Hashes, versions, diffs and stage times recorded (Section 3). |
| 10 | Mutation-fuzzer arm missing (medium) | Scope stated | Out of scope for these trials. |
| 11 | Parser-return guard compares a normalised with a raw name (low) | Accepted | Raw frame name used; regression test added. |
| 12 | Unused pre-serial OpenOCD boot path in STM32 code (low) | Accepted | Removed. |
| 13 | Setup guide lacks tool sources, per-machine values and run commands (doc) | Accepted | Added to the board README; root README hook text restored. |
| 14 | Wiring table omits GND (doc) | Accepted | GND row added; the author confirmed that all four wires (GND, 5 V, D+, D−) are required. |
| 15 | Historical records read as current instructions (doc) | Accepted | Superseded notices on the four older records. |
| 16 | Two equivalence claims exceed their evidence (doc) | Accepted | Reworded in the replica record. |

### Finding 1: serial resend

The claim: after the firmware prints a ready marker in the middle of an exchange, the host waits 1 s plus the
transfer time and then resends. If the first packet was received but its answer arrives later, the firmware
answers twice and later answers shift by one query.

A marker in the middle of an exchange means the firmware restarted. During mining and evaluation no breakpoint
holds the parser, so a received packet is answered within milliseconds, well inside the grace interval. The only
case with a later answer is tracing, where the parser is held at a breakpoint. There the duplicate does no harm:
the tracer does not use the answer, and each watchpoint window closes its connection. The proposed fix, never
resending, would break tracing. `SUTConnection.send_input` has no timeout or retry, so a packet lost during the
attach reset would leave the tracer waiting for the entry breakpoint until its 30 s stop timeout. Two board mining
runs with every answer logged (4,059 and 4,150 answers) had no disagreement with the host oracle
([replica record §8](../esp32c3-paper-replica-2026-09-30/README.md#8-oracle-desynchronisation-during-mining)).

Round 2 found one real race in the kept design: `_read_result` checked the grace deadline before reading. If the
serial process was delayed past the deadline right after reading the marker, an answer already in the buffer was
treated as silence and the packet was resent. The reader now reads once before it checks the deadline, so only a
read that times out with no byte, after the deadline, counts as silence. Regression test:
`test_buffered_result_after_a_host_delay_is_not_resent` (fails on the old reader).

### Finding 8: watchpoint count

The paper's four watchpoints are the STM32's DWT capacity. The upstream INI key `watchpoint_count` means "number of
available watchpoints". Merged traces do not depend on the window size; only the number of executions and the
tracing time do. Trials 1 and 2 repeat trial-0 and keep its configuration (json 6, cgidecode 8, xml 7), so the
three trials are comparable. A four-watchpoint run would answer a timing question and remains a separate, optional
experiment ([October 1 review](../esp32c3-review-2026-10-01.md#controlled-timing-needed-to-explain-a-speed-difference)).

### Check of the shared stack-depth change

`src/miner/graph_utils.py` pops scopes by observed depth instead of one scope per reported frame. Host-only check:
`build_control_flow_graphs_from_traces` before (HEAD) and after the change gives identical CFG edges, function
entries and function scopes on all three sets of authors' STM32 traces and on C3 cgidecode and xml trial-0. Only C3
json differs (7 function scopes). There, newlib `strtod` reaches FreeRTOS `xTaskGetCurrentTaskHandle`, and GDB
reports a depth increase of 2 in one step (6 times). The old code then popped two scopes on return, including the
caller's.

### Round 2

Round-2 answers and resulting changes: see [Section 6](#6-round-2-review).

## 3. Trial procedure

`run-trials.sh` in this folder runs, for json, cgidecode and xml in turn:

1. Flash the firmware built in Section 4 over the UART link.
2. Run the corpus check once (`../esp32c3-paper-replica-2026-09-30/check_corpus.py`): all 20 seeds and 1,000
   evaluation inputs accepted, given invalid inputs rejected, 2,048 bytes accepted, 2,049 rejected, next packet
   aligned. The checker now exits non-zero when any answer disagrees; before round 2 it wrote `failed` and exited 0.
3. For trial 1, then trial 2:
   - Snapshot the code and inputs (below), then run `trace.py` with the target INI. It creates
     `output/esp32-c3_<target>/trial-<n>/`.
   - If tracing stops, the failure and its duration are kept. Once both links have been present for 30 s, the missing
     seeds are traced into `trial-<n>/resume-<k>/` and their traces added (at most two resumes).
   - `mine.py` only when there is exactly one trace per seed and `src/` is unchanged since the snapshot.
   - `precision_recall.py --out trial-<n>/evaluation.json`, again only with unchanged `src/`.

Before each trial and resume, the runner checks that both USB links are present, that no process holds the UART and
that no C3 OpenOCD is running. Each stage has a deadline of about three times its trial-0 duration (json tracing 3 h,
cgidecode 1 h, xml 20 h; xml mining 5 h, others 1 h; evaluation 1 h). A perl parent process sends SIGTERM at the
deadline (exit 143), so the deadline cannot interact with the `SIGALRM` handler in `precision_recall.py`. After a
failed stage, the runner stops leftover UART holders, GDB and OpenOCD. The campaign exits non-zero if any target
failed.

Each trial folder holds:

| File | Content |
| --- | --- |
| `state.txt` | Date, git revision, hash of every `src/*.py`, ELF hash, GDB, OpenOCD, Python and library versions, RNG policy |
| `src.tgz`, `git-diff.patch`, `git-status.txt` | The code that ran, including untracked C3 files |
| `seeds.sha256`, `eval.sha256` | Per-file hashes of the seeds and the evaluation corpus |
| `configuration.ini`, `build.log`, `flash.log`, `build.options.json` | Configuration and firmware provenance |
| `times.txt` | Exit status and wall time of each stage |
| `trace.log`, `mine.log`, `eval.log`, `out.log`, `evaluation.json` | Stage output; `out.log` has the tracing and mining times that the tools log |

The random number generators of mining and precision sampling stay unseeded, as upstream. Individual oracle answers
are not logged by the upstream tools.

## 4. Firmware

Built on 2026-10-01 with the board README command (Arduino-ESP32 3.3.12, `-O0 -g3 -ggdb3`). Logs:
`output/esp32-c3_<target>/build-2026-10-01.log`.

| Target | ELF SHA-256 | Note |
| --- | --- | --- |
| json | `c345758eaa2bc56d181905e637604bb4cf3f5867d3dd29c81fe7e8b5b055f830` | Sources equal to commit `dcc0cf0f`; cached objects reused |
| cgidecode | `fc93c36705731865ddce6a6eaa2180360bea1847df8c73d1055c405cebae40b1` | Includes the output-buffer fix |
| xml | `2389b2b28fba73ae2b330876188a0280d460e6a75557812ada8fee4a9ce6fa54` | Same sources as trial-0 |

Before the rebuild, the previous `build/` contents were copied to `output/esp32-c3_cgidecode/trial-0/firmware/` and
`output/esp32-c3_xml/trial-0/firmware/` (their timestamps match those trials' build logs) and to
`output/esp32-c3_json/build-2026-09-30T2043/` (built after json trial-0, so not its firmware).

## 5. Results

Pending. Campaign log: `output/esp32-c3-trials.stages.log`.

| Date | Event |
| --- | --- |
| 2026-10-01 09:36 | json flashed (ELF `c345758e…`); corpus check passed, 1,027 cases, 0 mismatches |
| 2026-10-01 09:37 | json trial-1 tracing started |
| 2026-10-01 10:00 | Stopped by the author (laptop to be unplugged) after 8 of 20 seeds. Partial output moved to `output/esp32-c3_json/interrupted-2026-10-01-trial-1/`, so the resumed campaign starts trial-1 afresh. Not mined or evaluated. |

To resume, check the UART device name (`ls /dev/cu.usbserial-*`) and update `[Connection] port` in the three INIs if it
changed, then start `run-trials.sh` again. After each finished trial, `check-trial.sh <target> <n>` compares the
board's rejections and scores with the host oracle.

## 6. Round-2 review

The reviewer agreed with the changes for findings 2, 5-7 and 11-16, with keeping 6/8/7 watchpoints for repeats of
trial-0 (finding 8), and with the narrowed scope (finding 10). It disagreed on three points and found six defects in
the new runner and documents.

| Point | Reviewer's argument | Decision |
| --- | --- | --- |
| Finding 1 | A delay of the serial process past the grace deadline turns a buffered answer into a resend | Accepted as a race; fixed by reading before the deadline check (Section 2). The resend itself stays, because tracing needs it. |
| Finding 4 | An input that repeatedly crashes or hangs the firmware cycles timeout, EN reset and resend without end | Accepted: stage deadlines in the runner; upstream retry loop unchanged |
| Finding 9 | State was captured only after tracing, untracked sources were not preserved, corpus hashes lost file boundaries | Accepted: snapshot before tracing with `src.tgz`, per-file corpus hashes, `src/` hash checked before mining and evaluation |
| New: corpus check | `check_corpus.py` exits 0 when answers disagree | Accepted: exits 1 |
| New: campaign status | A failed target left the campaign exit status 0 | Accepted: exits 1 if any target failed |
| New: banners | "It uses..." could be read as describing the current record | Accepted: "This historical record..." |
| New: README missing | This file did not exist yet when the reviewer looked | Written |
