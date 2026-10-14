"""Record what a run used, in its `run/` folder, so a published result can be traced back.

`provenance.txt` gets one block per start of the runner (a resumed run may use a new commit or
tool); devices appear by USB serial number, as paths change on replug. The seed and evaluation
hashes and `build.options.json` describe inputs that must not change during a run, so they are
written again. The exact command lines are in `commands.txt`, written by the stages.
"""

import hashlib
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from scripts.eval_runner.stages import Run


def _output(command: list[str]) -> str:
    """stdout and stderr of `command`, or the error; a missing tool must not stop the run."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"({shlex.join(command)} failed: {error})"
    return (result.stdout + result.stderr).rstrip()


def _first_line(command: list[str]) -> str:
    return next(iter(_output(command).splitlines()), "")


def _sha256(folder: Path) -> str:
    """`sha256sum` lines for the files of `folder`."""
    files = sorted(path for path in folder.iterdir() if path.is_file())
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
    )


def record(run: Run) -> None:
    """Append a provenance block and write the input hashes and build options to `run/`."""
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
        f"arduino-cli lib list:\n{_output([arduino_cli, 'lib', 'list'])}\n\n"
    )
    with (run.run_dir / "provenance.txt").open("a", encoding="utf-8") as file:
        file.write(block)
    (run.run_dir / "seeds.sha256").write_text(_sha256(run.seeds), encoding="utf-8")
    (run.run_dir / "eval.sha256").write_text(_sha256(run.eval_directory), encoding="utf-8")
    shutil.copy2(run.binary.parent / "build.options.json", run.run_dir)
