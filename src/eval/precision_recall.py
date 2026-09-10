# This code can generate calculate precision and recall values from a grammar
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
from configparser import ConfigParser
from pathlib import Path

import cmimid.fuzz as F
from eval import resolve_grammar_file
from eval.grammar import accepts
from tracer.gdb_tracer import GDBTracer
from util import find_output_directory, setup_logging

PRECISION_SIZE = int(os.environ.get("PRECISION_SET_SIZE", "1000"))


def main() -> None:
    # Create a parser
    parser = argparse.ArgumentParser(description="Calculates the precision of a mined grammar")

    # Add the arguments
    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")

    parser.add_argument("--grammar", type=str, help="Path to a grammar file.")

    parser.add_argument("--out", type=str, help="Path to an output file.")

    # Execute the parse_args() methode
    args = parser.parse_args()
    config_file_path = Path(args.config).expanduser()

    if not config_file_path.is_file():
        raise Exception(f"Config file at {config_file_path} does not exist")

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    output_directory = find_output_directory(Path(config["BASIC"]["output_directory"]))

    setup_logging(output_directory, config["LOGS"]["log_level"])

    eval_directory = Path(config["BASIC"]["eval_directory"])

    grammar_file = resolve_grammar_file(args.grammar, output_directory)

    with grammar_file.open() as f:
        mined = json.load(f)
    grammar = mined["[grammar]"]
    start = mined["[start]"]

    # fuzzer = GrammarCoverageFuzzer(readable(grammar), start_symbol=start)
    fuzzer = F.LimitFuzzer(grammar)
    accepted_count = 0

    with GDBTracer.open_sut_instance(config) as instance:
        instance.continue_execution()
        for i in range(PRECISION_SIZE):
            # input = fuzzer.fuzz()
            input = fuzzer.fuzz(start)
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                accepted_count += 1.0
            else:
                logging.info(f"Generated non accepting input: {input!r}")

    def handler(signum, frame):
        raise TimeoutError()

    # set the timeout handler
    signal.signal(signal.SIGALRM, handler)

    parsed_count = 0
    eval_set_len = 0
    for eval_f_name in eval_directory.glob("*"):
        with eval_f_name.open() as eval_file:
            eval_string = eval_file.read()
            eval_set_len += 1
            try:
                signal.alarm(10)
                if accepts(grammar, eval_string, start):
                    parsed_count += 1.0
            except (SyntaxError, TimeoutError):
                logging.warning(f"Can not parse {eval_string!r}")
            finally:
                signal.alarm(0)
    prec = accepted_count / PRECISION_SIZE
    rec = parsed_count / eval_set_len
    result = {"precision": prec, "recall": rec}

    result["f1"] = 2 * ((prec * rec) / (prec + rec)) if prec + rec else 0.0

    if "[no_tested_inputs]" in mined:
        result["no_tested_inputs"] = mined["[no_tested_inputs]"]

    logging.info(result)

    if args.out:
        with Path(args.out).open("w") as f:
            json.dump(result, f)


if __name__ == "__main__":
    main()
