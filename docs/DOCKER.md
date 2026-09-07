# Docker

## Local experiments

Build the reproducibility image from the repository root, then mount a local output directory:

```bash
docker build -t gdbminer .
docker run --rm -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

Full experiments can run for days. Use a dedicated output directory per trial so results are not overwritten.

For a quick single-target check, reduce the generated inputs and target list:

```bash
docker run --rm -e NUMBER_OF_SEEDS=1 -e PRECISION_SET_SIZE=3 \
  -e TARGETS=json -e MIMID_TARGETS=json \
  -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

## Python 3.12 dependency choices

The Ubuntu 24.04 image uses uv-managed Python 3.12.11. The project supports
Python `>=3.12,<3.13`; mise selects the latest locked 3.12 patch release for
local development.

The evaluation code uses the local implementation added in #3, so Fuzzing
Book, ISLa, and Z3 are no longer dependencies. This avoids the unavailable
Linux ARM64 Z3 wheel rather than maintaining a platform-specific build
workaround. The lock contains 12 packages for the `experiment` installation.

Meson moves from 0.46.1 to the 1.x series because the old CLI uses
`collections.MutableSet`, removed in Python 3.10. The LLVM 14 patch explicitly
selects Meson's `config-tool` dependency method: mimid reads LLVM flags through
`get_configtool_variable()`, which cannot operate on the CMake dependency that
modern Meson otherwise discovers first.

Recheck the lock with Docker's uv and Python versions:

```bash
uvx --from uv==0.11.1 uv lock --check --python 3.12.11
```

The full image build remains the installation check because it also compiles
mimid's taint instrumentation and the benchmark targets.

## Different architectures

The Dockerfile supports `linux/amd64` and `linux/arm64`. Build on a native host where possible:

```bash
docker build --platform linux/arm64 -t gdbminer:arm64 .
```

For a remote Docker daemon, create a context and run the build and experiment there:

```bash
docker context create remote --docker "host=ssh://user@host"
docker --context remote build --platform linux/arm64 -t gdbminer:arm64 .
docker --context remote run --rm -v "$(pwd)/output:/output" gdbminer:arm64 /run_experiment.sh
```

Run these commands from a checkout available to the remote daemon, or publish the image to a registry it can access. The `-v` path is on the remote host, not the local machine. For physical firmware, ensure the container can reach the remote GDB server or the attached USB debugger.
