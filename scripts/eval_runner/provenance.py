"""Record what a run used, in its `run/` folder, so a published result can be traced back.

`provenance.txt` gets one block per start of the runner (a resumed run may use a new commit or
tool); devices appear by USB serial number, as paths change on replug. The hashes of the seeds,
the evaluation files and the firmware build are written at the first start; a later start with
other inputs fails, as the results so far were made with the old ones. The exact command lines
are in `commands.txt`, written by the stages.
"""

import hashlib
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from scripts.eval_runner.stages import ConfigError, Run


def _output(command: list[str]) -> str:
    """stdout and stderr of `command`, or the error; a missing tool must not stop the run."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"({shlex.join(command)} failed: {error})"
    return (result.stdout + result.stderr).rstrip()


def _first_line(command: list[str]) -> str:
    return next(iter(_output(command).splitlines()), "")


def _sha256(folder: Path, ignore: str | None = None) -> str:
    """`sha256sum` lines for the files of `folder`, except those that match the pattern `ignore`."""
    files = sorted(
        path for path in folder.iterdir() if path.is_file() and not (ignore and path.match(ignore))
    )
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
    )


def record(run: Run) -> None:
    """Check or write the input hashes, append a provenance block, copy the build options."""
    # The ESP32 uploader (flasher.py) caches each upload as `*_flashed.bin` in the build folder.
    inputs = [
        ("seeds", run.seeds, None),
        ("eval", run.eval_directory, None),
        ("build", run.binary.parent, "*_flashed.bin"),
    ]
    for name, folder, ignore in inputs:
        hashes, recorded = _sha256(folder, ignore), run.run_dir / f"{name}.sha256"
        if not recorded.exists():
            recorded.write_text(hashes, encoding="utf-8")
        elif recorded.read_text(encoding="utf-8") != hashes:
            raise ConfigError(f"{folder} changed since this trial started; use --fresh")
    with run.config.open("rb") as file:
        gdb = tomllib.load(file)["GDB"]
    openocd = str(Path(shlex.split(gdb["gdb_server_path"])[0]).expanduser())
    arduino_cli = shutil.which("arduino-cli") or "arduino-cli"
    devices = "".join(f"  {role}: {serial}\n" for role, serial in run.board.serials.items())
    block = (
        f"== start {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"configuration: {run.config}\n"
        f"git commit: {_output(['git', 'rev-parse', 'HEAD'])}\n"
        f"git status --short:\n{_output(['git', 'status', '--short'])}\n"
        f"gdb: {_first_line([str(Path(gdb['gdb_path']).expanduser()), '--version'])}\n"
        f"openocd: {_first_line([openocd, '--version'])}\n"
        f"python: {sys.version.split()[0]}\n"
        f"GDB port: {run.gdb_port}\n"
        f"devices (USB serial numbers):\n{devices}"
        f"arduino-cli core list:\n{_output([arduino_cli, 'core', 'list'])}\n"
        f"arduino-cli lib list:\n{_output([arduino_cli, 'lib', 'list'])}\n\n"
    )
    with (run.run_dir / "provenance.txt").open("a", encoding="utf-8") as file:
        file.write(block)
    shutil.copy2(run.binary.parent / "build.options.json", run.run_dir)
