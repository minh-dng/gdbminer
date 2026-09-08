# Local Docker setup

## UTM Linux ARM64 daemon

Prefer the Docker daemon in the `utm-ubuntu-arm64` VM when it is available. It provides a native Linux ARM64 environment for GDB and Valgrind.

Create the Docker context once from macOS:

```bash
docker context create utm-ubuntu-arm64 \
  --docker "host=ssh://utm-ubuntu-arm64"
```

Build and run without changing the active context:

```bash
docker --context utm-ubuntu-arm64 info
docker --context utm-ubuntu-arm64 build --platform linux/arm64 -t gdbminer:arm64 .
docker --context utm-ubuntu-arm64 run --rm \
  -v "$(pwd)/output:/output" gdbminer:arm64 /run_experiment.sh
```

The Docker CLI sends the local build context to the VM. The bind-mount source is resolved inside the VM, so create an output directory there and replace `$(pwd)/output` with its absolute VM path.
