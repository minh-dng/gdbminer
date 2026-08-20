# This code compares mutational against grammar-based fuzzing
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

import argparse
import json
import logging
import os
from configparser import ConfigParser
from pathlib import Path

from eval import resolve_grammar_file
from eval.grammar import CoverageFuzzer, MutationFuzzer, trim_grammar
from tracer.gdb_tracer import GDBTracer

PRECISION_SIZE = int(os.environ.get("PRECISION_SET_SIZE", "1000"))

def find_output_directory(output_directory_base: Path) -> Path:
    # Find last 'trial-*' folder
    return next(
        sorted(
            output_directory_base.glob("trial-*"),
            key=lambda x: int(x.name.split("-")[1]),
            reverse=True,
        )
    )


def setup_logging(output_directory: Path, loglevel: str) -> None:
    logger = logging.getLogger()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s %(funcName)s()] %(message)s"
    )

    file_logger = logging.FileHandler(output_directory / "out.log")
    file_logger.setLevel(loglevel)
    file_logger.setFormatter(formatter)
    logger.addHandler(file_logger)

    stdout_logger = logging.StreamHandler()
    stdout_logger.setLevel(loglevel)
    stdout_logger.setFormatter(formatter)
    logger.addHandler(stdout_logger)

    logging.root.setLevel(loglevel)


def main() -> None:
    # Create a parser
    parser = argparse.ArgumentParser(
        description="Calculates the precision of grammar-based fuzzer against a mutation-based one"
    )

    # Add the arguments
    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")

    parser.add_argument("--grammar", required=False, type=str, help="Path to a grammar file.")

    # Execute the parse_args() methode
    args = parser.parse_args()
    config_file_path = Path(args.config).expanduser()

    if not config_file_path.is_file():
        raise Exception(f"Config file at {config_file_path} does not exist")

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    output_directory = find_output_directory(Path(config["BASIC"]["output_directory"]))

    loglevel = config["LOGS"]["log_level"]
    setup_logging(output_directory=output_directory, loglevel=loglevel)

    seeds_directory = Path(config["BASIC"]["seed_directory"])

    seeds = []
    for seed_file in seeds_directory.glob("*"):
        with seed_file.open() as f:
            seed_content = f.read()
            seeds.append(seed_content)

    mutation_fuzzer = MutationFuzzer(seed=seeds)

    grammar_file = resolve_grammar_file(args.grammar, output_directory)

    with grammar_file.open() as f:
        mined = json.load(f)
    grammar = mined["[grammar]"]
    start = mined["[start]"]

    grammar_fuzzer = CoverageFuzzer(trim_grammar(grammar, start))

    # fuzzer = F.LimitFuzzer(grammar)
    mutation_accepted_count = 0
    grammar_accepted_count = 0

    with GDBTracer.open_sut_instance(config) as instance:
        instance.continue_execution()
        for i in range(PRECISION_SIZE):
            # input = fuzzer.fuzz()

            input = mutation_fuzzer.fuzz()
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                mutation_accepted_count += 1.0

            input = grammar_fuzzer.fuzz(start)
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                grammar_accepted_count += 1.0
            else:
                logging.info(f"Generated non accepting input: {input!r}")

    logging.info(
        f"Accepted inputs MutationFuzzer: {mutation_accepted_count}, GrammarFuzzer: {grammar_accepted_count} "
    )


if __name__ == "__main__":
    main()
