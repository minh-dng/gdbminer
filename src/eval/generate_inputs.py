# This code can generate random inputs from context-free grammars
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

import argparse
import json
from configparser import ConfigParser
from pathlib import Path

from eval import resolve_grammar_file
from eval.grammar import CoverageFuzzer, trim_grammar
from tracer.gdb_tracer import GDBTracer

PRECISION_SIZE = 1000


def find_output_directory(output_directory_base: Path) -> Path:
    # Find last 'trial-*' folder
    return next(
        iter(
            sorted(
                output_directory_base.glob("trial-*"),
                key=lambda x: int(x.name.split("-")[1]),
                reverse=True,
            )
        )
    )


def main() -> None:
    # Create a parser
    parser = argparse.ArgumentParser(description="Generates inputs from grammar")

    # Add the arguments
    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")

    parser.add_argument("--grammar", type=str, help="Path to a grammar file.")

    parser.add_argument("out", type=str, help="Path to output folder.")

    parser.add_argument("count", type=int, help="Number of files to generate.")

    # Execute the parse_args() methode
    args = parser.parse_args()
    config_file_path = Path(args.config).expanduser()

    if not config_file_path.is_file():
        raise Exception(f"Config file at {config_file_path} does not exist")

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    output_directory = Path(args.out)

    grammar_file = resolve_grammar_file(args.grammar, output_directory)

    with grammar_file.open() as f:
        mined = json.load(f)
    grammar = mined["[grammar]"]
    start = mined["[start]"]
    grammar = trim_grammar(grammar, start)
    fuzzer = CoverageFuzzer(grammar)

    seen = set()
    i = 0

    with GDBTracer.open_sut_instance(config) as instance:
        instance.continue_execution()

        while i < args.count:
            input = fuzzer.fuzz(start)
            if not input.strip():
                continue
            if input in seen:
                continue
            seen.add(input)
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                i += 1
                with (output_directory / f"input.{i}").open("w") as out_file:
                    out_file.write(input)


if __name__ == "__main__":
    main()
