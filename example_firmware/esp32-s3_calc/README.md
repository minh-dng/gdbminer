# ESP32-S3 calc target

This target runs the paper's desktop [calc parser](../../example_programs/calc/) on the Waveshare
ESP32-S3-Zero. It uses the desktop target's 20 seeds and 1,000 evaluation inputs and the serial
protocol of the [S3 JSON target](../esp32-s3_json/README.md). The board, build options, debugger
and tracing method are in the [S3 setup guide](../ESP32-S3-Zero.md).

## Prepare the parser

`src/calc.c` is a symlink to the desktop `example_programs/calc/calc.c`. Run
`fetch_example_programs.sh` first: it downloads the pinned upstream `rdp.c` and applies the patch by
M. Eisele.

The desktop `main()` reads a file; the firmware never calls it, and the linker discards it.
`parser()` in `src/main.cpp` does the rest of the desktop `main()`: reject empty input (the desktop
exits with status 3), call the desktop `strip_input()`, establish `setjmp`, call
`rdp_parse_expression` and treat `longjmp` or a nonzero return as rejection.

## ROM `strtol`: existing S3 handling, no added unwind metadata

The firmware calls `strtol` in mask ROM through the ROM stub `__call_strtol` (`0x400014e8`, set by
the core's `esp32s3.rom.newlib.ld`), as it does for `strlen`. The stub loads the routine's address
and jumps to it; the backend follows it to the routine's `ENTRY` (see the [S3 setup
guide](../ESP32-S3-Zero.md#tracing-the-paper-replica-method)). The stub has no `ENTRY`: bare GDB
omits the direct caller `parse_primary` there. The backend executes the stub without recording it.
The actual routine is an ordinary windowed function: `entry`, two `call8` instructions
(`__getreent` and `_strtol_l$isra$0`) and `retw.n`, with no tail call.

Using the stock `esp32s3_rev0_rom.elf`, hardware checks retained the caller chain inside `strtol`,
including with caller register windows spilled to the stack, and after returning to the parser.
No additional unwind metadata was needed for these paths. The existing S3 backend's ROM-stub
handling and register-window exception retries remain necessary.

## Nesting limit

The parser is recursive. Each `(` adds four calls (`parse_primary`, `parse_expr`, `parse_sum` and
`parse_mult`), and at `-O0` each has a 64-byte frame (`entry a1, 64`), 256 bytes per level. The
wrapper sets the stack of Arduino's loop task, which runs the parser, to 32 KiB with
`SET_LOOP_TASK_STACK_SIZE`. Probed over the serial port on 2026-10-24 (board `E8:06:90:95:80:6C`,
no debugger), the board answers up to 124 levels of nesting.
At 125 levels the board panics with `Stack canary watchpoint triggered (loopTask)` (FreeRTOS's
end-of-stack guard, which uses DBREAK1) and restarts without an answer.

An independent hardware recheck on 2026-10-25 reproduced this boundary. A scratch build using the
default 8 KiB loop-task stack accepted 28 levels and hit the stack canary at 29. These are
standalone serial results, not limits measured while tracing: two armed data watchpoints borrow
DBREAK1 from the stack guard.

The seeds and evaluation inputs nest at most 3 levels.

## Build and upload

Follow the [S3 build and upload steps](../ESP32-S3-Zero.md#build-and-upload) with
`TARGET=esp32-s3_calc`. Create `calc.c` first. No `arduino-cli lib install` is needed. The expected
ELF is `build/esp32-s3_calc.ino.elf`; both TOMLs use it.

## Tracing

Both configurations start at `rdp_parse_expression` and watch the original global `buf`. Nothing is
skipped, including `strtol`, which consumes the input digits. There is no `ignore_functions_regex`,
so there is no `finish`, and no exit breakpoint. `configuration.1-watchpoint.toml` watches one byte
per run; `configuration.2-watchpoints.toml` watches two, at least 4 bytes apart
(`watchpoint_min_distance = 4`).

Both TOMLs leave `Connection.port` empty because the serial device path depends on the host.
Set it or pass `--port` to each stage (`trace.py`, `mine.py` and `precision_recall.py`); otherwise
the stage stops with `Set Connection.port in the configuration or pass --port`.
Pass `--adapter-serial` for the same board, as described in the S3 setup guide.

## Recorded checks

These are smoke checks on one board, not a full evaluation. Board: ESP32-S3-Zero
`E8:06:90:95:80:6C`, Arduino-ESP32 3.3.12, build `-O0 -g3 -ggdb3`, ELF SHA-256
`0755c78b9ef85655195bdac2136a7dcbfef90d583d1d88ec3666e3de0d5a3511`, 2026-10-24.

- **Trace of `1+2`, one and two watchpoints:** both options give 555 trace entries and 12 read
  records, identical in address, function, stack and reads. The stack at ROM `strtol` lists the
  return addresses of all callers up to `vPortTaskWrapper`; the tracer appends a dummy `0x0` to
  every stack. The minimum stored stack depth is five, including that marker, and
  every offset is read, including digits inside ROM `_strtol_l$isra$0`. This three-byte input
  arms only one watchpoint per pass under both configurations because of the minimum spacing.
- **Trace of `((8))*55+425`, two watchpoints:** 1,166 entries, minimum stack depth 5, maximum 24,
  32 entries with reads, and every stack ends with the same outer callers (`parser`, `loop`,
  `loopTask`, `vPortTaskWrapper`). Unlike `1+2`, this input is long enough for passes with both
  watchpoints armed; the saved summary does not verify simultaneous arming.
- **Serial answers:** accepted and rejected inputs, `5/0` (guarded in the parser) and
  `INT_MIN / -1` (accepted, no restart) answer without a restart. The firmware's `long` is 32-bit,
  so the desktop's 64-bit results can differ for large values.

Not done: a full 20-seed trace, mining and evaluation, and a comparison with the desktop `calc` over
the 1,000 evaluation inputs.
