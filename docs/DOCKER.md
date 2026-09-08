# Docker

## Local experiments

Build the reproducibility image from the repository root, then mount a local output directory:

```bash
docker build -t gdbminer .
docker run --rm -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

Full experiments can run for days. Use a dedicated output directory per trial so results are not overwritten.

## Toolchain management (mise)

The image pins mise 2026.9.1 and installs the toolchain from
`docker/mise.toml` and `docker/mise.lock` with `mise install --locked`.

| Tool  | Version             | Check                             |
| ----- | ------------------- | --------------------------------- |
| uv    | 0.12.10             | `uv --version`                    |
| Java  | Temurin 11.0.32+101 | `java -version && javac -version` |
| CMake | 3.29.0              | `cmake --version`                 |
| Ninja | 1.13.2              | `ninja --version`                 |
| jq    | 1.8.2               | `jq --version`                    |

Python 3.12.14 is installed separately through uv from `.python-version`.
This uses uv's experimental `--default` option. If that option breaks, install
Python through mise again by adding it to `docker/mise.toml` and removing the
uv Python installation from the Dockerfile. Check it with
`python --version && UV_PYTHON=3.12 uv python find`.

mise selects the correct binaries for `linux/amd64` and `linux/arm64`. Native
build dependencies remain installed through apt or built from source.

For a quick single-target check, reduce the generated inputs and target list:

```bash
docker run --rm -e NUMBER_OF_SEEDS=1 -e PRECISION_SET_SIZE=3 \
  -e TARGETS=json -e MIMID_TARGETS=json \
  -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

## Different architectures

The Dockerfile supports `linux/amd64` and `linux/arm64`; mise selects matching
binaries without a `TARGETARCH` switch. Build on a native host where possible:

```bash
docker build --platform linux/arm64 -t gdbminer:arm64 .
```

When a remote native host is available, prefer it over architecture emulation. Keep machine-specific context details in an untracked `docs/DOCKER.local.md`; this file is local to each machine. Otherwise, create a context and run the build and experiment there:

```bash
docker context create remote --docker "host=ssh://user@host"
docker --context remote build --platform linux/arm64 -t gdbminer:arm64 .
docker --context remote run --rm -v "$(pwd)/output:/output" gdbminer:arm64 /run_experiment.sh
```

The Docker CLI sends the local build context to the remote daemon. The `-v` source path is resolved on the remote host, so create the output directory there and use its absolute remote path. For physical firmware, ensure the container can reach the remote GDB server or the attached USB debugger.
