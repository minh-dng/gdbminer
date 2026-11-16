"""Where a configuration's results go: target folder, setup suffix and trial number.

A configuration `example_firmware/<firmware>/configuration/configuration.<suffix>.toml` is
published to `<out>/<target>/trial-N-<suffix>/`. The firmware folder names the chip and the
application; the TOML name names the setup (C3 `1-cable`/`2-cables`, S3
`1-watchpoint`/`2-watchpoints`), so both are needed to tell two runs apart. N counts per target
and setup, so a new setup starts at trial-0 next to older trials of another setup.
"""

import re
from pathlib import Path

# The evaluation folders name the parser library, as `evaluation/stm32_applications` does.
LIBRARY_NAMES = {"json": "arduinojson", "xml": "libyxml"}
# Gitignored. One folder per firmware and setup holds an unfinished run.
SCRATCH_ROOT = Path("output/eval-runner")


def firmware_name(config: Path) -> str:
    """`example_firmware/esp32-c3_json/configuration/x.toml` gives `esp32-c3_json`."""
    return config.parent.parent.name


def setup_suffix(config: Path) -> str:
    """`configuration.1-cable.toml` gives `1-cable`."""
    _, _, suffix = config.name.removesuffix(".toml").partition(".")
    if not config.name.endswith(".toml") or not suffix:
        raise ValueError(f"{config.name}: expected configuration.<setup>.toml")
    return suffix


def target_name(firmware: str) -> str:
    """`esp32-c3_json` gives `esp32-c3_arduinojson`; other applications keep their name."""
    chip, _, application = firmware.partition("_")
    return f"{chip}_{LIBRARY_NAMES.get(application, application)}"


def next_trial(target_dir: Path, suffix: str) -> int:
    """The highest `trial-N-<suffix>` in `target_dir` plus 1, or 0 if there is none."""
    pattern = re.compile(rf"trial-(\d+)-{re.escape(suffix)}")
    numbers = [int(m[1]) for p in target_dir.glob("trial-*") if (m := pattern.fullmatch(p.name))]
    return max(numbers, default=-1) + 1


def destination(out: Path, config: Path) -> Path:
    """`<out>/<target>/trial-N-<suffix>`, with N computed now from the folders that exist."""
    suffix = setup_suffix(config)
    target_dir = out / target_name(firmware_name(config))
    return target_dir / f"trial-{next_trial(target_dir, suffix)}-{suffix}"


def scratch_dir(config: Path) -> Path:
    """The working folder of an unfinished run: `output/eval-runner/<firmware>-<suffix>`."""
    return SCRATCH_ROOT / f"{firmware_name(config)}-{setup_suffix(config)}"


def preview(configs: list[Path], out: Path) -> str:
    """One `TOML -> destination/` line per configuration, in run order."""
    lines = [f"{config} -> {destination(out, config)}/" for config in configs]
    return "\n".join([*lines, "(run/ in each destination holds the logs and provenance)"])
