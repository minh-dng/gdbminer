# ESP32-C3 mJS target

This target compiles the same Cmimid mJS benchmark source as the
[desktop target](../../example_programs/mjs/README.md), with its 20 seeds and 1,000 evaluation
inputs. A small libc bridge makes the benchmark's expanded Linux expressions work on the C3;
the downloaded parser and lexer source is unchanged.

## Fetch the desktop benchmark source

From the repository root:

```sh
./fetch_example_programs.sh --mjs-source-only
```

The shared fetch script copies `mjs.c`, `mjs.h` and `mjs_extra.h` into `example_programs/mjs/`.
Its Cmimid revision matches the Docker desktop baseline,
[`9c96909783ba99035372f78d6c52003f7f42b1ec`][desktop-source]. The source-only option skips desktop
compilation and the other examples, so it also works on the Arduino host. Downloaded sources
and binaries are git-ignored; upstream license notices remain intact.

`src/mjs_source.h`, `src/mjs.h` and `src/mjs_extra.h` link directly to those desktop files,
following calc's source-reuse pattern. The `.h` alias for `mjs.c` lets Arduino copy it into the
build without compiling a second translation unit. `src/parser.c` includes it with the desktop
`main` renamed; the linker discards that unused entry point.

Cmimid's `mjs_exec_internal` returns immediately after `mjs_parse`, preserving the benchmark's
parse-only modification. The wrapper calls `mjs_exec` and destroys the engine after each query,
avoiding the desktop process's per-query allocation leak in the long-running firmware. Inputs
are never executed: `while (true) {}` and `unknown();` are accepted.

The wrapper rejects a zero-length packet as the desktop file reader rejects an empty file.
A nonempty input starting with NUL is still accepted as an empty C string, and bytes after the
first NUL are ignored, matching the desktop benchmark. The original global `buf` is passed
through without stripping or copying it.

`src/cmimid_compat.h` restores the libc operations already expanded in Cmimid's source:
assertions still report and abort, NaN checks use `isnan`, and a classification table supplies
the four glibc masks the source uses. It preserves signed-char indices and EOF. The bridge uses
the C locale, as the desktop program does; firmware calls the parser from one Arduino loop task.
The table is initialized before `mjs_parse`, outside the recorded parser trace.

The serial protocol is ready byte `A`, a four-byte little-endian length, input bytes, and result
`0x00` (accepted) or `0xff` (rejected). The 2,048-byte payload limit excludes a separate NUL byte.
Oversized packets are drained and rejected, leaving the next packet aligned.

## Check the native oracle

After fetching the source:

```sh
uv run --frozen python example_firmware/esp32-c3_mjs/check_oracle.py
```

The checker verifies all three desktop source hashes and symlinks, builds the firmware wrapper
natively, and checks 20 seeds, 1,000 evaluation inputs and ten controls, including empty and
embedded-NUL inputs. Compiler, source and corpus metadata is written to
`build/native/corpus-check.json`. These finite checks do not establish grammar quality or
unbounded hardware reliability.

For a checkout previously prepared with Cesanta sources, move the generated `src/upstream/`
directory outside `src/` before compiling, for example into the ignored `build/` directory.
Arduino recursively compiles sources under `src/`; the old generated parser must not be linked
alongside the Cmimid source. The native checker rejects a leftover directory before compiling.

## Build and upload

