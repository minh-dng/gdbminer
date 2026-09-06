from __future__ import annotations

from pathlib import Path


def find_output_directory(output_directory_base: Path) -> Path:
    """Find the last 'trial-*' folder in the output directory base."""
    return next(
        iter(
            sorted(
                output_directory_base.glob("trial-*"),
                key=lambda x: int(x.name.split("-")[1]),
                reverse=True,
            )
        )
    )
