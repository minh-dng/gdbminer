# ESP32-C3 calc: reusable UART (two-cable) trial-0 traces

These twenty completed traces and their exact seed files are inputs for re-mining the two-cable
calc setup on another computer. They sit beside the native USB set in `../trial-0-1-cable/`. The
earlier mining of these traces (precision and recall 1.0) used `empty_rule_removal = "released"`
and predates the connection-error, resend and calc loop-stack fixes now on `main`.

## Provenance

- Capture source revision: `1baa516251d70c823decc1a49695ad599363e4e8`.
- Capture setup: ESP32-C3 v1.1, board `A0:F2:62:01:70:28`. Inputs go over the UART bridge at 9600
  baud (`input_channel = "esp32-uart"`); the native USB cable carries JTAG only. Eight read
  watchpoints and debugger unwind metadata for ROM `strtol`. Firmware built with CDCOnBoot=default.
- Dataset: the same twenty original calc seeds as the one-cable set (the seed files are
  byte-identical). Tracing ran 18-19 October 2026 in three attempts (a startup retry stopped the
  first after 1.1 s). Each retained trace passed complete seed-byte coverage and nonempty-stack
  checks.
- Source run record: `docs/thesis/esp32c3-calc-2-cables-full-trial-0-2026-10-18/` on the local
  thesis branch, not pushed. The trace hashes match its `evidence-archive.json`.
- Transfer branch base: `05aa19f9ebc55889bcbc60235890a82b817219f1`, the remote `main` tip.

The traces total 33,330,459 bytes. They have the same instruction counts as the one-cable traces
but different code addresses, because the two firmware images differ. Do not mix the two sets.
`run/trace-check.json` preserves each trace's instruction count, covered byte count and SHA-256.
`run/SHA256SUMS` covers all twenty traces, twenty seed files and that checkpoint file, with paths
relative to this directory.

The original capture firmware ELF SHA-256 is:

```text
393ef8a04bbdccc78368aaa1123fe5c15a6f12c1a3046c6dd67351e394dc5839
```

The original debugger ROM ELF SHA-256 is:

```text
342a7d3b8040d842767baff9224879fea67dd7ed3abd2c95d030699c6586644e
```

Mining reads addresses from the traces, so the board must run a firmware image with the same code
layout. Build `build-2/` from the same source and toolchain, and compare the ELF hash above. If
it differs, report that.

## Fetch on the other computer

From the repository root, fetch and extract this directory into the current checkout:

```sh
git fetch origin data/esp32c3-calc-trial0-traces
git archive FETCH_HEAD \
  evaluation/esp32-c3_applications/esp32-c3_calc/trial-0-2-cables | tar -x
calc_trace_dataset=evaluation/esp32-c3_applications/esp32-c3_calc/trial-0-2-cables
(cd "$calc_trace_dataset" && sha256sum -c run/SHA256SUMS)
```

On macOS, use `shasum -a 256 -c run/SHA256SUMS` for the checksum command.

## Start at mining

Copy the traces into a new output base. This command requires that the base does not exist:

```sh
calc_reuse_output=output/esp32-c3_calc-2-cables-reused-trial0
test ! -e "$calc_reuse_output" &&
  mkdir -p "$calc_reuse_output/trial-0" &&
  cp "$calc_trace_dataset"/seed.*.in.trace "$calc_reuse_output/trial-0/"
```

Use a copy of `example_firmware/esp32-c3_calc/configuration/configuration.2-cables.toml` with
these settings:

- `BASIC.output_directory`: `./output/esp32-c3_calc-2-cables-reused-trial0`.
- `BASIC.seed_directory`: the included `run/seeds` directory. Write its expanded repository path
  into the TOML; shell variable names are not expanded by the configuration loader.
- `BASIC.binary_file`, `GDB.esp32c3.rom_elf`, serial port and debugger paths: the files and devices
  used by that computer's flashed calc firmware.
- `BASIC.eval_directory`: that campaign's calc evaluation corpus.
- `BASIC.empty_rule_removal`: `"every-subset"` to apply the PR #59 fix; the default `"released"`
  reproduces the earlier mining.

Run the mining stage, then the evaluation stage, with the copied configuration. Mining derives
its control-flow graphs from these trace records and sends membership queries to the board.
Precision evaluation also queries the board; recall uses the corpus offline.

## Reporting reuse with current main

Report the new run as mining with reused trial-0 traces, and record its own host revision,
firmware hash, configuration, query policy and RNG seeds. The original tracing durations belong
to the resumed capture campaign.
