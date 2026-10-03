# Independent ESP32-C3 rebase review

Reviewed HEAD `7d05b79232c1c732183d9a8aabc945dce70b727e` against main
`eee8adc8fd64baa0cfefb432c02c8c0358c30933` in
`/Users/dan173/Documents/Uni/thesis/impl/gdbminer.feat-esp32-c3-devkitm-1-n4x-review`.
All file/line citations below refer to that pinned HEAD. No source or Git state was changed.
No hardware was accessed. The worktree was clean after review.

The refs resolved and the three-dot diff was non-empty. Reviewed the main-to-feature diff and
seven commits, the pre-rebase range against checkpoint `d81b64f4`, and the checkpoint-to-HEAD
follow-up. Independent GPT-6 Astra agents at high reasoning effort reviewed Standards and Spec
with no inherited conversation. The coordinator rechecked their findings against call flows.
The mjs target and prior review reports were excluded.

## Standards

1. **P3, possible Refused Bequest, inherited design heuristic.**
   `src/tracer/instance/esp32c3_instance.py:28` declares
   `class ESP32C3Instance(STM32Instance)`, but replaces STM32 stepping, response processing,
   reset and teardown. At line 420 it explicitly bypasses its parent with
   `SUTInstance.get_gdb_responses(self)`. The coupling complicates the TOML migration:
   `src/tracer/instance/stm32_instance.py:21` permits a missing STM32 table, and line 26
   branches the ARM workaround default on the selected backend to accommodate C3 construction.
   A maintainer changing STM32 initialization must account for C3 even though C3 prohibits ARM
   settings. Extract shared remote startup, connection and input operations into a composed
   helper, then derive C3 directly from `SUTInstance`. This is a judgement call, not a documented
   breach or demonstrated runtime failure. The inheritance predates the rebase.

2. **P3, documented Markdown breach, inherited.**
   `example_firmware/ESP32-C3 DevKitM-1-N4X.README.md:295` and line 296 exceed 100 characters.
   The target READMEs also contain long prose, for example `esp32-c3_json/README.md:3`,
   `esp32-c3_cgidecode/README.md:3` and `esp32-c3_xml/README.md:3`, under `example_firmware/`.
   `AGENTS.md:76` requires "Manual line break at 100 characters." These paragraphs exceed the
   required source-reading width. Wrap prose at word boundaries without changing rendered
   content. No Markdown formatter or linter was found enforcing this rule. These examples
   existed before the rebase.

## Spec

1. **P1, inherited: CGI reserves every slot before its entry breakpoint.**
   Requirement: "CGI eight starting at 0."
   `src/tracer/instance/esp32c3_instance.py:460` reserves the complete configured read window
   during `__enter__`, including all eight slots in the supplied CGI config. Only afterward,
   `src/tracer/gdb_tracer.py:150` requests the entry breakpoint, and line 153 resumes toward it.
   `src/tracer/instance/esp32c3_instance.py:316` forces that breakpoint to be hardware.
   In the archived matching OpenOCD version,
   `docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/riscv.c:1658` routes hardware breakpoints
   through `add_trigger`; `set_trigger` at line 845 refuses reserved slots. The supplied CGI
   configuration therefore cannot insert its entry breakpoint under this documented allocator.
   Defer reservation until the temporary entry breakpoint has fired and been deleted, before
   arming the first raw read trigger. This keeps all eight slots available for CGI reads and
   preserves JSON/XML budgets. The sequence is unchanged from pre-rebase HEAD. The finding is
   established by source and call order, not a new live run; historical measurements do not
   establish that this exact startup sequence works.

2. **P2, TOML follow-up regression: resume rewriting depends on whitespace.**
   Requirement: "Update active tooling and documentation for TOML."
   `docs/thesis/esp32c3-trials-2026-10-01/run-trials.sh:163` replaces only unindented assignments
   with exactly `" = "`. Valid TOML such as `seed_directory="..."` and
   `output_directory="..."` retains both original values. Offline reproduction confirmed that
   the unchanged result still passes `validate_config`. After an interruption, the resume traces
   the full corpus into the next main trial instead of its resume directory. The copy at line
   171 finds no resumed traces, and the current trial cannot complete. Parse TOML, update its
   `[BASIC]` values and serialize the result; verify the resulting paths before starting tracing.

3. **P2, incomplete new validation: explicit exit breakpoint omitted from the shared budget.**
   Requirements: "C3 has eight slots shared with managed breakpoints" and "Validate unsafe
   settings before creating trials or starting target resources."
   `src/util/config.py:109` checks only the raw window bounds and accepts eight read triggers
   together with a nonempty `exitpoint`, confirmed offline. `src/tracer/trace.py:52` creates a
   trial before target startup. `src/tracer/gdb_tracer.py:171` arms the reads and line 186 requests
   an additional hardware exit breakpoint. Even after fixing finding 1, eight active read
   triggers leave no slot for that breakpoint. Reject eight-watchpoint configurations with an
   explicit exitpoint during validation. Do not infer that XML's preserved inactive ignore regex
   requires another two slots. This is an omission in the new validation, not evidence that the
   supplied 6/8/7 budgets were changed by the rebase.

## Verification and limits

- The configuration regression script passed, including source TOML parsing and mocked rejection
  before trial-directory creation. The 34 ESP32 tests, one graph test and one retry test passed.
  These checks used Python 3.12 with bytecode writes disabled and mocked target resources.