Follow the shared [Arduino toolchain setup](../Arduino-CLI.md#toolchain). The build uses
Arduino-ESP32 core 3.3.12, debug symbols and `-O0` for the wrapper and parser. It does not rebuild
Espressif's precompiled SDK libraries.

For two cables, use UART for inputs and native USB for JTAG:

```sh
TARGET=esp32-c3_mjs
BUILD=2
CDC=default

arduino-cli compile \
  -b "esp32:esp32:esp32c3:CDCOnBoot=$CDC,FlashMode=dio" \
  --build-property 'compiler.optimization_flags=-O0 -g3 -ggdb3' \
  --build-property "runtime.tools.ctags.path=$HOME/.local/opt/arduino-ctags/5.8-arduino11/bin" \
  --build-path "$PWD/example_firmware/$TARGET/build-$BUILD" \
  "example_firmware/$TARGET"
```

For one cable, set `BUILD=1` and `CDC=cdc` before compiling. Both JTAG and inputs then use the
native USB-Serial/JTAG device. Omit the ctags override where the packaged executable works.
Follow the shared [upload instructions](../ESP32-C3%20DevKitM-1-N4X.md#build-and-upload) with
`TARGET=esp32-c3_mjs`, uploading the matching build directory. Build mJS with the command above;
no `MJS_EXPOSE_PRIVATE` definition is needed for the included benchmark source.

The two-cable configuration uses `build-2/esp32-c3_mjs.ino.elf`; the one-cable configuration uses
`build-1/esp32-c3_mjs.ino.elf`. The wrapper skips `Serial.flush()` on native HWCDC because it can
discard the queued ready byte (issue [#60](https://github.com/minh-dng/gdbminer/issues/60)). UART
builds keep the flush.

## Trace and mine

Follow the [C3 wiring and device identification guide](../ESP32-C3%20DevKitM-1-N4X.md#hardware).
Set local tool paths and serial ports in the selected TOML. The flashed image and configured ELF
must come from the same build. Run one stage at a time with exclusive access to the board.

- Two cables: `configuration/configuration.2-cables.toml`, output `output/esp32-c3_mjs/`.
- One cable: `configuration/configuration.1-cable.toml`, output `output/esp32-c3_mjs-1-cable/`.

For example, after replacing the chip MAC placeholder with the JTAG device's identifier:

```sh
CONFIG=example_firmware/esp32-c3_mjs/configuration/configuration.2-cables.toml
ADAPTER_SERIAL='<chip MAC>'

uv run --frozen python src/tracer/trace.py \
  --config "$CONFIG" --adapter-serial "$ADAPTER_SERIAL"
uv run --frozen python src/miner/mine.py \
  --config "$CONFIG" --adapter-serial "$ADAPTER_SERIAL"
```

Use `--port` and `--gdb-port` to override local serial/debugger ports. Mine only after all 20 seeds
have complete traces. The miner selects the newest trial, including incomplete trials left by
interrupted runs; see the shared [evaluation workflow][evaluation-guide] before continuing.

## Debugger settings

Both TOMLs start at `mjs_parse`, watch `buf`, and use six input-read triggers in slots 2-7. Slots
0-1 remain available for GDB's `finish`. The `memory_regions` list describes valid C3 memory
windows to GDB before attachment. It prevents stop-frame argument display from dereferencing
stale pointers into unmapped memory; it does not alter the firmware or allocate parser memory.

The skip list includes libc allocators/string helpers and ROM arithmetic helpers used for
bytecode-buffer sizing. It also skips the compatibility table getter, matching the desktop's
libc PLT skip: this getter reads the classification table, never the input. Parser and lexer
helpers remain visible. The identifier scanner reads
characters before the reserved-word comparison, but C3 `finish` does not record reads inside
skipped functions. Confirm full input-byte coverage and consistent watchpoint windows when
qualifying a build. The fixed seeds contain no digits; check numeric paths if the corpus changes.

## Evaluation

Select the completed trial explicitly. For one cable, use its corresponding configuration and
`output/esp32-c3_mjs-1-cable/` trial directory instead:

```sh
RUN=output/esp32-c3_mjs/trial-0
PRECISION_SET_SIZE=1000 uv run --frozen python src/eval/precision_recall.py \
  --config "$CONFIG" --adapter-serial "$ADAPTER_SERIAL" --grammar "$RUN/parsing_g.json" \
  --out "$RUN/evaluation.json"
PYTHONHASHSEED=0 PRECISION_SET_SIZE=1000 uv run --frozen python -c \
  'import random, runpy
random.seed(0)
runpy.run_path("src/eval/compare_fuzzers.py", run_name="__main__")' \
  --config "$CONFIG" --adapter-serial "$ADAPTER_SERIAL" --grammar "$RUN/parsing_g.json" \
  > "$RUN/mutation-comparison.log" 2>&1
```

Record trace/mining times, source and fuzzer revisions, and the random seed with each run. The
comparison command pins random and hash seeds to zero and uses the repository's mutation fuzzer;
it does not establish identical queries to the paper's fuzzingbook run. Full active mining,
precision/recall and mutation comparison for this target remain incomplete.

## Qualification limits

The wrapper keeps the default task stack. Earlier Cesanta-based images panicked on deeply
nested inputs; those measurements do not qualify this Cmimid build. Fresh nesting and heap/stack
qualification are required before evaluation. Treat resets as infrastructure failures, not parser
rejections; corpus agreement does not qualify arbitrary generated inputs.

Cmimid's `mjs_create` dereferences its initial allocation before returning, so a null-result check
in the wrapper cannot recover from that failure. Qualify minimum free heap, parser-stack use and
resets for the flashed image and corpus, including repeated large and deeply nested inputs.
Measurements from a diagnostic image do not qualify every build.

The serial adapter permits one resend after a lost response, then stops if both sends are lost.
Stop on missing responses or boot/panic output and withhold scores from runs with infrastructure
failures. Native corpus checks and firmware builds do not replace on-board qualification or
precision/recall measurements.

[desktop-source]:
https://github.com/vrthra/mimid/blob/9c96909783ba99035372f78d6c52003f7f42b1ec/Cmimid/examples/mjs.c
[evaluation-guide]: ../ESP32-C3%20DevKitM-1-N4X.md#running-the-evaluation
