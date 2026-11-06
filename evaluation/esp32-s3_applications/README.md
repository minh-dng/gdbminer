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

`<target>` is `cgidecode`, `arduinojson` or `libyxml`. `<setup>` is `1-watchpoint` or
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
  trace. The logs of the resumed `trace.py` calls are not published; the `trace-resume-N` rows of
  `times.txt` list the seeds each resume traced (`seeds=`).
- `mining.requests` adds up the `Used N requests to generalize` lines of `mine.log`.
- `evaluation_duration` is the sum of the `eval` rows of `times.txt`.

## Comparison with the Linux results

`execution_duration` in `evaluation/linux_applications/` is the wall time of `trace.py` plus
`mine.py` (`run_experiment.sh`). Here it is real time: the start-up of the tools and the seed in
progress when `trace.py` stopped are not counted. The wall time of every stage is in
`run/times.txt`.
