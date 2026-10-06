# Shared configuration and input transport for hardware debug targets.
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import logging
import shlex
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import override

from tracer.connection.sut_connection import SUTConnection
from tracer.instance.sut_instance import SUTInstance
from util import Config

GDB_SERVER_STOP_TIMEOUT_SEC = 5
"""Time the GDB server gets to exit after SIGTERM before `_stop_gdb_server` kills it."""


class HardwareInstance(SUTInstance, ABC):
    """GDB-server settings, input file and serial input transport shared by hardware targets."""

    connection: SUTConnection
    """Serial input transport, opened by the backend's `__enter__`."""
    gdb_server: subprocess.Popen[bytes]
    """GDB server process, started by the backend's `__enter__`."""

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config)
        self.gdb_server_path_with_args = shlex.split(config["GDB"]["gdb_server_path"])
        self.gdb_server_address = config["GDB"]["gdb_server_address"]
        self.watchpoint_count = config["GDB"]["watchpoint_count"]
        self.input_file = Path(input_file)

    @abstractmethod
    def reset(self) -> None:
        """Halt the target in a freshly reset state.

        Called by `__enter__` and, through `init_sut_connection`, by `SUTConnection` after a serial
        reconnect, when the target may be running.
        """

    def init_sut_connection(self):
        return SUTConnection(self.config, self.reset)

    def _stop_gdb_server(self) -> None:
        """Stop the GDB server, killing it if it ignores SIGTERM.

        A server left running keeps the debug probe open, so the next instance's server could not
        attach to the target.
        """
        self.gdb_server.terminate()
        try:
            self.gdb_server.wait(timeout=GDB_SERVER_STOP_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            self.gdb_server.kill()
            self.gdb_server.wait()
        logging.info("GDB Server terminated")

    @override
    def send_input(self) -> None:
        with self.input_file.open("rb") as f:
            input = f.read()
        self.connection.send_input(input)

    @override
    def input_accepted(self, input: bytes) -> bool:
        self.number_of_tested_inputs += 1
        accepted = self.connection.input_accepted(input)
        logging.debug(f"Test {input} : {accepted=}")
        return accepted
