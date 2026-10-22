# ESP32-C3 calc: reusable native USB trial-0 traces

These twenty completed traces and their exact seed files are inputs for mining on another
computer. Tracing finished on 18 October 2026. The later mining attempts stopped before producing
a full grammar or evaluation score.

## Provenance

- Capture source revision: `1baa516251d70c823decc1a49695ad599363e4e8`.
- Capture setup: ESP32-C3 v1.1, board `A0:F2:62:01:70:28`, one native USB cable, eight read
  watchpoints and debugger unwind metadata for ROM `strtol`.
- Dataset: twenty original calc seeds, traced during 16-18 October with resumptions. Each retained
  trace passed complete seed-byte coverage and nonempty-stack checks.
- Original archive commit: `013c75eb`, on the local thesis branch. The checksums also match the
  declared dataset of the HWCDC no-flush mining attempt on 20 October.
- Transfer branch base: `05aa19f9ebc55889bcbc60235890a82b817219f1`, the remote `main` tip checked on
  22 October 2026.

The traces total 33,330,459 bytes. `run/trace-check.json` preserves each trace's instruction count,
covered byte count and SHA-256. `run/SHA256SUMS` covers all twenty traces, twenty seed files and
that checkpoint file, with paths relative to this directory.

The original capture firmware ELF SHA-256 is:

```text
c7f1fde246d85b6280c03f298b75220da7f4395c2264316e5ae7f7993682c02d
```

The original debugger ROM ELF SHA-256 is:

```text
342a7d3b8040d842767baff9224879fea67dd7ed3abd2c95d030699c6586644e
```

## Fetch on the other computer

From the repository root, fetch and extract this directory into the current checkout:

```sh
git fetch origin data/esp32c3-calc-trial0-traces
git archive FETCH_HEAD \
  evaluation/esp32-c3_applications/esp32-c3_calc/trial-0-1-cable | tar -x
calc_trace_dataset=evaluation/esp32-c3_applications/esp32-c3_calc/trial-0-1-cable
(cd "$calc_trace_dataset" && sha256sum -c run/SHA256SUMS)
```

On macOS, use `shasum -a 256 -c run/SHA256SUMS` for the checksum command.

## Start at mining

Copy the traces into a new output base. This command requires that the base does not exist:

```sh
calc_reuse_output=output/esp32-c3_calc-reused-trial0
test ! -e "$calc_reuse_output" &&
  mkdir -p "$calc_reuse_output/trial-0" &&
  cp "$calc_trace_dataset"/seed.*.in.trace "$calc_reuse_output/trial-0/"
```

Use a copy of the other computer's working native USB calc TOML with these settings:

- `BASIC.output_directory`: `./output/esp32-c3_calc-reused-trial0`.
- `BASIC.seed_directory`: the included `run/seeds` directory. Write its expanded repository path
  into the TOML; shell variable names are not expanded by the configuration loader.
- `BASIC.binary_file`, `GDB.esp32c3.rom_elf`, serial port and debugger paths: the files and devices
  used by that computer's flashed calc firmware.
- `BASIC.eval_directory`: that campaign's calc evaluation corpus.

Run the mining stage, then the evaluation stage, with the copied configuration. Mining derives
its control-flow graphs from these trace records and sends membership queries to the board.
Precision evaluation also queries the board; recall uses the corpus offline.

## Reporting reuse with current main

The relevant changes since capture include the miner's optional-rule fix, connection error and
resend handling, native USB flushing, and the calc loop-task stack size. The instruction trace
collector is unchanged in that comparison. Report the new run as mining with reused trial-0
traces, and record its own host revision, firmware hash, configuration, query policy and RNG seeds.
The original tracing durations belong to the resumed capture campaign.

## Mining on 22 October 2026

The trees, grammars, `out.log`, `evaluation.json` and the new files in `run/` (`state.txt`,
`times.txt`, `configuration.toml`, `build.options.json`, `mine.log`, `eval.log`, `run.sh`) come
from mining these traces on `main` `05aa19f9`, which includes the optional-symbol fix of #59.
Mining took 7,977 s and 196,728 board queries; precision, recall and F1 are reported as 1.0.
Recall uses the 1,000 inputs of `example_programs/calc/eval`.

The evaluation lasted 4 s. The code defaults to 1,000 precision queries and the runner does not
set `PRECISION_SET_SIZE`, but the inherited environment and per-input answers were not recorded.
The log confirms the score, not the exact query count. Precision 1.0 remains provisional until
that count is independently confirmed.

The rebuilt ELF (`47e7c923...844c`) differs from the capture ELF above. Only 5 of the 332 distinct
traced addresses resolve to the traced function name in it (`addr2line -f`). The miner builds its
control-flow graphs from the traces alone (`src/miner/tree_builder.py:58`); the ELF gives GDB its
symbols, and the board answers the queries. The address shift should therefore not change the
mined grammar. This is a reading of the code, not a test.

`evaluation.json` has no `tracing` or `execution_duration` field, because these runs did not trace.
