# This code contains the main logic for tracing
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import argparse
import dataclasses
import json
import logging
import time
from configparser import ConfigParser
from pathlib import Path

from tracer.gdb_tracer import GDBTracer
from util import setup_logging


def create_output_dir(output_dir_base: Path) -> Path:
    base = output_dir_base.expanduser()
    base.mkdir(parents=True, exist_ok=True)
    counter = 0
    while True:
        output_directory = base / f"trial-{counter}"
        try:
            output_directory.mkdir(parents=True, exist_ok=False)
            return output_directory
        except FileExistsError:
            counter += 1


def generate_trace(filename: Path, config: ConfigParser) -> list[GDBTracer.TraceEntry]:
    gdb_tracer = GDBTracer(config)

    # Start gdb execution
    trace = gdb_tracer.trace_input(filename)
    logging.debug(trace)

    return trace


def main() -> None:
    start_time = time.time()

    # cli
    parser = argparse.ArgumentParser(description="Generate traces of a program")
    parser.add_argument("--config", required=True, type=str, help="Path to a config file.")

    config_file_path = Path(parser.parse_args().config).expanduser()

    if not config_file_path.is_file():
        raise Exception(f"Config file at {config_file_path} does not exist")

    config = ConfigParser()
    config.read(config_file_path)

    # Setup logging
    output_directory = create_output_dir(Path(config["BASIC"]["output_directory"]))
    setup_logging(output_directory, config["LOGS"]["log_level"])

    seed_directory = Path(config["BASIC"]["seed_directory"])
    # list_of_traces = []
    for filename in (p for p in seed_directory.iterdir() if p.is_file()):
        logging.info(f"Start generating trace for {filename}")
        trace = generate_trace(filename, config)
        # list_of_traces.append(trace)
        trace_file_path = output_directory / f"{filename.name}.trace"
        with trace_file_path.open("w") as trace_file:
            json.dump(trace, trace_file, default=dataclasses.asdict)

        logging.info(f"Write trace of {filename.name} to {trace_file_path}")

    # print(list_of_traces)
    logging.info(f"Tracing time: {time.time() - start_time} seconds")


if __name__ == "__main__":
    main()
