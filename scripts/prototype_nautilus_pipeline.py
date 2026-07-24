#!/usr/bin/env python3
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

"""PROTOTYPE: Convert a GDBMiner grammar and sample it with NAUTILUS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from gdbminer_nautilus.grammar_adapter import (  # noqa: E402
    convert_gdbminer_to_nautilus,
    load_gdbminer_grammar,
    write_nautilus_json,
)
from gdbminer_nautilus.nautilus_runner import generate_inputs  # noqa: E402

DEFAULT_GRAMMAR = (
    REPO_ROOT
    / "evaluation"
    / "stm32_applications"
    / "stm32_cgidecode"
    / "trial-0"
    / "parsing_g.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "prototype_nautilus"
DEFAULT_NAUTILUS_DIR = REPO_ROOT / "third_party" / "nautilus"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "PROTOTYPE: convert a GDBMiner parsing_g.json file into NAUTILUS "
            "rules and optionally generate sample inputs."
        )
    )
    parser.add_argument("--grammar", type=Path, default=DEFAULT_GRAMMAR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--nautilus-dir", type=Path, default=DEFAULT_NAUTILUS_DIR)
    parser.add_argument("--tree-depth", type=int, default=40)
    parser.add_argument("--generate-count", type=int, default=1)
    args = parser.parse_args()

    document = load_gdbminer_grammar(args.grammar)
    converted = convert_gdbminer_to_nautilus(document)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    output_grammar = args.out_dir / "gdbminer.nautilus.json"
    output_map = args.out_dir / "symbol-map.json"
    write_nautilus_json(converted, output_grammar)
    with output_map.open("w", encoding="utf-8") as map_file:
        json.dump(dict(converted.symbol_map), map_file, indent=2)
        map_file.write("\n")

    state = {
        "prototype": "PROTOTYPE - GDBMiner grammar to NAUTILUS generator",
        "source_grammar": str(args.grammar),
        "nautilus_grammar": str(output_grammar),
        "symbol_map": str(output_map),
        **converted.summary(),
        "sample_rules": converted.to_json()[:5],
    }

    if args.generate_count > 0:
        generated = generate_inputs(
            output_grammar,
            args.nautilus_dir,
            tree_depth=args.tree_depth,
            count=args.generate_count,
        )
        state["generated_inputs"] = [
            {
                "index": generated_input.index,
                "bytes": len(generated_input.data),
                "preview": generated_input.preview,
            }
            for generated_input in generated
        ]

    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