- Two additional offline reproductions confirmed the valid-TOML whitespace resume defect and
  acceptance of eight read triggers with an explicit exitpoint.
- The three supplied C3 configurations retain 6/8/7 triggers starting at 2/0/1. XML retains
  always-inserted breakpoint behavior. ROM symbols use additive `add-symbol-file`. The serial
  adapter transmits original input bytes, waits for readiness and handles the captured boot-noise
  sequence. Its documented unframed-protocol limitations remain.
- The reservation fix should occur once, at first raw-trigger allocation after parser entry.
  Existing owner checks and partial-initialization cleanup must remain. Reservation must precede
  any raw trigger writes and later exit/finish insertion. Teardown already clears owned trigger
  registers and terminates the private OpenOCD process, which ends its reservation state.
- No live trace, flash, serial, OpenOCD or GDB session was performed. Passing mocked checks does
  not establish hardware correctness or reproduce the historical measurements.

Standards: 2 P3 findings, one documented breach and one design heuristic. Spec: 3 findings;
the worst within Spec is P1, the inherited CGI entry-breakpoint reservation failure.

## Re-review appendix, working fixes against 7d05b792

Reviewed the working diff in the `-review` worktree against pinned HEAD
`7d05b79232c1c732183d9a8aabc945dce70b727e`. The similarly named original worktree contains mJS
commits and was excluded. Appendix citations refer to the reviewed working files. Both original
review agents checked their respective axes again. Review remained read-only except this report.

### Standards re-review

- The original prose-width finding is resolved in the four edited C3 READMEs. Their prose now
  fits the requested 100-character width; tables and fenced evidence output were excluded.
- The inherited P3 Refused Bequest heuristic remains open and is deliberately deferred to a
  separate refactor. It does not block the runtime fixes.
- One new P3 documentation issue was found during reflow. In
  `example_firmware/ESP32-C3 DevKitM-1-N4X.README.md:225`, the top-level `[openocd-release]`
  definition interrupts the OpenOCD list item. The recorded-run description becomes a separate
  paragraph rather than part of that item. Move the reference definition to the document bottom
  and indent list continuation text by two spaces. Preserve footnote indentation during the same
  reflow. The reviewer verified the list split with a GFM renderer; the footnote itself still
  renders as one footnote, so its indentation is a source-readability issue only.
- No new actionable standards defect was found in the runtime or script changes.

### Spec re-review

All three original Spec findings are resolved in the reviewed working diff.

1. `src/tracer/instance/esp32c3_instance.py:192` now reserves the raw window during the first
   read-trigger allocation. The temporary entry breakpoint can use a slot before reservation.
   Allocation checks that the target is halted and the first slot has no active owner before
   reserving, then reserves before raw register writes. Later exit/finish breakpoints remain
   outside the window. Existing partial-initialization cleanup remains, and shutdown terminates
   the private OpenOCD process and its reservations. The 6/8/7 budgets remain intact.
2. `src/util/config.py:114` rejects eight read triggers with a nonempty exitpoint. The regression
   check exercises the CLI and verifies that neither trial creation nor target tracing starts.
3. `docs/thesis/esp32c3-trials-2026-10-01/run-trials.sh:162` loads native TOML and changes the
   `[BASIC]` paths. Lines 166-179 emit nested tables and require a successful round-trip before
   output. Lines 182-184 stop the resume if generation fails. This resolves whitespace-dependent
   rewriting and preserves supported configuration values. No new actionable Spec issue found.

### Re-review checks

The coordinator reran configuration regression checks, all 34 ESP32 unit tests, shell syntax and
`git diff --check`; all passed. An additional execution of the actual resume heredoc preserved
compact/quoted path assignments, Unicode, quotes, backslashes and nested tables. The independent
Spec agent also checked resume generation across JSON, XML and CGI. No hardware was accessed.
These checks establish the configuration and mocked command-order fixes, not a new live trace.

Re-review counts: Standards has one deferred inherited P3 heuristic and one new P3 Markdown issue;
Spec has zero outstanding findings. The original Markdown width finding is resolved.

## Final documentation correction and integration

The main agent corrected the Markdown issue after the re-review. The OpenOCD reference definition
now appears at the document bottom, list continuations retain two-space indentation, and the
Arduino CLI footnote retains four-space indentation. Fenced evidence and table contents remain
unchanged. The four C3 target/setup READMEs wrap prose at 100 columns.

The runtime fixes are committed on the base branch:

- `150a27ce` defers reservation until parser entry and validates the explicit exit-breakpoint budget.
- `5ddc4bf0` generates resume TOML from parsed values and checks the round-trip before tracing.

Ruff lint/format, BasedPyright with the existing Python 3.12 environment, ShellCheck, shell syntax,
configuration checks, all 34 ESP32 tests, connection lifecycle/retry checks and diff whitespace
checks pass. The actual resume helper preserves all native configuration values across the three
source targets with both original and compact/quoted assignments. Invalid configuration generation
fails before tracing. The main agent also checked the extracted Python helper with Ruff.

Final disposition: no outstanding Spec findings; the Markdown findings are resolved. The inherited
P3 inheritance heuristic is deliberately deferred because it is not a demonstrated runtime failure
and would broaden the rebase fixes into a module refactor. No hardware was accessed for this task.
