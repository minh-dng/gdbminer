# ESP32-C3: replace mismatched runtime stubs with an official matched build

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record steps through runtime functions with ROM unwind rules, which were removed when those functions became skipped with `finish`. Do not run
> the commands below against the current checkout.

## Goal and scope

Make GDBMiner tracing and mining work without replacing missing runtime functions with no-op implementations.
Keep the JSON library and wrapper unchanged while changing the framework/toolchain. Grammar precision/recall is a
pipeline check, not evidence of coverage, crash discovery or effectiveness in a real fuzzing campaign.

The earlier [Arduino_JSON port](../esp32c3-arduino-json-2026-09-28/README.md) passed one-seed tracing/mining/evaluation,
but its full-corpus run stopped on `input.14`, at `0x4201e010`, with a truncated caller chain. That run is not a
full-corpus success. It combined an old Arduino framework with a manually overridden GCC 16 toolchain.

## 1. Preserve the old experiment

The previous entire `example_firmware/esp32-c3_json` project, including ELF/bin and configuration, is archived at:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-official-arduino-2026-09-29/before/esp32-c3_json.tgz
```

No new trace uses its output directory. The replacement ELF and its configurations have separate paths.

## 2. Select a supported package pairing

Use Arduino CLI 1.5.1 and Espressif's official Boards Manager package `esp32:esp32@3.3.12`.
Its package index specifies `esp-rv32@2601`, which supplies GCC 14.2.0_20260121, and matching ESP32-C3 SDK libraries.
The Arduino_JSON version remains 0.2.0. This isolates the build change from parser-version changes.

Removed from the target:

- `src/toolchain_stubs.c`: no-op cleanup/exception-sorting and always-failing entropy replacements.
- The old `platformio.ini`, including its compiler override.

Added a comment-only Arduino sketch entry file. The existing `src/main.cpp` supplies `setup()` and `loop()` and remains
byte-identical to the archived source. Parser sources compile with `-O0 -g3 -ggdb3`; prebuilt SDK libraries keep their
vendor build settings. Build/upload commands are in the [C3 setup README](../../../example_firmware/ESP32-C3%20DevKitM-1-N4X.README.md#build-and-upload).

## 3. Resolve host-only installation issues

The old framework's matched Intel compiler could not run without Rosetta, and the configured Linux VM was unreachable.
The new official package supplies a native Apple Silicon compiler. Package installation initially stopped during a
large download; retrying used the cached packages and completed.

Arduino CLI's separate ctags 5.8-arduino11 package is Intel-only. Build that exact upstream source natively, using
`CFLAGS='-O2 -include dirent.h'` to avoid its old `__unused__` macro colliding with the macOS SDK. Select it with
`runtime.tools.ctags.path`; no package or source is patched. This executable generates sketch prototypes on the host
and is not linked into the firmware. The new target's `.ino` contains no functions requiring generated prototypes.

Homebrew GDB 17.2 crashes resolving `break cJSON_Parse` in the new ELF, reproducible in a board-free batch command.
Espressif's bundled GDB 17.1_20260402 passes that command, so both target configurations now select it.

## 4. Build, flash and check the serial oracle

The official matched build links without the deleted compatibility stubs and flashes with verified image hashes.
Its log (`build-native-corrected.log`) was moved to `output/esp32-c3_json/trial-0/build.log` in this worktree.
The ELF SHA-256 is:

```text
f6cf61b78578edf6b69a4dd9b6aae29597064bbae64e6620f38a29cd6947bd8e
```

All ten existing serial oracle checks pass: objects, arrays, invalid escape/token rejection, empty-input rejection,
reference-compatible trailing-byte/NUL handling, the 2,048-byte limit, oversized rejection and subsequent packet
alignment. This establishes functional acceptance, not complete tracing.

## 5. Separate ROM unwind metadata from runtime substitutions

With the previous custom ROM unwinder disabled, a `{}` trace still stops inside ROM `memset`, now at `0x40058d46`,
with `Unexpected parser return stack: ['0x0']`. The compiler/framework migration cannot change the chip's ROM code.

The existing byte-validated debugger-only rule was tested against the new ELF through a separate experiment
configuration, `configuration.rom-metadata.ini`. It describes the real outer return address saved in `t0` during
`memset`'s internal call. It does not replace a runtime function, modify registers or skip input observations.
The validation passed, so both new target INIs now enable this debugger metadata.

## 6. Completed smoke pipeline and next gate

Eight-slot and one-slot traces of `{}` match exactly: 1,165 instructions, 14 observed input reads, with per-byte counts
`[10, 4]`. Instruction addresses, function names, stacks and read offsets match across the runs. The eight-slot run took
135.71 s; the two one-slot windows took 260.82 s. For a two-byte seed, only two of the eight available slots are armed.

The normal miner consumed the eight-slot trace and produced `parsing_g.json` in 21.79 s. The normal evaluator then
completed 1,000 generated inputs on the C3 and all 1,000 recall samples. Smoke precision was 1.0, recall 0.001 and F1
0.001998, with six generalization queries. This is a `{}`-only training grammar: these values demonstrate pipeline
execution, not useful JSON coverage or fuzzing effectiveness.

The separate numeric regression on `input.14` first stopped at `0x40057174`, the `ret` instruction of ROM
`__floatunsidf`. Its immediately preceding instruction is `c.addi sp,16`: the real stack pointer has already been
restored, but GDB's fallback unwinder still reads as if that frame were allocated. A direct breakpoint reproduces the
missing parser callers independently of watchpoints.

A second debugger rule now handles the executing frame only when the live bytes are a positive, nonzero
`c.addi sp,immediate` or `c.addi16sp immediate` followed by `c.jr ra` (`ret`). At that epilogue point, it describes the
caller using the actual RA, SP and restored callee-saved registers. It declines other instruction patterns and does
not modify the target. The first version supported only the short `c.addi` encoding; the full numeric trace then
reached `__muldf3`'s `c.addi16sp sp,48; ret` at `0x400568ac`, exposing the second compressed encoding.
`check_rom_stack.py --check-return` verifies that stepping the real return reaches live RA and produces exactly the
caller chain that was unwound, while stack requests leave the checked registers unchanged. That hardware regression
fails before the rule and passes afterward. Both `__floatunsidf` and `__muldf3` return probes pass, including exact
caller-chain equality after the real return. This is host debugger metadata, not another firmware compatibility stub.

The complete numeric trace is being rerun with this rule. It uses the same ELF and two eight-slot windows and gates
the full 20-seed trace → mine → evaluate run. The copied seed and isolated configuration are under `regression-number/`;
`trace-both-return-forms.exit` records the current regression outcome. Earlier failed attempts retain their logs and
exit files. Blocked full-run statuses are preserved with `.blocked-before-return-rule` and `.blocked-before-addi16sp`
suffixes. `full-pipeline.state` and `full-pipeline.exit` describe the current regression/full-corpus pipeline.
The earlier smoke comparison above predates this additional return rule; its measurements remain historical.

The first rerun with both return forms (started 23:10) was aborted by the host, not by the tracer. About one second
after the second eight-slot window was armed, the USB-JTAG device disconnected: the serial worker failed with
`Device not configured` and OpenOCD reported `esp_usb_jtag: device not found`. The tracer then waited for GDB
indefinitely instead of failing; it was stopped manually at 23:59. `trace-both-return-forms.exit` records this.
The run provides no evidence for or against the return rule. The wait-forever behavior after device loss is a
separate robustness gap and is not changed here.

## Evidence

All commands' logs, the official package index, source/ELF/corpus hashes, failed attempts and new trace results are under:

```text
/Users/dan173/Documents/Uni/thesis/experiments/esp32c3-official-arduino-2026-09-29/
```

The build, oracle and smoke pipeline have passed. No full-corpus result is claimed at this stage.

Sources (software documentation, not new research papers):

- [Arduino-ESP32 3.3.12](https://github.com/espressif/arduino-esp32/releases/tag/3.3.12)
- [Official package index](https://espressif.github.io/arduino-esp32/package_esp32_index.json)
- [Arduino ctags 5.8-arduino11](https://github.com/arduino/ctags/releases/tag/5.8-arduino11)
