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


def main() -> None:
    # cli
    parser = argparse.ArgumentParser(description="Generates inputs from grammar")

    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")
    parser.add_argument("--grammar", type=str, help="Path to a grammar file.")
    parser.add_argument("out", type=str, help="Path to output folder.")
    parser.add_argument("count", type=int, help="Number of files to generate.")

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

    seen: set[str] = set()
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
            accepted = instance.input_accepted(input.encode())
            if accepted:
                i += 1
                (output_directory / f"input.{i}").write_text(input)


if __name__ == "__main__":
    main()
