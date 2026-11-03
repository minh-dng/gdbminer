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
recall and F1 were the same for one and two cables in trial-0 and trial-1. There is no
`trial-2-2-cables`: its trace-only, resumed attempts were never mined and are not published.
Precision, recall and F1 are 1.0 in all five; the times come from `evaluation.json`:

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
(5, 14, 4, 17 and 18 for trial-1 one cable, trial-1 two cables, trial-2, trial-3 and trial-4).

Provenance gaps of the trial-1 to trial-4 folders:

- `run/build.log` exists only in `trial-2-1-cable`, and it is a copy of the trial-0 one-cable
  build log. The other four folders have none; their ELF hashes are in `run/state.txt`.
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
