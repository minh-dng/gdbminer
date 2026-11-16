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

`<target>` is `cgidecode`, `arduinojson`, `libyxml`, `calc` or `jsonrs`. `<setup>` is
`1-watchpoint` or `2-watchpoints` (hardware watchpoints used while tracing; `watchpoint_count` of
the configuration).

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

## Jsonrs trial-0 folder

`jsonrs/trial-0-2-watchpoints` holds one complete run (flash, trace, mine and evaluate) of the
desktop Rust parser (tinyjson 2.5.1) with the corpus of `example_programs/json`, using two hardware
watchpoints (`watchpoint_count` 2, DBREAK0 and DBREAK1). There is no one-watchpoint `jsonrs` run.
The run was not resumed: `run/times.txt` has one row per stage, all with exit code 0, and the folder
has no `build.log`. The values come from `evaluation.json`, the logs in `run/` and `run/state.txt`;
AEDT is local time.

| Folder | Start (AEDT) | End (AEDT) | Inputs | Tracing (h) | Mining (s) | Eval (s) | Requests (methods / loops / tokens) | Throughput (requests/s) | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `jsonrs/trial-0-2-watchpoints` | 28 Oct 09:38 | 29 Oct 05:36 | 7,073 | 19.89 | 141.8 | 9 | 5,975 / 857 / 241 | 49.9 | 1.000 | 0.608 | 0.7562 |

Tracing is the sum of the 20 seed durations (71,619.5 s; `times.txt` has 71,622 s for the call).
Tracing ended on 29 October 05:32, mining ran from 05:33 to 05:35 and evaluation from 05:36:22 to
05:36:29. The `Mining time` line of `run/mine.log` (141.8 s) equals `mining.duration`, and the
result line of `run/eval.log` equals `evaluation.json`. The board is `E8:06:90:95:F2:70` on
`/dev/cu.usbmodem101` with GDB port 3335, and the ELF sha256 is
`e4d636325e5c1b48d44d4d8894d761ef7724d1d6093b2f9f9190696655aa0eba`. The 20 seeds and the
1,000-input evaluation corpus are those of `run/seeds.sha256` and `run/eval.sha256`.

Compared with the ESP32-C3 `jsonrs` folders in `evaluation/esp32-c3_applications/`, which use six
hardware watchpoints: precision 1.0 and recall 0.608 are the values of all seven C3 folders. The
methods and loops requests (5,975 and 857) are equal; the tokens step is 241 against 231 to 336.
After sorting the rule alternatives, the S3 grammar has 35 nonterminals and 157 alternatives, as
each C3 grammar does, and its nonterminal names differ from theirs in 65 nonterminals. The cause
of that difference is not assessed.

Provenance gaps of this folder:

- `run/state.txt` records Git HEAD `c569282d`, a detached HEAD with a clean tree (0 changed paths).
  It is not on `main`: it descends from `1937b8ef`, which is on `main`, through three commits that
  `main` does not have (the C3 and S3 `jsonrs` targets in an earlier form and a C3 post-mortem).
  `git merge-base --is-ancestor` shows that it contains `7c2e798c`, `e6675aec`, `94690b6c`,
  `aad1dc4f`, `0e288191`, `7a8f1526`, `d1c5a129`, `87c16375` and `1937b8ef`, and lacks the
  commits that put the `jsonrs` targets on `main` (for example `e49bbb28`). Between that HEAD and
  `main`, `src/`, the S3 `jsonrs` firmware sources and `example_programs/` do not differ; the
  differences in the S3 `jsonrs` directory are its `README.md` and the `port` line of its two
  configurations (`/dev/cu.usbmodem2101` against an empty string). The `git status:` line points
  to a `git-status.txt` that is not published (it is empty).
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). `eval.log` has
  no `Generated non accepting input` line, which fits precision 1.0 but does not show the count, so
  the precision of 1.0 stays provisional.
- There is no `run/build.log`: the source folder has none. The ELF is identified by the sha256
  above and the build by `run/build.options.json`.
