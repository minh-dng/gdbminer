from __future__ import annotations

from pathlib import Path


def resolve_grammar_file(args_grammar: str | None, output_directory: Path) -> Path:
    return Path(args_grammar) if args_grammar else output_directory / "parsing_g.json"
