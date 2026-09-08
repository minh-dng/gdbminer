# Repository Guidelines

## Project Structure & Module Organization

Core Python code lives in `src/`:

- `src/tracer/` drives GDB-compatible targets and records input traces.
- `src/miner/` converts traces into grammars; `mine.py` is the mining entry point.
- `src/eval/` generates inputs and calculates precision/recall.
- `src/cmimid/` contains the bundled Cmimid baseline and grammar utilities.

Use `example_programs/<target>/` for desktop targets, including `configuration/`, `seeds/`, and `eval/`. Use `example_firmware/` for STM32 examples. Keep generated traces and mined JSON in configured output directories.

## Build, Test, and Development Commands

Develop with Python 3.12 (the supported range is `>=3.12,<3.13`). `mise` is the
recommended way to pin that runtime and the rest of the dev toolchain; see
`mise.toml` for the configured tool set and `mise.lock` for exact resolved
versions. System deps still come from your OS (e.g. `gdb`, `valgrind`,
`graphviz`/`graphviz-dev`, `pkg-config`, `llvm-14`).

Preferred (mise):

```bash
curl https://mise.run | sh          # once
mise trust                          # trust mise.toml (once per checkout)
mise install                        # install the toolchain pinned by mise.lock
mise run install:dev                # uv sync --frozen --group dev  → .venv
mise run lint                       # ruff check  (mise-managed, no venv needed)
mise run fmt:check                  # ruff format --check
mise run typecheck                  # basedpyright (pipx-managed)
mise run check                      # lint + fmt:check + typecheck
mise run trace                      # example_programs/json default config
mise run mine
mise run eval
# or with an explicit config:
mise run trace -- example_programs/json/configuration/configuration.ini
mise run shellcheck; mise run shfmt:check
mise tasks ls                       # all available tasks
```

Without mise (vanilla venv + pip):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # or: uv sync --group dev
./src/tracer/trace.py --config example_programs/json/configuration/configuration.ini
./src/miner/mine.py --config example_programs/json/configuration/configuration.ini
./src/eval/precision_recall.py --config example_programs/json/configuration/configuration.ini
```

Tracing creates `*.trace`; mining writes `parsing_g.json`. For Docker and different arch testing, see `docs/DOCKER.md`.

## Coding Style

Preserve existing type hints and logging patterns. In `src/` (tracer/miner/eval/cmimid), keep target-specific values in INI files rather than hard-coding paths or debugger settings. That INI-over-hardcode rule applies to GDBMiner program code, not to Dockerfile/infra setup, where `ARG`/`ENV` pins are the mechanism.

## Testing Guidelines

There is no configured automated test suite. Validate with the smallest affected workflow: trace and mine an existing example, then run `precision_recall.py` when grammar output changes. Keep generated results out of source changes unless intentional.

If the test can be verified with a linting / type-hint check then do not test it.

## Commit & Pull Request Guidelines

Use `conventional-commit` for both commits and PR titles. Do small trackable commits. PRs should state the target/configuration, commands run, output changes, and linked issue (if exists); add logs or screenshots only when useful.

Pull requests are documentation tools, as part of my honours thesis submission and write up (where I will gather the information from the PRs). I would like to see decision made regarding the code changes, use diagrams if it helps, engineering decisions carried out, trade-offs and related documentation / inspiration.

## Configuration & Hardware

Treat configuration files as the execution contract: set binary paths, seed/output directories, GDB instance, watchpoint details, and entry/exit points there. Desktop targets need debug symbols and no compiler optimization; STM32 work requires the documented ST-Link/GDB-server setup.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `minh-dng/gdbminer`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.
