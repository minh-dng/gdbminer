# ESP32-S3 evaluation results

Results of the full pipeline (`trace.py`, `mine.py`, `precision_recall.py`) on the
ESP32-S3-Zero, in the layout of `evaluation/stm32_applications/`:

```text
esp32-s3_<target>/trial-<n>-<setup>/
├── seed.N.in.trace      # one trace per seed
├── method_trees.json, loop_trees.json, mined_g.json, parsing_g.json
├── evaluation.json      # precision, recall and run statistics (below)
├── out.log
└── run/                 # provenance: configuration, build, flash and stage logs, times.txt
```

`<target>` is `cgidecode`, `arduinojson`, `libyxml` or `calc`. `<setup>` is `1-watchpoint` or
`2-watchpoints` (hardware watchpoints used while tracing; `watchpoint_count` of the configuration).

## Trial-3 and trial-4 folders

The `arduinojson` and `cgidecode` folders of trial-3 and trial-4 (both setups) and the `libyxml`
folders of trial-3 (both setups) and trial-4 (two watchpoints) hold full runs (flash, trace, mine
and evaluate) with 20 traces each, started between 29 October and 4 November 2026. Each run traced
in one `trace.py` call: `run/times.txt` has one `flash`, `trace`, `mine` and `eval` row per folder,
all with exit code 0. The values come from `evaluation.json`; the start is the date line of
`run/state.txt`.

| Folder | Start (AEDT) | Inputs | Tracing (h) | Mining (s) | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `arduinojson/trial-3-1-watchpoint` | 29 Oct 17:29 | 3,992 | 7.38 | 23.7 | 0.981 | 0.977 | 0.9790 |
| `arduinojson/trial-3-2-watchpoints` | 29 Oct 13:14 | 4,008 | 4.18 | 24.2 | 0.982 | 0.999 | 0.9904 |
| `arduinojson/trial-4-1-watchpoint` | 30 Oct 06:52 | 4,014 | 7.49 | 22.2 | 0.981 | 0.977 | 0.9790 |
| `arduinojson/trial-4-2-watchpoints` | 30 Oct 02:37 | 4,348 | 4.18 | 38.9 | 0.847 | 0.999 | 0.9167 |
| `cgidecode/trial-3-1-watchpoint` | 29 Oct 12:13 | 2,187 | 0.96 | 15.6 | 0.987 | 0.971 | 0.9789 |
| `cgidecode/trial-3-2-watchpoints` | 29 Oct 11:29 | 2,185 | 0.67 | 15.5 | 0.978 | 0.971 | 0.9745 |
| `cgidecode/trial-4-1-watchpoint` | 30 Oct 01:39 | 2,188 | 0.91 | 51.7 | 0.974 | 0.971 | 0.9725 |
| `cgidecode/trial-4-2-watchpoints` | 30 Oct 00:55 | 2,184 | 0.68 | 15.1 | 0.980 | 0.971 | 0.9755 |
| `libyxml/trial-3-1-watchpoint` | 1 Nov 02:55 | 100,726 | 83.05 | 347.6 | 0.996 | 1.000 | 0.9980 |
| `libyxml/trial-3-2-watchpoints` | 30 Oct 15:01 | 100,725 | 35.70 | 398.1 | 0.995 | 1.000 | 0.9975 |
| `libyxml/trial-4-2-watchpoints` | 4 Nov 14:09 | 100,726 | 41.39 | 380.0 | 0.996 | 1.000 | 0.9980 |

The `libyxml` folders have no trial-1: the numbering goes from trial-0 to trial-2 to trial-3. There
is no `libyxml` trial-4 for one watchpoint because that run has not been done.

Within a target, these folders share one ELF with the trial-2 folders (`run/state.txt`):
`5be11988...` (`arduinojson`), `010d8184...` (`cgidecode`) and `41d92905...` (`libyxml`). The
trial-0 and trial-1 folders of `arduinojson` and `cgidecode` have other ELFs (`6c67d32a...` and
`646897ec...`), and the `libyxml` trial-0 folders have `3219a327...`. All eleven runs used the board
`E8:06:90:95:F2:70` on `/dev/cu.usbmodem101`.

Provenance gaps of these folders:

- `run/state.txt` records Git HEAD `cb5f33e3` of the branch `docs/esp32-evaluation-trial-2`, which
  is not on `main`. Its `src/` and `example_firmware/` are identical to those of `05aa19f9`, which
  is on `main`. Fixes committed to `main` on 27 and 28 October (OpenOCD start attempts, the exit of
  GDB, watchpoints without C casts, the `GDB.frame_arguments` option, a finish that ends with
  ICOUNT) are not in that HEAD; their effect on these results is not assessed. The `git status:`
  line points to a `git-status.txt` that is not published (5 to 28 changed paths).
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). In every folder
  `eval.log` has `1000 * (1 - precision)` `Generated non accepting input` lines, which fits a
  1,000-input set.