- `trace.log` has 146 `OpenOCD startup retry` lines, 149 `LIBUSB_ERROR_IO` lines and two failed
  first attach attempts (28 October 20:08 and 23:22; no second attempt failed). All 20 traces were
  written (20 `Start generating trace for` and 20 `Write trace of` lines). `flash.log`,
  `mine.log` and `eval.log` have no match for `ERROR`, `Traceback`, `Timeout`, `restart`, `abort`,
  `Stack canary`, `LIBUSB_ERROR` or `failed` and no retry line. `mine.log` has no `No suitable loop`
  warning.
- Absolute paths of the machine that ran it are kept in the `run/*.log`, `run/configuration.toml`
  (the seed directory) and `run/build.options.json` files.

## Trial-5 to trial-9 folders

These nine folders hold full runs (flash, trace, mine and evaluate) with 20 traces each, using two
hardware watchpoints: `arduinojson` `trial-5` to `trial-8` and `cgidecode` `trial-5` to `trial-9`.
They were run on 15 and 16 November 2026. With them `cgidecode` has two-watchpoint `trial-0` to
`trial-9`, and `arduinojson` has two-watchpoint `trial-0` to `trial-8`. The one-watchpoint folders
of both targets end at `trial-4`. The values come from `evaluation.json`, the logs in `run/` and
`run/state.txt`; AEDT is local time.

The thesis testing campaign ended with these runs, so the gaps are deliberate and no run failed:
`arduinojson` two-watchpoint `trial-9`, and one-watchpoint `trial-5` and later of both targets,
were not run. For scope only: an S3 `calc` one-watchpoint run was started and stopped on purpose at
13 of 20 traces when the campaign ended. It was not mined or exported and has no folder.

Two boards ran the nine runs, one run at a time on each board and both boards in parallel. Every
run flashed its own board first. The end is the last time stamp of `run/eval.log`.

| Board (`run/state.txt`) | Runs in order (start, end) |
| --- | --- |
| `E8:06:90:95:F2:70`, `/dev/cu.usbmodem101`, GDB port 3335 | `cgidecode` `trial-5` (15 Nov 15:15, 15:59), `trial-7` (15:59, 16:44), `trial-9` (16:44, 17:28); `arduinojson` `trial-6` (17:28, 21:42), `trial-7` (21:42, 16 Nov 02:00) |
| `E8:06:90:95:80:6C`, `/dev/cu.usbmodem3101`, GDB port 3334 | `cgidecode` `trial-6` (15 Nov 15:16, 16:00), `trial-8` (16:00, 16:44); `arduinojson` `trial-5` (16:45, 22:59), `trial-8` (23:00, 16 Nov 03:23) |

Every stage of `run/times.txt` has `exit=0` once, with one exception: `arduinojson/trial-5` has two
`mine` rows (see below). No folder has `errors.log`, `resume-*` material or `runner.log`.

### Results

All values come from `evaluation.json`. Recall is constant per target: 0.971 for `cgidecode`, and
0.977 or 0.998 to 0.999 for `arduinojson`.

