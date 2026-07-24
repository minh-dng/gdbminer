# AGENTS.md

This file applies to the whole repository.

## Project Overview

GDBMiner is a Python 3.9 research prototype for debugger-driven grammar mining. The core workflow is:

1. Trace seed inputs through a target binary with GDB.
2. Mine a grammar from the generated trace files.
3. Evaluate the mined grammar against generated inputs.

The project is script-oriented rather than service-oriented. Most entrypoints live under `src/` and are run directly.

## Repository Layout

- `src/tracer/`: GDB tracing implementation and SUT connection/instance abstractions.
- `src/miner/`: grammar tree construction and generalization logic.
- `src/cmimid/`: vendored/adapted CMimid grammar-mining helpers.
- `src/eval/`: input generation and precision/recall evaluation scripts.
- `example_programs/`: native target programs, grammars, seeds, and configurations.
- `example_firmware/`: embedded/PlatformIO examples and board configs.
- `evaluation/` and `output/`: experiment outputs; treat as generated data unless a task explicitly targets them.
- `Dockerfile` and `run_experiment.sh`: reproducible benchmark environment and multi-target experiment runner.

## Environment

- Python requirement: `>=3.9,<3.10`.
- Local setup from the README:

  ```bash
  sudo apt install gdb graphviz graphviz-dev pkg-config libcairo2-dev python3-dev
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e .
  ```

- The Dockerfile uses `uv sync --frozen` with `uv.lock`; prefer preserving the lockfile unless dependency changes are intentional.
- Direct script execution often needs package imports from `src`; use an editable install or set `PYTHONPATH=$PWD/src`.
- Tracing depends on external tools and target binaries built with debug symbols and without optimization (`-g -O0`).

## Platform Notes

- `linux/arm64`: The Dockerfile maps Docker `arm64` to `aarch64` for the CMake installer, but native toolchain and third-party benchmark behavior may still be less exercised than `amd64`. Prefer the Docker environment for reproducible runs.
- `windows/amd64`: Native Windows is not a supported runtime for the main workflow. The tracer and experiment scripts assume Linux tools, Bash scripts, POSIX paths, GDB, and Valgrind. Use WSL2 or Docker from Windows.

## Common Commands

Generate evaluation inputs from a grammar:

```bash
python3 src/eval/generate_inputs.py \
  --config example_programs/json/configuration/configuration.ini \
  --grammar example_programs/json/json.grammar \
  example_programs/json/eval 1000
```

Trace then mine for a configured target:

```bash
python3 src/tracer/trace.py --config example_programs/json/configuration/configuration.ini
python3 src/miner/mine.py --config example_programs/json/configuration/configuration.ini
```

Evaluate precision/recall:

```bash
python3 src/eval/precision_recall.py --config example_programs/json/configuration/configuration.ini
```

Build and run the benchmark container:

```bash
docker build . -t gdbminer
docker run --rm -v "$(pwd)/output:/output/" gdbminer /run_experiment.sh
```

Full benchmark runs can take days. Do not start them as a casual validation step.

## Development Guidance

- Prefer small, local changes that match the current script/module style.
- Follow the surrounding Python: four-space indentation, `snake_case` functions and modules, `PascalCase` classes, and concise module-level scripts with `main()`.
- Keep existing license headers intact. New source files should use the project license context unless told otherwise.
- Avoid broad rewrites of `src/cmimid/` unless the task is specifically about the adapted CMimid behavior.
- Be careful with trace and grammar JSON shapes; downstream scripts expect keys such as `"[grammar]"` and `"[start]"`.
- Config files are central to behavior. Check the relevant `configuration.ini` before changing tracer, miner, or eval logic.
- Do not modify generated experiment outputs in `evaluation/`, `output/`, seeds, traces, or mined grammars unless explicitly requested.
- Avoid committing cache/build artifacts such as `__pycache__/`, egg-info changes, temporary trace output, or local virtualenv files.
- Use targeted searches. The repository contains large bundled third-party trees and generated outputs, especially under `example_programs/svgcpp/`, `evaluation/`, and `output/`.

## Validation

There is no conventional test suite configured in this repository. Choose the narrowest practical validation for the change:

- For pure Python utility changes, run the specific script or import path affected.
- For tracer changes, use a small example target and remember this may require GDB, Valgrind, and compiled debug binaries.
- For miner changes, run mining against an existing small trace directory when available.
- For Docker/experiment changes, prefer `docker build . -t gdbminer` before running experiments.

If a validation step cannot be run because required native tools, hardware, downloaded examples, or long-running experiments are unavailable, state that clearly in the final response.

## Commit and Pull Request Guidelines

Use the `conventional-commit` skill for both commits and pull request titles. Keep commits small and trackable. Pull requests should state the target and configuration, commands run, output changes, and linked issue; add logs or screenshots only when useful.

## Agent Skills

- Issues are tracked in GitHub Issues for `minh-dng/gdbminer`; see `docs/agents/issue-tracker.md`.
- Use the default five-label vocabulary in `docs/agents/triage-labels.md`.
- This is a single-context repository; see `docs/agents/domain.md`.
- For Docker and cross-architecture guidance, see `docs/DOCKER.md`.
