# This code contains the main logic for tracing
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import argparse
import json
import logging
import time
from configparser import ConfigParser
from pathlib import Path

from tracer.gdb_tracer import GDBTracer


def uniquify(logfile_path: Path) -> Path:
    counter = 0
    while True:
        new_path = Path(f"{logfile_path}-{counter}")
        counter += 1
        if not new_path.exists():
            return new_path


def create_output_directory(output_directory_base: Path) -> Path:
    output_directory = uniquify(logfile_path=output_directory_base / "trial")
    output_directory.mkdir(parents=True, exist_ok=True)
    return output_directory


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


def generate_trace(filename: Path, config: ConfigParser) -> list[GDBTracer.TraceEntry]:
    gdb_tracer = GDBTracer(config)

    # Start gdb execution
    trace = gdb_tracer.trace_input(filename)
    logging.debug(trace)

    return trace


def main() -> None:
    start_time = time.time()
    # Create a parser
    parser = argparse.ArgumentParser(description="Generate traces of a program")

    # Add the arguments
    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")

    # Execute the parse_args() methode
    config_file_path = Path(parser.parse_args().config).expanduser()

    if not config_file_path.is_file():
        raise Exception(f"Config file at {config_file_path} does not exist")

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    # Setup logging
    output_directory = create_output_directory(
        output_directory_base=Path(config["BASIC"]["output_directory"])
    )
    loglevel = config["LOGS"]["log_level"]
    setup_logging(output_directory=output_directory, loglevel=loglevel)

    seed_directory = Path(config["BASIC"]["seed_directory"])
    list_of_traces = []
    for filename in sorted(seed_directory.glob("*")):
        logging.info(f"Start generating trace for {filename}")
        trace = generate_trace(filename, config)
        list_of_traces.append(trace)
        trace_file_path = output_directory / f"{filename.name}.trace"
        with trace_file_path.open("w") as trace_file:
            json.dump(trace, trace_file, default=vars)

        logging.info(f"Write trace of {filename.name} to {trace_file_path}")

    # print(list_of_traces)
    logging.info(f"Tracing time: {time.time() - start_time} seconds")


if __name__ == "__main__":
    main()