| Folder | Start (AEDT) | Precision | Recall | F1 | Inputs | Tracing (h) | Mining (s) | Eval (s) | Requests (methods / loops / tokens) | Throughput (requests/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `arduinojson/trial-5-2-watchpoints` | 15 Nov 16:45 | 0.901 | 0.977 | 0.9375 | 4,432 | 4.17 | 69.9 | 20 | 1,378 / 1,071 / 1,983 | 63.4 |
| `arduinojson/trial-6-2-watchpoints` | 15 Nov 17:28 | 0.838 | 0.998 | 0.9110 | 4,251 | 4.17 | 34.9 | 22 | 1,378 / 1,071 / 1,802 | 121.8 |
| `arduinojson/trial-7-2-watchpoints` | 15 Nov 21:42 | 0.857 | 0.999 | 0.9226 | 4,342 | 4.21 | 99.3 | 33 | 1,378 / 1,071 / 1,893 | 43.7 |
| `arduinojson/trial-8-2-watchpoints` | 15 Nov 23:00 | 0.976 | 0.977 | 0.9765 | 3,991 | 4.32 | 24.6 | 23 | 1,378 / 1,071 / 1,542 | 162.2 |
| `cgidecode/trial-5-2-watchpoints` | 15 Nov 15:15 | 0.976 | 0.971 | 0.9735 | 2,185 | 0.67 | 15.1 | 9 | 287 / 307 / 1,591 | 144.7 |
| `cgidecode/trial-6-2-watchpoints` | 15 Nov 15:16 | 0.982 | 0.971 | 0.9765 | 2,183 | 0.68 | 15.0 | 9 | 287 / 307 / 1,589 | 145.5 |
| `cgidecode/trial-7-2-watchpoints` | 15 Nov 15:59 | 0.983 | 0.971 | 0.9770 | 2,187 | 0.69 | 51.6 | 9 | 287 / 307 / 1,593 | 42.4 |
| `cgidecode/trial-8-2-watchpoints` | 15 Nov 16:00 | 0.980 | 0.971 | 0.9755 | 2,186 | 0.69 | 15.0 | 9 | 287 / 307 / 1,592 | 145.7 |
| `cgidecode/trial-9-2-watchpoints` | 15 Nov 16:44 | 0.975 | 0.971 | 0.9730 | 2,187 | 0.68 | 15.0 | 8 | 287 / 307 / 1,593 | 145.8 |

Cross-checks, all nine folders: each `Mining time` line of the last `mine` call equals
`mining.duration`; the 20 per-seed tracing durations add up to `tracing.duration`; the three request
types add up to `no_tested_inputs`; the result line of `run/eval.log` equals `evaluation.json`; each
`trace.log` has 20 `Start generating trace for` and 20 `Write trace of` lines; the number of
`Generated non accepting input` lines in `eval.log` equals `1000 * (1 - precision)` (24, 18, 17, 20
and 25 for `cgidecode`; 99, 162, 143 and 24 for `arduinojson`). The `cgidecode` mining time of
`trial-7` (51.6 s against 15.0 to 15.1 s) includes one failed attach attempt in `run/mine.log` (see
the retries below); the request counts are those of the other `cgidecode` runs.

### Code, firmware and USB dropouts

`OpenOCD startup retry` lines and `; USB reset` lines, counted per log. A failed first attach
attempt (`S3 attach attempt 1 failed: S3 OpenOCD startup timed out after 30s`) shows as 73 or 74
retry lines and one reset line. In every `trace.log` and `mine.log` the number of reset lines equals
the number of failed first attempts, and no second attempt failed, so every dropout was recovered.
`eval.log` and `flash.log` have no retry line.

| Folder | Git HEAD | ELF sha256 | Board | Trace: retries / resets | Mine: retries / resets |
| --- | --- | --- | --- | --- | --- |
| `arduinojson/trial-5-2-watchpoints` | `c8ea5336` | `553c65e5...` | `80:6C` | 222 / 3 | 74 / 1 |
| `arduinojson/trial-6-2-watchpoints` | `c8ea5336` | `553c65e5...` | `F2:70` | 296 / 4 | 0 / 0 |
| `arduinojson/trial-7-2-watchpoints` | `c8ea5336` | `553c65e5...` | `F2:70` | 589 / 8 | 74 / 1 |
| `arduinojson/trial-8-2-watchpoints` | `c8ea5336` | `553c65e5...` | `80:6C` | 369 / 5 | 0 / 0 |
| `cgidecode/trial-5-2-watchpoints` | `c8ea5336` | `a6c7d080...` | `F2:70` | 147 / 2 | 0 / 0 |
| `cgidecode/trial-6-2-watchpoints` | `c8ea5336` | `a6c7d080...` | `80:6C` | 221 / 3 | 0 / 0 |
| `cgidecode/trial-7-2-watchpoints` | `c8ea5336` | `a6c7d080...` | `F2:70` | 222 / 3 | 74 / 1 |
| `cgidecode/trial-8-2-watchpoints` | `c8ea5336` | `a6c7d080...` | `80:6C` | 221 / 3 | 0 / 0 |
| `cgidecode/trial-9-2-watchpoints` | `c8ea5336` | `a6c7d080...` | `F2:70` | 148 / 2 | 0 / 0 |

No `trace.log`, `mine.log`, `eval.log` or `flash.log` has a `TimeoutError`, `Traceback` or `Stack
canary` line, and no `out.log` has a `TimeoutError` or `Traceback` line. The `LIBUSB_ERROR_IO`
lines accompany the retries; `arduinojson/trial-6-2-watchpoints` also has three in `mine.log` and
one in `eval.log` without a retry or a failed attach. The traces show no effect of the dropouts:
the 20 seed traces of every folder are byte-identical to those of `trial-3-2-watchpoints`
(`arduinojson`) and `trial-4-2-watchpoints` (`cgidecode`) on this branch.

### First mining attempt of `arduinojson/trial-5-2-watchpoints`

`run/times.txt` has two `mine` rows:

```text
flash exit=0 seconds=13
trace exit=0 seconds=15015
mine exit=143 seconds=7212
mine exit=0 seconds=72
eval exit=0 seconds=20
```

The first attempt ended with exit 143 (128 plus SIGTERM) after 7,212 s, which fits a runner limit
of 2 h (7,200 s). The runner is not part of this repository. The second attempt, started at 22:57
without any intervention, finished in 72 s (the miner's own timer: 69.9 s). The published
`run/mine.log` holds only the second attempt. `out.log` is longer (9,684 lines) because it holds
both attempts, so the first one is visible there:

- Attempt 1 started at 20:57:10 (`out.log` line 7462), 32 s after the last trace was written. It
  finished the methods step (1,378 requests, 20:57:18) and the loops step (1,071 requests,
  20:57:25), the same counts as attempt 2, and began the tokens step. The last progress line is
  `token_generalizer.py:168 find_max_widened()` at 20:57:31.999 (line 7815).
- Then `out.log` has 237 lines `sut_connection.py:110 input_accepted()] Connection timeout!`, one
  every 30.1 to 30.3 s, without a gap, from 20:58:03 (line 7816) to 22:56:42 (line 8052), and no
  other line in between. The miner reported no progress for two hours.
- The runner's `errors.log` (in the run checkout under `output/s3-eval-trial-5/`, not published)
  keeps only the tail of the attempt: the last four warnings, then the warning of the Python
  `resource_tracker` that follows the termination.

```text
2026-11-15 22:57:22 [b json-2-watchpoints] mine exit 143 (attempt 1)
    | 2026-11-15 22:55:11,830 [WARNING sut_connection.py:110 input_accepted()] Connection timeout!
    | 2026-11-15 22:55:42,028 [WARNING sut_connection.py:110 input_accepted()] Connection timeout!
    | 2026-11-15 22:56:12,229 [WARNING sut_connection.py:110 input_accepted()] Connection timeout!
    | 2026-11-15 22:56:42,417 [WARNING sut_connection.py:110 input_accepted()] Connection timeout!
    | .../multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 9 leaked semaphore objects to clean up at shutdown
```

The cause of the stall is not known. No other published log has a `Connection timeout!` line, and
the second attempt, started on the same board, ran without it. The published grammar and
`evaluation.json` come from the second attempt. `execution_duration` (15,082.2 s) is tracing plus
the mining time of that attempt; the 7,212 s of the first attempt are not counted, so the wall time
of this run is longer (6.25 h, from 16:45 to 22:59).

### Precision of `arduinojson`

Precision is 0.838 to 0.976 in the four new `arduinojson` folders, and 0.847 to 0.982 in
`trial-2` to `trial-4` on this branch. Recall is 0.977 or 0.998 to 0.999. The table lists all
two-watchpoint `arduinojson` trials from `trial-2` on; `trial-0` and `trial-1` (precision 0.997 and
0.992, recall 0.881) have other traces and a smaller grammar and are left out.

| Trial | Precision | Recall | Inputs | Tokens requests | Delimiters widened in `parsing_g.json` |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.981 | 0.977 | 4,031 | 1,582 | none |
| 3 | 0.982 | 0.999 | 4,008 | 1,559 | `[` |
| 4 | 0.847 | 0.999 | 4,348 | 1,899 | `}` and `[` |
| 5 | 0.901 | 0.977 | 4,432 | 1,983 | `,` |
| 6 | 0.838 | 0.998 | 4,251 | 1,802 | `:` |
| 7 | 0.857 | 0.999 | 4,342 | 1,893 | `}` and `[` |
| 8 | 0.976 | 0.977 | 3,991 | 1,542 | none |

What the files show:

- **Same input, other grammar.** The 20 seed traces, `mined_g.json`, `method_trees.json`,
  `loop_trees.json` and `trees.json` of `trial-2` to `trial-8` are the same in both setups (the
  JSON files differ only in the seed directory path). The methods and loops requests are 1,378 and
  1,071 in every run. `mine.py` writes `mined_g.json` before the token step and `parsing_g.json`
  after it. Only `parsing_g.json` differs, and only in the token step: sorted by alternatives it
  gives five grammars in these seven runs (79 or 80 nonterminals, 353 or 355 alternatives;
  `trial-2` and `trial-8` are equal, and so are `trial-4` and `trial-7`).
- **The grammars differ in one widened token.** In every grammar one token of the seeds is widened
  to `<__ASCII_PRINTABLE_s__>` (any run of printable ASCII) and used by the number rules. In
  `trial-2` and `trial-8` that is all. In the other five runs the widened token also stands in for
  a structural delimiter: the opening `[` of an array (rule `parse_array.0-0-c`), the closing `}` of
  an object (`parse_object.0`), the `:` of an object member (`parse_object.0-3`) or the `,` between
  members (`parse_object.0-9`). The table above lists which. The delimiter in each rule is read
  from the grammars where it is not widened.
- **Precision follows the widened delimiter.** Widening `}`, `:` or `,` goes with precision 0.838 to
  0.901; widening `[` alone (`trial-3`) does not (0.982). The same holds in the one-watchpoint
  folders on this branch: `trial-3` and `trial-4` widen no delimiter (0.981), `trial-2` widens `[`
  and `,` (0.887, recall 0.999), and `trial-1` widens `}` (0.850, with the earlier grammar).
- **Recall follows `[` and `:`.** Recall is 0.998 or 0.999 when `[` or `:` is widened (`trial-3`,
  `trial-4`, `trial-6`, `trial-7`) and 0.977 when neither is (`trial-2`, `trial-5`, `trial-8`).
- **The number of inputs is a symptom.** `trial-4` to `trial-7` (precision 0.838 to 0.901) have
  4,251 to 4,432 inputs; `trial-2`, `trial-3` and `trial-8` (0.976 to 0.982) have 3,991 to 4,031.
  The methods and loops requests are equal, so the difference is the tokens step (1,802 to 1,983
  against 1,542 to 1,582 requests).
- **Sampling noise is small.** The precision inputs are random draws from the grammar (1,000 per
  run, see gaps), which gives a standard error of about 0.004 at 0.98 and 0.011 at 0.85. Runs with
  the same grammar agree within that: `trial-4` and `trial-7` have 0.847 and 0.857; `trial-2`,
  `trial-8` and the one-watchpoint `trial-3` and `trial-4` have 0.976 to 0.981.
- **Not explained.** Why the token step widens different delimiters from the same inputs is not
  established. The step calls the unseeded `random.choice` (twice in
  `src/miner/token_generalizer.py`) to fill the rest of a tree before it asks the board whether a
  replacement is accepted, which is one candidate. `src/miner` and `src/eval` do not differ between
  `cb5f33e3` (`trial-3`, `trial-4`) and `c8ea5336` (`trial-5` to `trial-8`), so a code change does
  not explain the spread. No file here tests the candidate. The USB dropouts do not explain it
  either: the traces are identical, and the two folders with a failed attach in `mine.log`
  (`trial-5`, `trial-7`) have precision 0.901 and 0.857, the two without (`trial-6`, `trial-8`)
  0.838 and 0.976. Among these four runs the boards show no pattern (`80:6C`: 0.901 and 0.976,
  `F2:70`: 0.838 and 0.857). A mean of precision over trials describes this pipeline with this
  unseeded miner; it is not a property of the target or the board.

### Reading the results for `cgidecode`

Precision is 0.975 to 0.983 and recall is 0.971 in all five folders. Together with `trial-0` to
`trial-4` the ten two-watchpoint folders have precision 0.975 to 0.983. After sorting the rule
alternatives, `trial-2` to `trial-9` give two grammars (11 nonterminals, 179 alternatives, or 180 in
`trial-5` and `trial-7`); `mined_g.json` is identical to that of `trial-4` in all five folders.

### Provenance gaps

- `run/state.txt` records Git HEAD `c8ea5336`, which is on `main`, for all nine folders. It contains
  the tracer, miner and firmware fixes `0e288191`, `12bdd858`, `7a8f1526`, `d1c5a129`, `87c16375`
  and `1937b8ef` (`git merge-base --is-ancestor`). Compared with `cb5f33e3`, the HEAD of
  `trial-3` and `trial-4`, only five files differ in `src/`: `esp32_instance.py`,
  `esp32c3_instance.py`, `esp32s3_instance.py`, `sut_instance.py` and `util/config.py`. `src/miner`,
  `src/eval` and the `esp32-s3_json` and `esp32-s3_cgidecode` firmware sources do not differ. The
  effect of the tracer changes on the results is not assessed.
- The ELFs are new builds: `553c65e5...` for `arduinojson` and `a6c7d080...` for `cgidecode`.
  One build per target served all its trials (the same ELF in every `run/state.txt`). They differ
  from the ELFs of `trial-2` to `trial-4` (`5be11988...` and `010d8184...`); the cause was not
  examined. `run/build.options.json` differs from that of `trial-4` only in the `sketchLocation`
  path. `run/seeds.sha256`, `run/eval.sha256` and `run/configuration.toml` equal those of
  `trial-4-2-watchpoints` except for `seed_directory` and `output_directory`.
- There is no `run/build.log`: the source folders have none. The ELF is identified by the sha256 in
  `run/state.txt` and the build by `run/build.options.json`.
- Left out: `run/git-status.txt`, as in the earlier folders. The `git status:` line of
  `run/state.txt` points to it and keeps the counts: 4, 5, 6 and 7 changed paths (`arduinojson`
  `trial-5` to `trial-8`) and 0, 0, 1, 2 and 4 (`cgidecode` `trial-5` to `trial-9`). All entries are
  untracked paths (`??`, result folders of other trials); no tracked file was modified.
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). The
  `Generated non accepting input` count above fits 1,000 queries, which is the only evidence.
- The nine folders differ from `trial-3` and `trial-4` in the board: those used
  `E8:06:90:95:F2:70` only, these used both boards.
- Absolute paths of the machine that ran them are kept in the `run/*.log`, `run/configuration.toml`
  and `run/build.options.json` files, and in `out.log`.
- In eight logs (`arduinojson/trial-5-2-watchpoints` to `trial-8-2-watchpoints`, `out.log` and
  `run/mine.log`) a carriage return before a line feed was normalised to a line feed on commit: two
  in `trial-5` `out.log` (one per mining attempt), one in each of the other seven. It is the
  `\r` of a log line that prints a blacklisted token.

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
