# Check of the fixed jsonrs configurations

On 2026-10-27, seeds 9 (`""`) and 15 (`false`) were traced again on both boards with the final
jsonrs configurations of PR #76: `frame_arguments = "none"`, `watchpoint_type = ""` and
`input_buffer = "data"`, without `GDB.language`, on `main` with PR #78. The new traces were compared
with the trial 0 traces of the same seeds, which used `language = "c"`, `watchpoint_type =
"(char*)"` and `input_buffer = "buf"`, and on the C3 printed frame arguments.

| Board | Seed | Entries | Hits | Result |
| --- | --- | --- | --- | --- |
| C3 | 9 | 1128 | 2 | Identical apart from `function_args` (differs in 428 entries) |
| C3 | 15 | 1725 | 6 | Identical apart from `function_args` (differs in 625 entries) |
| S3 | 9 | 1232 | 2 | Byte-identical |
| S3 | 15 | 1981 | 6 | Byte-identical |

The new C3 traces have an empty `function_args` in every entry, which is the intended effect of
`frame_arguments = "none"`. The S3 trial 0 already used `"none"`. The watch expression changes
neither the watched addresses nor the hits on either board.

## Seed 11 through `String::push`

Seeds 9 and 15 never call `String::push`, where trial 0's GDB crashed. Seed 11 does, and the
earlier seed 11 check (`repro/fixed-trace.log`) still set `language = "c"`. So window 0 of seed 11
(bytes 0 to 5) was traced again on the C3 with the final configuration at DEBUG level, on `main` at
`be815134` (PR #78 merged).

| Time (AEDT) | Event |
| --- | --- |
| 22:28:41 to 22:30:12 | Reads of bytes 0 to 5 |
| 22:30:09 | Stop at `0x4200963a`, the entry of `String::push`, trial 0's crash point. The stop record names the arguments, `[{'name': 'self'}, {'name': 'ch'}]`, without values |
| 22:41:48 | Window 0 ends: the parser returned and the six slots were released |

GDB did not crash, and the tracer logged no error. The run was then stopped (exit 143, `SIGTERM`)
as the next window started, because one window shows the result and the full seed takes about an
hour. `c3-seed-11/trace-excerpt.log` keeps every non-DEBUG record of the 240 MB log and the DEBUG
record of the `String::push` stop; `c3-seed-11/configuration.toml` is the configuration used.

## Setup

| | C3 | S3 |
| --- | --- | --- |
| Board | ESP32-C3-DevKitM-1, adapter `A0:F2:62:01:70:28` | ESP32-S3-Zero, adapter `E8:06:90:95:F2:70` |
| Input port, GDB port | `/dev/cu.usbserial-11130`, 3333 | `/dev/cu.usbmodem101`, 3335 |
| Firmware (ELF sha256) | `50b72ec1…` (`build-2`), as in trial 0 | `e4d63632…` (`build`), as in trial 0 |
| Time (AEDT) | 21:46:04 to 21:49:09 | 21:46:06 to 22:07:09 |

Nothing was flashed; both boards still held the trial 0 firmware. The configurations are the
committed ones, with only `seed_directory` and `output_directory` pointing at the scratch
directory `/tmp/pr76-evidence`. `c3/trace.log` has OpenOCD errors (`LIBUSB_ERROR_PIPE`,
`Unsupported DTM version: -1`) at each start, followed directly by `C3 OpenOCD initialized`; trial
0's log has the same lines, and both seeds traced.

## Files

| File | Content |
| --- | --- |
| `comparison.txt` | Output of `compare.py` for the four pairs |
| `compare.py` | Entry-by-entry comparison of two traces |
| `c3/`, `s3/` | Configuration, tracer output (`trace.log`) and the new traces |
| `c3/trial-0/` | The C3 trial 0 traces of seeds 9 and 15, copied from the trial 0 output |
| `c3-seed-11/` | Seed 11, window 0: configuration, log excerpt and start and end times |

The S3 trial 0 traces are not copied: they are byte-identical to `s3/seed.*.in.trace`, as the
sha256 values in `comparison.txt` show.

## Commands

From the repository root of a checkout of PR #76, with the two firmware builds in place. The
configurations read their seeds from the scratch directories of the recorded runs.

```sh
F=docs/failed-evaluations/esp32-c3_jsonrs-trial-0-2-cables/fix-check
J=example_programs/json/seeds
mkdir -p /tmp/pr76-evidence/seeds /tmp/pr76-seed11/seeds
cp $J/seed.9.in $J/seed.15.in /tmp/pr76-evidence/seeds/
cp $J/seed.11.in /tmp/pr76-seed11/seeds/

uv run src/tracer/trace.py --config $F/c3/configuration.toml \
    --adapter-serial A0:F2:62:01:70:28 --gdb-port 3333 --port /dev/cu.usbserial-11130
uv run src/tracer/trace.py --config $F/s3/configuration.toml \
    --adapter-serial E8:06:90:95:F2:70 --gdb-port 3335 --port /dev/cu.usbmodem101
uv run $F/compare.py $F/c3/trial-0/seed.9.in.trace $F/c3/seed.9.in.trace

# Seed 11, stopped after window 0 (the first `C3 released slot 7` in the log)
uv run src/tracer/trace.py --config $F/c3-seed-11/configuration.toml \
    --adapter-serial A0:F2:62:01:70:28 --gdb-port 3333 --port /dev/cu.usbserial-11130
```