- Every `trace.log` has 74 to 1,312 `OpenOCD startup retry` lines (`LIBUSB_ERROR_IO`) and 1 to 18
  failed attach attempts (`libyxml/trial-3-1-watchpoint` and `libyxml/trial-4-2-watchpoints` have
  one failure of attempt 2); all 20 traces were still written in every folder.
  `cgidecode/trial-4-1-watchpoint` and `libyxml/trial-4-2-watchpoints` also have 74 and 73 retry
  lines and one failed attach attempt in `mine.log`. No `eval.log` or `flash.log` has one.
- No folder has a `run/build.log`; the ELF is identified by the sha256 in `run/state.txt` and the
  build by `run/build.options.json`.
- Absolute paths of the machine that ran them are kept in the `run/*.log`,
  `run/configuration.toml` and `run/build.options.json` files. In eight logs
  (`arduinojson/trial-3-1-watchpoint` to `trial-4-2-watchpoints`, `out.log` and `run/mine.log`) one
  carriage return before a line feed was normalised to a line feed on commit.

## Calc trial-0 folder

`calc/trial-0-2-watchpoints` holds one complete run (flash, trace, mine and evaluate) of the
desktop calc parser with the authors' 20 seeds and evaluation corpus, using two hardware
watchpoints. Precision, recall and F1 are 1.0 on 196,745 inputs. There is no one-watchpoint calc
run. The calc firmware and configuration used here are added in
[#71](https://github.com/minh-dng/gdbminer/pull/71). The values come from `evaluation.json`, the
logs in `run/` and `run/state.txt`; AEDT is local time.

| Folder | Start (AEDT) | Tracing ended | Inputs | Tracing (h) | Mining (h) | Eval (s) | Requests (methods / loops / tokens) | Throughput (requests/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `calc/trial-0-2-watchpoints` | 25 Oct 01:54 | 6 Nov 11:00 | 196,745 | 236.26 | 2.54 | 9 | 154,455 / 42,164 / 126 | 21.5 |

The run was resumed three times on one board (S3 B, adapter serial `E8:06:90:95:80:6C`,
`/dev/cu.usbmodem3101`, GDB port 3334). The start is the date line of `run/state.txt`, the start of
each call is in `run/commands.log`, and the exit codes and seconds are in `run/times.txt` (22 rows,
in this order):

| Phase (`times.txt` rows) | Start (AEDT) | End | Exit | Seconds | Traces written (seeds) |
| --- | --- | --- | --- | --- | --- |
| `flash`, `trace` | 25 Oct 01:55 | 28 Oct 01:05 | 0, 1 | 11, 256,189 | 8: 15, 9, 11, 8, 10, 20, 14, 7 |
| `flash`, `trace-resume-1`, `flash`, `trace-resume-2`, `flash`, `trace-resume-3` | 28 Oct 01:05 | 28 Oct 01:11 | 0, 1 | 11, 114, 5, 68, 17, 20 | none |
| six `flash` | 28 Oct 01:28 | 28 Oct 01:46 | 1 | 11 to 12 each | none |
| four `flash` | 28 Oct 01:57 | 29 Oct 01:47 | 0 | 6, 6, 9, 6 | none |
| `trace-resume-1` (second call) | 28 Oct 01:58 | 29 Oct 01:37 | no row | not recorded | 5: 3, 2, 6, 1, 19 |
| `trace-resume-2` (second call) | 29 Oct 01:47 | 5 Nov 01:47 | 143 | 604,814 | 10: 3, 2, 6, 1, 19, 5, 4, 18, 13, 17 |
| `flash`, `trace-resume-3` (second call) | 5 Nov 01:48 | 6 Nov 11:00 | 0 | 13, 119,515 | 2: 16, 12 |
| `mine` | 6 Nov 11:00 | 6 Nov 13:33 | 0 | 9,155 | |
| `eval` | 6 Nov 13:33 | 6 Nov 13:34 | 0 | 9 | |

What happened in each phase:

- The first `trace.py` call ended with exit 1 after 256,189 s. Its `run/trace.log` ends with
  `TimeoutError: S3 stop timeout: pc=0x4002e77e` while seed 3 (started 27 October 20:32) was in
  progress. That seed was lost and traced again.
- The first calls of resume 1, 2 and 3 on 28 October each started one seed and failed after 114, 68
  and 20 s, before any trace was written. Their logs are not published. The runner's `errors.log`
  (not published) shows two `S3 stop timeout` errors and, for resume 3, `Remote connection closed`
  on `-target-select extended-remote :3334`.
- Six `flash` rows exit with 1, in two runner restarts (28 October 01:28 to 01:31 and 01:43 to
  01:46, three attempts each). The same `errors.log` shows the esptool message
  `Failed to connect to ESP32-S3: No serial data received` for each. The flashes of 01:57 and
  01:58 then succeeded.
- Resume 1 started on 28 October 01:58 and wrote seeds 3, 2, 6, 1 and 19 by 19:19. The runner was
  stopped by hand on 29 October 01:37 from another session that needed the board for other tests
  (`runner-calc2.log`, not published). The last line of `run/resume-1/trace.log` is from 01:30.
  `times.txt` has no row for this call because the runner was stopped before it wrote one. Seed 5,
  in progress since 19:19 on 28 October, was lost.
- Resume 2 started on 29 October 01:47 with the same 12 missing seeds as resume 1, so it traced
  seeds 3, 2, 6, 1 and 19 a second time, then 5, 4, 18, 13 and 17. The `timeout` limit of 604,800 s
  ended it with SIGTERM (exit 143, 604,814 s) on 5 November 01:47. Seed 16, in progress since
  3 November 18:14, was lost. The logs of resume 1 and 2 end with the Python `resource_tracker`
  warning about 9 leaked semaphore objects, which follows the termination.
- Resume 3 started on 5 November 01:48, traced the two missing seeds (16 in 115,524 s and 12 in
  3,989 s) and exited with 0. Mining started about 30 s after it ended.

Reconciliation of the trace logs. `run/trace.log` and the three `run/resume-N/trace.log` files have
28 `Start generating trace for` lines (9, 6, 11 and 2) and 25 `Write trace of` lines (8, 5, 10 and
2). Three starts were not completed (seed 3 in `run/trace.log`, seed 5 in resume 1 and seed 16 in
resume 2). Of the 25 traces written, five are second writes (seeds 1, 2, 3, 6 and 19, in resume 1
and again in resume 2), which leaves the 20 seeds. No log has `Write validated trace of`.

Checks on the 20 traces:

- The `seed.N.in.trace` file names equal the seed names in `run/seeds.sha256`, and the 20 files of
  `example_programs/calc/seeds` match its hashes. `trace.json` has the input of each seed exactly
  once. `run/eval.sha256` matches the evaluation inputs of `example_programs/calc/eval`. Both hash
  files are identical to those of the ESP32-C3 calc folders.
- In the source checkout, the resume 1 and resume 2 traces of the five seeds written twice are
  byte-identical to each other and to the published files. The published traces of seeds 4, 5, 13,
  17 and 18 equal the resume 2 files, and those of seeds 12 and 16 equal the resume 3 files.
- Seed 12 was also traced on another S3 board as a backup (6 November 08:47 to 09:39, 3,116 s).
  That trace is byte-identical to the published `seed.12.in.trace` of board B (sha256
  `d3072e18...`) and is not published. A backup of seed 16 on that board was stopped without a
  trace.

`evaluation.json` had only the four fields written by `precision_recall.py`. The runner's
`add-timings.py` stopped at its assertion of one written trace per seed, which the five second
writes break. The other fields were added in a second commit with a copy of that script in which a
seed written twice counts once, for the later run (resume 2). The same five seeds took 62,424 s in
resume 1 and 59,142 s in resume 2, so counting resume 1 would raise `tracing.duration` by
3,282 s. `tracing.duration` (236.26 h) is the sum of the 20 seeds. The wall time from the first
flash to the last trace was 297.1 h; the difference is the three lost seeds, the failed attempts
and the waits between calls. `execution_duration` is 238.8 h. `mining.duration` is the
`Mining time` of `run/mine.log` (9,153.0 s against 9,155 s for the `mine` row), and
`evaluation_duration` is the `eval` row.

Provenance gaps of this folder:

- `run/state.txt` records Git HEAD `936e5458` of `feat/calc-esp32-s3-target`, which is not on
  `main`. It adds the calc firmware, configurations and documents to `05aa19f9` and leaves `src/`
  unchanged. One path is changed: the untracked `example_programs/calc/calc.c` (sha256
  `15a1c58f...` in `run/source-and-elf.sha256`). The `git status:` line points to a
  `git-status.txt` that is not published (it holds only that path). The ELF sha256 is
  `85f024ef21abc1ca059c56b2b6ba0857015d5c381ce3a4259be77a046c40ce84`.
- Six commits on `main` after `05aa19f9` change `src/` and are not in that HEAD
  (`git merge-base --is-ancestor`): `0e288191`, `12bdd858` and `7a8f1526` (OpenOCD start attempts,
  a stop timeout when GDB has exited), `d1c5a129` (watchpoints without C casts), `87c16375`
  (`GDB.frame_arguments`) and `1937b8ef` (a finish that ends with ICOUNT). The run has stop
  timeouts and OpenOCD start timeouts, but no file shows whether these commits would have changed
  it; their effect is not assessed.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). `eval.log` has
  no `Generated non accepting input` line, which fits precision 1.0 but does not show the count, so
  the precision of 1.0 is as provisional as in the C3 folders.
- There is no `run/build.log`: the source folder has none. The ELF is identified by the sha256
  above and the build by `run/build.options.json`. The `openocd:` line of `run/state.txt` holds the
  version (`v0.12.0-esp32-20260831`).
- `run/flash.log` is the flash of 5 November 01:48. The logs of the other flashes, the failed
  resume calls, the runner log and the backup trace are not published. The statements above that
  rest on them are marked.
- `run/` has no other files of the source folder: `git-status.txt`, 14 `flash.log.before-*`
  backups, `run-eval.sh`, `status.sh`, `add-timings.py`, `input-check.txt`, `python-packages.txt`,
  `source-head.txt`, `source-configuration.toml` and the `configuration.toml` of the resumes (they
  differ from `run/configuration.toml` in the seed and output directory lines only). It adds
  `commands.log` and `source-and-elf.sha256` to the usual files, and the three resume logs.
- Absolute paths of the machine that ran it are kept in the `run/*.log`, `run/configuration.toml`
  and `run/build.options.json` files.

Anomaly scan of the logs (`ERROR`, `Traceback`, `Timeout`, `restart`, `abort`, `Stack canary`,
`LIBUSB_ERROR`, `failed`):

- `run/mine.log`, `run/eval.log` and `run/flash.log` have no match and no `OpenOCD startup retry`
  line.
- `OpenOCD startup retry` in the trace logs: 878 (`trace.log`), 509, 1,241 and 219 (resume 1 to 3).
  They come with 882, 506, 1,243 and 216 `LIBUSB_ERROR_IO` lines and one `LIBUSB_ERROR_PIPE` line
  (resume 3). The logs also have 38 failed first and one failed second attach attempt (resume 1,
  28 October 12:34); the run went on after each, so they are recoverable.
- The only tracebacks are the stop timeout at the end of `run/trace.log`. The SIGTERM of resume 2
  and the stop of resume 1 leave no traceback.
- The grammar has 23 nonterminals and 49 alternatives, as in all seven mined C3 calc folders. After
  sorting the alternatives it differs from them in five nonterminals, all because the string
  conversion function has another name (`_strtol_l$isra$0` here, `__call_strtol` on the C3).
- `mine.log` has 51 `No suitable loop` warnings, as in all seven mined C3 calc folders.
- The method and loop requests (154,455 and 42,164) equal those of the C3 one-cable runs; the 126
  token requests are within their range (109 to 137). Throughput is 21.5 requests per second
  against 24.7 to 26.0 for the C3 one-cable runs; this is not explained.

## evaluation.json

| Field | Unit | Meaning |
| --- | --- | --- |
| `precision`, `recall`, `f1` | ratio, 0 to 1 | Written by `src/eval/precision_recall.py`. |
| `no_tested_inputs` | requests | Inputs the miner sent to the board. Equals `mining.requests.total`. |
| `watchpoint_count` | count | Hardware watchpoints used (`watchpoint_count` of the run's configuration). |
| `execution_duration` | seconds | `tracing.duration` + `mining.duration`. |
| `tracing.duration` | seconds | Sum of `tracing.seeds`. Start-up and a seed lost to a stop are not counted. |
| `tracing.seeds` | seconds | One `{seed, duration}` entry per written trace, sorted by seed number. |
| `mining.duration` | seconds | The miner's own timer (`Mining time` in `run/mine.log`). |
| `mining.requests` | requests | Board requests per step: `methods`, `loops`, `tokens` and their `total`. |
| `mining.throughput` | requests per second | `mining.requests.total` / `mining.duration`. |
| `evaluation_duration` | seconds | Wall time of `precision_recall.py`, which has no timer of its own. |

The statistics are derived from the logs in `run/`:

- A seed's duration is the time between `Start generating trace for` and `Write trace of` in
  `trace.log`. A seed that was interrupted and traced again counts once, for the run that wrote its
  trace. Except for calc, the logs of the resumed `trace.py` calls are not published; the
  `trace-resume-N` rows of `times.txt` list the seeds each resume traced (`seeds=`). The calc
  resume logs are `run/resume-N/trace.log`; see the calc section above.
- `mining.requests` adds up the `Used N requests to generalize` lines of `mine.log`.
- `evaluation_duration` is the sum of the `eval` rows of `times.txt`.

## Comparison with the Linux results

`execution_duration` in `evaluation/linux_applications/` is the wall time of `trace.py` plus
`mine.py` (`run_experiment.sh`). Here it is real time: the start-up of the tools and the seed in
progress when `trace.py` stopped are not counted. The wall time of every stage is in
`run/times.txt`.
