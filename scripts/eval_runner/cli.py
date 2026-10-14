"""Command line of the evaluation runner."""

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main() -> None:
    """Flash, trace, mine and evaluate ESP32 configurations."""
