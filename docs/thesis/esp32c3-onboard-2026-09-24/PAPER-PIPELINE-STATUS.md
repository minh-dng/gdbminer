# Paper-style GDBMiner pipeline on ESP32 — status 2026-09-24

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record describes the firmware input-access bitmap and custom parsers, which were rejected as off-method; the tracer no longer supports the bitmap. Do not run
> the commands below against the current checkout.

## Paper protocol (Eisele et al. 2025)

Per §5 evaluation and Table 8 (embedded):

1. 20 seeds from the golden grammar (GrammarCoverageFuzzer, duplicates skipped).
2. `trace.py` — GDB single-step + input-access events (hardware watchpoints on the paper's STM32; input-access bitmap on our C3/RISC-V adapters).
3. `mine.py` — mine input grammar from traces.
4. Precision: generate 1,000 inputs from the **mined** grammar; fraction the SUT accepts.
5. Recall: generate 1,000 inputs from the **golden** grammar; fraction the mined grammar parses.
6. Record tracing time, mining time, and mutation-fuzzer acceptance.

Commands (firmware configs):

```bash
uv run python src/tracer/trace.py --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini
uv run python src/miner/mine.py   --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini
PRECISION_SET_SIZE=1000 uv run python src/eval/precision_recall.py \
  --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini \
  --out output/esp32-c3_cgidecode.20.gdbminer.result
```

Same for `esp32-c3_json` and `esp32-c3_xml`.

## What is actually runnable today

| Stage | cgi_decode | json | xml |
| --- | --- | --- | --- |
| Firmware + serial SUT | yes | yes | yes |
| Serial accept/reject oracle (not paper Table 8) | 1020/1020 | 1020/1020 | 1014/1020 vs expat |
| `trace.py` (needs GDB + JTAG) | **blocked** | **blocked** | **blocked** |
| `mine.py` (needs traces) | blocked | blocked | blocked |
| `precision_recall.py` (needs SUT + mined grammar) | blocked | blocked | blocked |

`trace.py` / `open_sut_instance` starts Espressif OpenOCD `board/esp32c3-builtin.cfg`. That fails until native USB Serial/JTAG is wired (GPIO18/19). See [[ESP32-C3 debug path and native USB-JTAG wiring]].

## Serial-oracle results (SUT feedback only)

These are **not** Table 8 precision/recall. They only check that the board's accept/reject matches a host oracle on the checked-in seeds and 1,000 eval inputs.

| Target | Result | Notes |
| --- | --- | --- |
| `esp32-c3_cgidecode` | 20/20 + 1000/1000 | classic `cgi_decode` |
| `esp32-c3_json` | 20/20 + 1000/1000 | after rejecting JSON leading zeros |
| `esp32-c3_xml` | 20/20 + 994/1000 | 6 eval mismatches are **duplicate attribute names** in one element (yxml accepts redefinition; Python expat rejects). Paper §5.3 notes the same class of backend disagreement for SVG++. |

## Timing clarification (vs paper)

Serial smoke is milliseconds per input because the SUT runs at full speed over UART. The paper's Table 8 times are dominated by **instruction-level GDB tracing** (single-step, stack traces, watchpoint/bitmap polls), not by the feedback oracle. The earlier "much quicker than the paper" impression is not a watchpoint win — watchpoints are not in use yet.

## Unblock path

1. Wire Mac USB D-/D+ to GPIO18/19 (or attach ESP-Prog / CMSIS-DAP).
2. Confirm `openocd -f board/esp32c3-builtin.cfg` sees `esp_usb_jtag`.
3. Re-run the three commands above per target.
4. Report Table 8-style precision, recall, F1, trace/mine time — and compare to the paper's B-L475E numbers with the C3 strategy difference labeled (bitmap vs DWT watchpoints).

## Desktop paper pipeline results (2026-09-24, Docker gdbminer:arm64)

| Target | Precision | Recall | F1 | Trace s | Mine s |
| --- | --- | --- | --- | --- | --- |
| cgi_decode | 1.000 | 1.000 | 1.000 | 120 | 71 |
| json | 1.000 | 0.668 | 0.801 | 135 | 15 |
| yxml | 0.989 | 0.767 | 0.864 | 627 | 903 |

Full write-up: `Uni/Thesis/Replication/Paper GDBMiner replication cgi_decode json yxml 2026-09-24.md`

## Desktop paper targets note

`example_programs/{cgi_decode,json,yxml}` + Valgrind is the paper's host path. Those checked-in ELFs are x86-64 Linux. Docker was not running on this Mac (2026-09-24), and Valgrind is not available on macOS. Use the UTM Linux VM or start Docker to run that side of the replication.
