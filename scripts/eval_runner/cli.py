"""Command line of the evaluation runner: a flag for every input, a picker for each one missing.

Nothing has a built-in default because every value depends on the machine or the campaign: the
boards attached, the GDB port a concurrent session leaves free, the evaluation folder. The
configurations run one after another in the order given; one that fails for good does not stop
the others, and the exit code is non-zero if any failed.
"""

import shutil
from pathlib import Path
from typing import Annotated

import questionary
import typer

from scripts.eval_runner import layout, provenance, stages
from scripts.eval_runner.devices import ADAPTER, UART, Board, list_devices

CONFIGS = "example_firmware/esp32-*/configuration/*.toml"
OTHER = "other path…"

app = typer.Typer(add_completion=False)


def _pick_configs() -> list[Path]:
    # The TOML names repeat across targets (1-cable, 2-cables, ...), so show the folder too.
    choices = [
        questionary.Choice(f"{path.parent.parent.name} / {path.name}", value=path)
        for path in sorted(Path().glob(CONFIGS))
    ]
    return questionary.checkbox(
        "Configurations (Space toggles, Enter confirms)",
        choices=choices,
        validate=lambda picked: bool(picked) or "Pick at least one",
    ).unsafe_ask()


def _pick_out() -> Path:
    folders = [str(path) for path in sorted(Path("evaluation").glob("*_applications"))]
    answer = questionary.select("Destination", choices=[*folders, OTHER]).unsafe_ask()
    if answer == OTHER:
        answer = questionary.path("Destination folder", only_directories=True).unsafe_ask()
    return Path(answer)


def _pick_device(role: str) -> str:
    devices = list_devices()
    if not devices:
        raise typer.BadParameter(f"no USB serial device found for the {role}")
    choices = [
        questionary.Choice(f"{d.path}  {d.serial}  {d.description}", value=d.serial)
        for d in devices
    ]
    return questionary.select(f"The {role}", choices=choices).unsafe_ask()


def _pick_gdb_port() -> int:
    def valid(text: str) -> bool | str:
        return (text.isdigit() and 0 < int(text) < 65536) or "A port from 1 to 65535"

    return int(questionary.text("GDB port", validate=valid).unsafe_ask())


def _uses_uart(config: Path) -> bool:
    """Whether `config` needs the UART bridge; an unreadable one fails later, in `_runs`."""
    try:
        return stages.uses_uart(config)
    except (OSError, ValueError, KeyError):
        return False


def _runs(
    configs: list[Path], serials: dict[str, str], gdb_port: int, retries: int, hours: float
) -> dict[Path, stages.Run | str]:
    """A run per configuration, or the error that stops it before anything starts."""
    runs: dict[Path, stages.Run | str] = {}
    for config in configs:
        roles = (ADAPTER, UART) if _uses_uart(config) else (ADAPTER,)
        board = Board({role: serials[role] for role in roles})
        try:
            runs[config] = stages.Run(config, board, gdb_port, retries, hours * 3600)
        except Exception as error:
            runs[config] = f"failed: {error}"
    return runs


def _scratch_state(run: stages.Run, fresh: bool) -> str | None:
    """A preview line for a run that has scratch state, or None."""
    if not run.scratch.exists():
        return None
    if fresh:
        return f"{run.scratch}: --fresh discards it"
    traces = len(list(run.trial.glob("*.trace")))
    return f"{run.scratch}: continues, {traces} traces kept"


def _execute(run: stages.Run, out: Path, fresh: bool) -> str:
    """Run every stage and publish; return the result line."""
    try:
        if fresh and run.scratch.exists():
            shutil.rmtree(run.scratch)
        run.prepare(out)
        provenance.record(run)
        run.execute()
        return f"done -> {run.publish(out)}/"
    except Exception as error:
        return f"failed: {error}"


@app.command()
def main(
    configs: Annotated[
        list[Path] | None,
        typer.Argument(help=f"TOML files; picked from {CONFIGS} if omitted.", show_default=False),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Destination root, such as evaluation/esp32-c3_applications."),
    ] = None,
    adapter_serial: Annotated[
        str | None, typer.Option(help="USB serial number of the debug adapter.")
    ] = None,
    uart_serial: Annotated[
        str | None,
        typer.Option(help='USB serial number of the UART bridge (input_channel = "esp32-uart").'),
    ] = None,
    gdb_port: Annotated[
        int | None, typer.Option(min=1, max=65535, help="GDB port of OpenOCD.")
    ] = None,
    max_retries: Annotated[int, typer.Option(min=0, help="Retries per failure.")] = 3,
    stage_timeout: Annotated[
        float, typer.Option(min=0, help="Hours after which a stage is stopped.")
    ] = 24,
    yes: Annotated[bool, typer.Option("--yes", help="Start without the preview prompt.")] = False,
    fresh: Annotated[
        bool, typer.Option("--fresh", help="Discard unfinished scratch state first.")
    ] = False,
) -> None:
    """Flash, trace, mine and evaluate ESP32 configurations, resuming after failures."""
    try:
        configs = configs or _pick_configs()
        out = out or _pick_out()
        serials = {ADAPTER: adapter_serial or _pick_device(ADAPTER)}
        if any(_uses_uart(config) for config in configs):
            serials[UART] = uart_serial or _pick_device(UART)
        gdb_port = gdb_port or _pick_gdb_port()
        runs = _runs(configs, serials, gdb_port, max_retries, stage_timeout)

        print(layout.preview([c for c, run in runs.items() if isinstance(run, stages.Run)], out))
        for config, run in runs.items():
            if isinstance(run, str):
                print(f"{config}: {run}")
            elif state := _scratch_state(run, fresh):
                print(state)
        if not yes:
            input("Press Enter to start, Ctrl-C to cancel. ")

        results: dict[Path, str] = {}
        for config, run in runs.items():
            if isinstance(run, str):
                results[config] = run
            else:
                results[config] = _execute(run, out, fresh)
                print(f"{config}: {results[config]}", flush=True)
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Start again to continue from the scratch state (--fresh discards it)."
        )
        raise typer.Exit(130) from None

    print("\nSummary:")
    for config, result in results.items():
        print(f"  {config}: {result}")
    raise typer.Exit(int(any(result.startswith("failed") for result in results.values())))
