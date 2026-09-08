# Docker

## Local experiments

Build the reproducibility image from the repository root, then mount a local output directory:

```bash
docker build -t gdbminer .
docker run --rm -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

Full experiments can run for days. Use a dedicated output directory per trial so results are not overwritten.

## Toolchain management (mise)

The image uses a separate `docker/mise.toml` and `docker/mise.lock` because it
needs Java, CMake, and Ninja in addition to the local development tools. The
Dockerfile installs this config globally under `/root/.config/mise`. The uv
binary itself is pinned there (aqua backend), replacing the previous
`COPY --from ghcr.io/astral-sh/uv` image. Python is installed with that
uv binary, pinned by Dockerfile `ARG PYTHON_VERSION`; jq uses the same exact
version as the root `mise.lock`; the mise binary is also pinned through
`ARG MISE_VERSION`.

| Tool | Docker pin | Replaces |
| ---- | ---------- | -------- |
| mise | 2026.9.1 | unpinned `curl \| sh` |
| uv | 0.12.10 | `COPY --from ghcr.io/astral-sh/uv:0.11.1` image |
| Python | 3.12.14 (`ARG PYTHON_VERSION`, uv-managed) | uv-managed Python 3.12.11 |
| Java | Temurin 11.0.32+101 | `apt` OpenJDK 11 |
| CMake | 3.29.0 | architecture-specific 3.29.0-rc2 installer |
| Ninja | 1.13.2 | `apt` package |
| jq | 1.8.2 | `apt` package |

mise selects the correct binaries for `linux/amd64` or `linux/arm64`. The
build checks uv, Python discovery, the JDK and `$JAVA_HOME` (exposed via an
`/opt/java` symlink), CMake, Ninja, jq, GDB, and Valgrind.
Native build dependencies remain installed through apt or built from source.

The root config keeps its broad `python = "3.12"` and `jq = "latest"`
selectors, while the root lock records exact versions. Docker repeats those
exact versions (mise tools in `docker/mise.toml`+lock, Python in
`ARG PYTHON_VERSION`) because image builds must not advance when the root
selectors are updated; the Docker pins are manually kept in sync with the
root lock. `UV_PYTHON=3.12` selects the uv-installed interpreter series,
while `ARG PYTHON_VERSION` remains the single exact Python pin for the image.

The image runs as root because mise shims and installs live under `/root`.
Changing `USER` or `HOME` would also require moving the mise installation.

For a quick single-target check, reduce the generated inputs and target list:

```bash
docker run --rm -e NUMBER_OF_SEEDS=1 -e PRECISION_SET_SIZE=3 \
  -e TARGETS=json -e MIMID_TARGETS=json \
  -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

## Python 3.12 dependency choices

The Ubuntu 24.04 image uses uv-managed Python 3.12.14 (Dockerfile
`ARG PYTHON_VERSION`, kept in sync with the root mise lock). The project supports
Python `>=3.12,<3.13`; local and Docker pins select the same patch release.

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
uvx --from uv==0.12.10 uv lock --check --python 3.12.14
```

The full image build remains the installation check because it also compiles
mimid's taint instrumentation and the benchmark targets.

## Different architectures

The Dockerfile supports `linux/amd64` and `linux/arm64`; mise selects matching
binaries without a `TARGETARCH` switch. Build on a native host where possible:

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
