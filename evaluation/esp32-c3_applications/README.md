# ESP32-C3 evaluation results

Results of the full pipeline (`trace.py`, `mine.py`, `precision_recall.py`) on the ESP32-C3
DevKitM-1-N4X, in the layout of `evaluation/stm32_applications/`:

```text
esp32-c3_<target>/trial-<n>-<setup>/
├── seed.N.in.trace      # one trace per seed
├── method_trees.json, loop_trees.json, mined_g.json, parsing_g.json
├── evaluation.json      # precision, recall and run statistics (below)
├── out.log
└── run/                 # provenance: configuration, build, flash and stage logs, times.txt
```

`<target>` is `cgidecode`, `arduinojson`, `libyxml`, `calc` or `jsonrs`. `<setup>` is `1-cable`
(USB-Serial/JTAG, one cable) or `2-cables` (UART bridge next to the JTAG cable).

The `calc` trial-0 folders hold 20 reused traces per setup, captured at `1baa5162` and mined on
22-23 October 2026 at `05aa19f9`. No new tracing ran. Their `tracing` fields record the original
capture, and `execution_duration` adds that capture time to the later mining time, rather than
measuring one continuous run. Both precision estimates are provisional because the exact
precision-query counts were not logged.
[PR #70](https://github.com/minh-dng/gdbminer/pull/70) records the
capture provenance, firmware hashes, resumed mining and method limitations. Calc `trace.log`
combines the original capture and resumed attempts from 16-19 October. The two-cable
`flash.log` is from that capture; the one-cable log is a reflash after tracing on 18 October,
not its unavailable initial flash. Both `build.log` files are from later runs on 24 and
26 October, with the same ELF hashes as the mining firmware; no original capture build log
is available. The `flash` and `trace` rows in calc `times.txt` are from the 24-27 October
reruns; the mining/evaluation rows are from 22-23 October. `evaluation.json` retains the
original capture's completed-seed timings. The rerun rows describe different trace inputs.

The `calc` trial-1 to trial-4 folders hold full runs (flash, trace, mine and evaluate) with 20
traces each, unlike trial-0: `trial-1-1-cable`, `trial-1-2-cables`, `trial-2-1-cable`,
`trial-3-1-cable` and `trial-4-1-cable`. Trials 3 and 4 have one cable only, because precision,
recall and F1 were the same for one and two cables in trial-0 and trial-1. Precision, recall and
F1 are 1.0 in all five; the times come from `evaluation.json`. `trial-2-2-cables` is not a full
run and is described below.

| Folder | Run (AEDT, from `run/state.txt` and the logs) | Inputs | Tracing | Mining |
| --- | --- | --- | --- | --- |
| `trial-1-1-cable` | 29-30 October 2026 | 196,733 | 26.2 h | 2.15 h |
| `trial-1-2-cables` | 30 October - 1 November 2026 | 196,746 | 28.1 h | 9.81 h |
| `trial-2-1-cable` | traced 24-25 October, mined 1 November 2026 | 196,745 | 26.4 h | 2.11 h |
| `trial-3-1-cable` | 1-2 November 2026 | 196,743 | 25.7 h | 2.10 h |
| `trial-4-1-cable` | 2-3 November 2026 | 196,756 | 25.7 h | 2.11 h |

Trial-2 one cable is split: `run/times.txt` has two flash rows, and its tracing (24 October, 14 s
flash and 94,964 s trace, the same values as the rerun rows of the trial-0 one-cable
`times.txt`) and its mining (1 November) are a week apart. Its `run/state.txt` was written at
the start of tracing and was not updated for mining. The one-cable folders use the same ELF
(`47e7c923...`, as in trial-0 one cable) and the two-cable folder another one (`b6b5b107...`, as in
trial-0 two cables); the full hashes are in `run/state.txt`.

`run/state.txt` records the code as Git HEAD `cb5f33e3` of the branch
`docs/esp32-evaluation-trial-2` for trial-1, trial-3 and trial-4, and `e2965d7b` of the same branch
for trial-2. `src/` is identical in the two commits. They descend from `05aa19f9` and do not
include the ESP32 tracer fixes that were merged on 27 October. The `git status:` line of
`run/state.txt` refers to a `git-status.txt` that is not published; it lists the changed paths
(5 and 14 for trial-1 with one and two cables, 4 and 5 for trial-2 with one and two cables, 17
for trial-3 and 18 for trial-4).

`trial-2-2-cables` holds the 20 traces of the trial-2 two-cable run of 26-27 October 2026 (AEDT).
Tracing finished (`trace exit=0`, 99,241 s in `run/times.txt`, the flash and trace rows that the
trial-0 two-cable `times.txt` calls the rerun), but the runner skipped mining and evaluation, so
the folder has no `evaluation.json`, grammar, `trace.json`, `mine.log` or `eval.log`. It is not
mined yet: [#83](https://github.com/minh-dng/gdbminer/issues/83). Its `run/state.txt` records
`e2965d7b` and the ELF `b6b5b107...`. `runner.log` is not published.

Provenance gaps of the trial-1 to trial-4 folders (`trial-2-2-cables` has no mining data):

- `run/build.log` exists only in `trial-2-1-cable` and `trial-2-2-cables`; each is a copy of the
  trial-0 build log of the same setup. The other four folders have none; their ELF hashes are in
  `run/state.txt`.
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded here either. `precision_recall.py` uses
  `PRECISION_SET_SIZE` (default 1,000, the variable is not recorded in the run), and
  `evaluation.json` has no field for it; `no_tested_inputs` is the miner's request count. The
  precision of 1.0 is therefore as provisional as in trial-0.
- Mining time varies a lot. `trial-1-2-cables` needed 9.81 h for 196,746 requests (5.6 requests per
  second), the one-cable runs about 2.1 h for about 196,700 (25.4 to 26.0 requests per second).
  Trial-0 with two cables took 11.85 h, including the resume described in PR #70. The method and
  loop counts (154,455 and 42,164) are the same in all five trials; only the tokens step differs
  (114 to 137).
- The `run/*.log`, `run/configuration.toml` and `run/build.options.json` files keep the absolute
  paths of the machine that ran them.

The `jsonrs` trial-0 folders hold one complete run per setup (flash, trace, mine and evaluate) on
28 October 2026: the desktop Rust parser (tinyjson) with the corpus of `example_programs/json`,
using six hardware watchpoints. Their `run/state.txt` has no Git lines and the `openocd:` line holds
a Python traceback instead of the version; the OpenOCD version is in `run/eval.log`. The
`run/*.log`, `run/configuration.toml` and `run/build.options.json` files keep the absolute paths of
the machine that ran them.

The `cgidecode` trial-2 to trial-4, `arduinojson` trial-2 to trial-4 and `jsonrs` trial-1 to
trial-4 folders hold full runs (flash, trace, mine and evaluate) with 20 traces each, run on 3 and
4 November 2026. `cgidecode` and `jsonrs` have one cable only from trial-2 on, and `arduinojson`
in trial-4, after the first comparison of the two setups. The values come from `evaluation.json`;
the start is the date line of `run/state.txt`.

| Folder | Start (AEDT) | Inputs | Tracing (min) | Mining (s) | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cgidecode/trial-2-1-cable` | 3 Nov 22:21 | 2,187 | 8.2 | 7 | 0.985 | 0.971 | 0.9779 |
| `cgidecode/trial-3-1-cable` | 4 Nov 01:31 | 2,185 | 8.0 | 7 | 0.973 | 0.971 | 0.9720 |
| `cgidecode/trial-4-1-cable` | 4 Nov 01:42 | 2,186 | 8.0 | 7 | 0.974 | 0.971 | 0.9725 |
| `arduinojson/trial-2-1-cable` | 3 Nov 22:32 | 4,062 | 35.4 | 42 | 0.980 | 0.977 | 0.9785 |
| `arduinojson/trial-2-2-cables` | 3 Nov 23:11 | 4,070 | 39.9 | 224 | 0.881 | 0.977 | 0.9265 |
| `arduinojson/trial-3-1-cable` | 3 Nov 23:58 | 4,182 | 35.6 | 38 | 0.967 | 0.977 | 0.9720 |
| `arduinojson/trial-3-2-cables` | 4 Nov 00:38 | 3,965 | 39.1 | 611 | 0.965 | 0.977 | 0.9710 |
| `arduinojson/trial-4-1-cable` | 4 Nov 07:45 | 3,770 | 36.0 | 12 | 0.984 | 0.977 | 0.9805 |
| `jsonrs/trial-1-1-cable` | 4 Nov 01:53 | 7,074 | 162.9 | 99 | 1.000 | 0.608 | 0.7562 |
| `jsonrs/trial-1-2-cables` | 4 Nov 04:40 | 7,063 | 176.5 | 303 | 1.000 | 0.608 | 0.7562 |
| `jsonrs/trial-2-1-cable` | 4 Nov 08:25 | 7,168 | 162.6 | 99 | 1.000 | 0.608 | 0.7562 |
| `jsonrs/trial-3-1-cable` | 4 Nov 11:12 | 7,068 | 162.6 | 99 | 1.000 | 0.608 | 0.7562 |
| `jsonrs/trial-4-1-cable` | 4 Nov 14:00 | 7,164 | 164.3 | 102 | 1.000 | 0.608 | 0.7562 |

`1-cable` is `build-1` (`CDCOnBoot=cdc`) and `2-cables` is `build-2` (`CDCOnBoot=default`, UART
bridge). They are different ELFs, so the traces differ in code addresses between the setups. Within
a target, the folders of one setup share one ELF (`run/state.txt`): one cable `45608463...`
(`cgidecode`), `5d4d5e05...` (`arduinojson`) and `5c802a35...` (`jsonrs`); two cables `442463dc...`
(`arduinojson`) and `50b72ec1...` (`jsonrs`).

Recall is the same for one and two cables in every target. `jsonrs` has precision 1.0 in both
setups. `arduinojson` precision swings between runs in both setups, and the sign of the gap flips:
two cables are higher in trial-0 and trial-1 (0.997 and 0.998 against 0.894 and 0.851), one cable
is higher in trial-2 (0.980 against 0.881) and the two are close in trial-3 (0.967 and 0.965). The
cause is not explained and is under separate investigation, so the two setups are not shown to be
equal for `arduinojson`.

Provenance gaps of these folders:

- `run/state.txt` records Git HEAD `cb5f33e3` of `docs/esp32-evaluation-trial-2` for `cgidecode`
  and `arduinojson`, and `5964ed1b` of `docs/jsonrs-open-points` for `jsonrs`. The `git status:`
  line points to a `git-status.txt` that is not published (19 to 26 changed paths for `cgidecode`
  and `arduinojson`, 1 for `jsonrs`).
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). For `cgidecode`
  and `arduinojson`, `eval.log` has `1000 * (1 - precision)` `Generated non accepting input` lines
  in every folder, which fits a 1,000-input set.
- The three two-cable folders log 39 to 46 recoverable `OpenOCD startup retry` lines
  (`LIBUSB_ERROR_PIPE`); the one-cable folders log none. `jsonrs/trial-4-1-cable` has one
  `LIBUSB_ERROR_IO` line.
- Every folder has a `run/build.log`. The five `jsonrs` logs are byte-identical to the trial-0 log
  of the same setup. The `cgidecode` and `arduinojson` logs differ from their trial-1 logs and are
  identical across the trials of one setup and target.
- Absolute paths of the machine that ran them are kept in the `run/*.log`,
  `run/configuration.toml` and `run/build.options.json` files.

The `libyxml` `trial-2-2-cables` and `trial-3-2-cables` folders hold full runs (flash, trace, mine
and evaluate) with 20 traces each, run one after the other on 5 and 6 November 2026 with the
two-cable setup. The tables add `trial-0-2-cables` and `trial-1-2-cables` for comparison. The
values come from `evaluation.json`, the logs in `run/` and `run/state.txt`. AEDT is local time; the
two earlier folders record their start in UTC, converted here (UTC+11).

| Folder | Precision | Recall | F1 | Inputs | Tracing (h) | Mining (h) | Eval (s) | Requests (methods / loops / tokens) | Throughput (requests/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `libyxml/trial-0-2-cables` | 0.976 | 0.672 | 0.7960 | 100,672 | 6.68 | 1.38 | 25 | 18,908 / 81,175 / 589 | 20.3 |
| `libyxml/trial-1-2-cables` | 0.986 | 0.672 | 0.7993 | 100,672 | 7.06 | 1.38 | 24 | 18,908 / 81,175 / 589 | 20.3 |
| `libyxml/trial-2-2-cables` | 0.997 | 1.000 | 0.9985 | 100,727 | 6.87 | 1.33 | 135 | 18,908 / 81,175 / 644 | 21.0 |
| `libyxml/trial-3-2-cables` | 0.995 | 1.000 | 0.9975 | 100,725 | 6.90 | 1.34 | 133 | 18,908 / 81,175 / 642 | 20.9 |

| Folder | Start (AEDT) | Git HEAD (`run/state.txt`) | ELF sha256 | `OpenOCD startup retry` (trace / mine / eval) |
| --- | --- | --- | --- | --- |
| `libyxml/trial-0-2-cables` | 9 Oct 03:53 | `54b314c8` | `b35b16e9...` | 62 / 3 / 1 |
| `libyxml/trial-1-2-cables` | 12 Oct 00:40 | not recorded | `48a5432e...` | 66 / 3 / 1 |
| `libyxml/trial-2-2-cables` | 5 Nov 20:15 | `565f278a` | `70cd6bc5...` | 70 / 3 / 1 |
| `libyxml/trial-3-2-cables` | 6 Nov 04:32 | `565f278a` | `70cd6bc5...` | 71 / 3 / 1 |

`trial-2-2-cables` ran until 6 November 04:31 and `trial-3-2-cables` until 12:51 (last line of
`run/eval.log`). Tracing took 24,739 s and 24,833 s, mining 4,786 s and 4,818 s, with 20 traces,
and every stage of `run/times.txt` exits with 0. The full hashes are in `run/state.txt`.

Recall is 1.0 in both new folders and 0.672 in the two earlier ones. The grammars differ too: after
sorting the rule alternatives, `trial-0-2-cables` and `trial-1-2-cables` are equal (96 nonterminals,
296 alternatives), `trial-2-2-cables` has 115 nonterminals and 437 alternatives, and
`trial-3-2-cables` 115 and 438 (they differ in 10 shared nonterminals and one nonterminal each).
The cause is not assessed. No run changed one factor at a time, and several differ between the
earlier and the new folders:

- Code: `565f278a` contains the tracer and miner fixes made after `54b314c8` (checked with
  `git merge-base --is-ancestor`; for example `7c2e798c`, `e6675aec` and `d1c5a129`), which
  `54b314c8` lacks. `trial-1-2-cables` records no Git HEAD.
- Configuration: `run/configuration.toml` of the new folders adds `set ESP_FLASH_SIZE 0` to the
  OpenOCD arguments and sets `reset_on_connect = true`; `trial-1-2-cables` does not. The seed
  directory is written as an absolute path (the same seeds: `run/seeds.sha256` is identical).
- Firmware: the ELF is another one, and the checkout and machine paths differ (`/Users/minh`
  against `/Users/dan173` in the earlier `build.options.json`).
- Traces: for all 20 seeds, the sequence of function names, arguments, watchpoint hits and stack
  depths in `trial-2-2-cables` equals that of `trial-1-2-cables`. The files differ in the code
  addresses. The 20 traces of `trial-2-2-cables` and `trial-3-2-cables` are byte-identical.

The mining requests for methods and loops are the same in all four folders; only the tokens step
differs (589 against 642 to 644). The evaluation took 133 to 135 s, against 24 to 25 s; this is not
explained either.

Provenance gaps of `libyxml/trial-2-2-cables` and `libyxml/trial-3-2-cables`:

- `run/build.log` is byte-identical in the two folders (`cmp`). One firmware build served both
  trials; no build was made per trial. The ELF sha256 (`70cd6bc5...`) is the same in both
  `run/state.txt` files, and `run/build.options.json` is identical. The build log differs from
  those of `trial-0-2-cables` and `trial-1-2-cables`.
- `run/state.txt` records Git HEAD `565f278a` in both. Its `git status:` line points to a
  `git-status.txt` that is not published (3 and 4 changed paths).
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). `eval.log` has
  3 and 5 `Generated non accepting input` lines, which fits a 1,000-input set and precisions of
  0.997 and 0.995.
- The `OpenOCD startup retry` lines (table above) are recoverable: every stage ends with exit 0.
  The logs show `libusb_get_string_descriptor_ascii()` errors, `LIBUSB_ERROR_PIPE` and, twice in
  `trial-2-2-cables/run/trace.log`, `LIBUSB_ERROR_IO`. `flash.log` has none, and `mine.log` and
  `eval.log` have the same 3 and 1 as the earlier folders.
- Other `libyxml` two-cable trial results are not part of these folders.
- The `run/*.log`, `run/configuration.toml` and `run/build.options.json` files keep the absolute
  paths of the machine that ran them.

The `libyxml` `trial-2-1-cable`, `trial-3-1-cable` and `trial-4-1-cable` folders hold full runs
(flash, trace, mine and evaluate) with 20 traces each, run one after the other on 4 and 5 November
2026 with the one-cable setup (USB-Serial/JTAG, `CDCOnBoot=cdc`, 7 hardware watchpoints). The
tables add `trial-0-1-cable` and `trial-1-1-cable` for comparison. The values come from
`evaluation.json`, the logs in `run/` and `run/state.txt`. AEDT is local time; the two earlier
folders record their start in UTC, converted here (UTC+11).

| Folder | Precision | Recall | F1 | Inputs | Tracing (h) | Mining (s) | Eval (s) | Requests (methods / loops / tokens) | Throughput (requests/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `libyxml/trial-0-1-cable` | 0.979 | 0.672 | 0.7970 | 100,673 | 6.46 | 400.2 | 10 | 18,908 / 81,175 / 590 | 251.6 |
| `libyxml/trial-1-1-cable` | 0.979 | 0.672 | 0.7970 | 100,673 | 6.46 | 269.7 | 9 | 18,908 / 81,175 / 590 | 373.3 |
| `libyxml/trial-2-1-cable` | 0.998 | 1.000 | 0.9990 | 100,726 | 6.30 | 243.8 | 121 | 18,908 / 81,175 / 643 | 413.2 |
| `libyxml/trial-3-1-cable` | 0.999 | 1.000 | 0.9995 | 100,727 | 6.31 | 244.1 | 121 | 18,908 / 81,175 / 644 | 412.6 |
| `libyxml/trial-4-1-cable` | 0.999 | 1.000 | 0.9995 | 100,727 | 6.31 | 249.9 | 122 | 18,908 / 81,175 / 644 | 403.1 |

| Folder | Start (AEDT) | End (AEDT) | Git HEAD (`run/state.txt`) | ELF sha256 | `OpenOCD startup retry` |
| --- | --- | --- | --- | --- | --- |
| `libyxml/trial-0-1-cable` | 9 Oct 12:01 | 11 Oct 01:40 | `54b314c8` | `bb929a33...` | 0 |
| `libyxml/trial-1-1-cable` | 12 Oct 09:09 | 12 Oct 15:44 | not recorded | `dbbc5554...` | 0 |
| `libyxml/trial-2-1-cable` | 4 Nov 19:35 | 5 Nov 02:01 | `cb5f33e3` | `f05c3b41...` | 0 |
| `libyxml/trial-3-1-cable` | 5 Nov 02:02 | 5 Nov 08:29 | `cb5f33e3` | `f05c3b41...` | 0 |
| `libyxml/trial-4-1-cable` | 5 Nov 08:29 | 5 Nov 14:57 | `cb5f33e3` | `f05c3b41...` | 0 |

The end is the last line of `run/eval.log`. In the three new folders every stage of `run/times.txt`
exits with 0 (flash 10 to 11 s, trace 22,687 to 22,730 s, mine 246 to 252 s, eval 121 to 122 s).
Each `Mining time` line of `run/mine.log` matches `mining.duration`, and the result line of
`run/eval.log` matches `evaluation.json`. The 2, 1 and 1 `Generated non accepting input` lines of
`eval.log` fit a 1,000-input set and precisions of 0.998, 0.999 and 0.999. `trial-0-1-cable` is
not a single uninterrupted run: its `times.txt` has three flash rows and a `trace-resume-1` row for
seeds 12, 13, 16 and 17, and its `trace.log` has 17 `Start generating trace` and 16 `Write trace
of` lines. This is a property of that earlier folder and is not described further here.

**The new folders ran from commit `cb5f33e3`, not from `main`.** `run/state.txt` records Git HEAD
`cb5f33e3` (branch `docs/esp32-evaluation-trial-2`, commit of 27 October 2026) in all three. That
commit is not an ancestor of `main`; it shares the merge base `05aa19f9` with it and carries seven
documentation commits that `main` does not have. Every line of the `git-status.txt` files that the
`git status:` line points to (28, 29 and 30 changed paths, not published) starts with `??`, so
they list untracked paths only, namely result folders and `example_programs/calc/calc.c`; no
tracked file was modified. The checks with `git merge-base --is-ancestor` give:

| Commit | `54b314c8` (trial-0) | `cb5f33e3` (trial-2 to trial-4) | `main` |
| --- | --- | --- | --- |
| `7c2e798c` miner: preserve every partial omission of optional symbols | no | yes | yes |
| `e6675aec` connection: stop when an input crashes the ESP32 firmware | no | yes | yes |
| `94690b6c` firmware: skip the HWCDC flush in the json, cgidecode and xml wrappers | no | yes | yes |
| `aad1dc4f` config: reset the ESP32-C3 after GDB attaches | no | yes | yes |
| `c1753725` config: turn off OpenOCD flash support in the ESP32-C3 configurations | no | yes | yes |
| `b3bcccc7` tracer: keep the target halted after GDB aborts an execution command | no | yes | yes |
| `0e288191`, `12bdd858` tracer: limit each OpenOCD start attempt and read its output once more | no | no | yes |
| `7a8f1526` tracer: report an exited ESP32 GDB instead of a stop timeout | no | no | yes |
| `d1c5a129` firmware: set watchpoints without C casts, drop type checks | no | no | yes |
| `87c16375` config: add the `GDB.frame_arguments` option | no | no | yes |

`trial-1-1-cable` records no Git HEAD. `94690b6c` changes `example_firmware/esp32-c3_xml/main.ino`.
The effect of the commits that `cb5f33e3` lacks is not assessed. `example_firmware/esp32-c3_xml`
is the same in `cb5f33e3` and in `565f278a`, the HEAD of the two-cable `libyxml` folders above.

Recall is 1.0 in the three new folders and 0.672 in the two earlier ones, and the grammars differ.
After sorting the rule alternatives, `trial-0-1-cable` and `trial-1-1-cable` are equal (96
nonterminals, 296 alternatives) and the three new folders are equal to each other (115 and 438);
`trial-1-1-cable` and `trial-2-1-cable` differ in 101 nonterminals. `mined_g.json`,
`method_trees.json` and `loop_trees.json` are byte-identical among the three new folders and among
the two earlier ones, and differ between the two groups. The two-cable folders above show the same
split: recall 0.672 for trial-0 and trial-1, 1.0 for trial-2 and trial-3. The files show these
differences between the earlier and the new folders; the cause is not assessed, and no run changed
one factor at a time:

- Code: see the table above. The recorded HEADs differ, and `trial-1-1-cable` has none.
- Configuration: `run/configuration.toml` of the new folders adds `set ESP_FLASH_SIZE 0` to the
  OpenOCD arguments, drops the `-s` script directory and sets `reset_on_connect = true`, where
  `trial-1-1-cable` has `false`. The seed directory is an absolute path. `run/seeds.sha256` is
  identical in all five folders (the same seeds). The three new configurations differ only in
  `output_directory`.
- Firmware: the ELF is another one in each of the three groups (`trial-0-1-cable`,
  `trial-1-1-cable`, the new folders), and the checkout and machine paths in
  `run/build.options.json` differ (`/Users/dan173` in the earlier folders, `/Users/minh` in the new
  ones).
- Traces: the sequence of function names, arguments, watchpoint hits and stack depths of all 20
  seeds equals that of `trial-1-1-cable`; the files differ in the code addresses. For
  `trial-0-1-cable` the sequences of 3 seeds differ (for seed 1, the first difference is a
  `yxml_pushstack` argument at record index 490). Among the new folders, 19 of 20 traces are
  byte-identical in each pair with `trial-2-1-cable`; seed 12 in `trial-3-1-cable` and seed 3 in
  `trial-4-1-cable` differ from `trial-2-1-cable`, again first at record index 490, a
  `yxml_pushstack` argument (`0` against `1070145536`).
- Mining: the methods and loops requests are equal in all five folders. The tokens step is 643 and
  644 against 590. The evaluation took 121 to 122 s, against 9 and 10 s; this is not explained
  either.

Provenance gaps of `libyxml/trial-2-1-cable`, `trial-3-1-cable` and `trial-4-1-cable`:

- `run/build.log` is byte-identical in the three folders (`cmp`). One firmware build served all
  three trials; no build was made per trial. The ELF sha256 (`f05c3b41...`) is the same in the three
  `run/state.txt` files, and `run/build.options.json` is identical. The build log differs from
  those of `trial-0-1-cable` and `trial-1-1-cable`, which also differ from each other.
- `run/state.txt` records Git HEAD `cb5f33e3` in all three, which is not on `main` (see above). Its
  `git status:` line points to a `git-status.txt` that is not published.
- The `openocd:` line in `run/state.txt` holds a Python traceback instead of the version. The
  OpenOCD version (`v0.12.0-esp32-20260831`) is in `run/eval.log`.
- The precision-query count is not recorded (`PRECISION_SET_SIZE`, default 1,000). Precision stays
  provisional apart from the `eval.log` fit stated above.
- The scan of `trace.log`, `mine.log`, `eval.log` and `flash.log` for `ERROR`, `Traceback`,
  `Timeout`, `restart`, `abort`, `Stack canary`, `LIBUSB_ERROR` and `failed` finds nothing, and no
  `OpenOCD startup retry` line exists. No `No suitable loop` warning appears in `mine.log`. Each
  `trace.log` has 20 `Start generating trace` and 20 `Write trace of` lines.
- The `run/*.log`, `run/configuration.toml` and `run/build.options.json` files keep the absolute
  paths of the machine that ran them.

## evaluation.json

| Field | Unit | Meaning |
| --- | --- | --- |
| `precision`, `recall`, `f1` | ratio, 0 to 1 | Written by `src/eval/precision_recall.py`. |
| `no_tested_inputs` | requests | Inputs the miner sent to the board. Equals `mining.requests.total`. |
| `watchpoint_count` | count | Hardware watchpoints used (`watchpoint_count` of the run's configuration). |
| `execution_duration` | seconds | `tracing.duration` + `mining.duration`. |
| `tracing.duration` | seconds | Sum of `tracing.seeds`. Start-up and a seed lost to a stop are not counted. |
| `tracing.seeds` | seconds | One `{seed, duration}` entry per written trace, sorted by seed number. |
| `mining.duration` | seconds | The miner's own timer (`Mining time` in `run/mine.log`); for resumed calc, see below. |
| `mining.requests` | requests | Board requests per step: `methods`, `loops`, `tokens` and their `total`. |
| `mining.throughput` | requests per second | `mining.requests.total` / `mining.duration`. |
| `evaluation_duration` | seconds | Wall time of `precision_recall.py`, which has no timer of its own. |

The statistics are derived from the logs in `run/`:

- A seed's duration is the time between `Start generating trace for` and `Write trace of` in
  `trace.log`. A seed that was interrupted and traced again counts once, for the run that wrote its
  trace. Except for calc, resumed `trace.py` logs are not published; the `trace-resume-N` rows of
  `times.txt` list the seeds each resume traced (`seeds=`).
- `mining.requests` adds up the `Used N requests to generalize` lines of `mine.log`.
- Resumed calc `mine.log` concatenates the original and resumed mining logs. Its
  `mining.duration` adds the methods duration derived from timestamps and the resumed timer.
  Failed startup and waiting time are excluded; PR #70 explains the split and `times.txt`
  keeps the invocation wall times. Its `eval.log` includes the failed and successful attempts.
- `evaluation_duration` is the sum of the `eval` rows of `times.txt`.

## Comparison with the Linux results

`execution_duration` in `evaluation/linux_applications/` is the wall time of `trace.py` plus
`mine.py` (`run_experiment.sh`). Here it is real time: the start-up of the tools and the seed in
progress when `trace.py` stopped are not counted. The wall time of every stage is in
`run/times.txt`.
