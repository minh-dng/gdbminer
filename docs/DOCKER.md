# Docker

## Local experiments

Build the reproducibility image from the repository root, then mount a local output directory:

```bash
docker build -t gdbminer .
docker run --rm -v "$(pwd)/output:/output" gdbminer /run_experiment.sh
```

Full experiments can run for days. Use a dedicated output directory per trial so results are not overwritten.

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
