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
