# This code contains the main logic for connecting to a target device
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import logging
import multiprocessing as mp
import queue
from configparser import ConfigParser

from tracer.connection.connection_base_class import ConnectionBaseClass
from tracer.connection.serial_connection import SerialConnection


class SUTConnection:
    """
    Create Process for a Connection component, and this instance forwards
    generated inputs to this Connection component.
    """

    def __init__(self, config: ConfigParser, sut_reset_method):
        self.config = config
        self.sut_reset_method = sut_reset_method
        self.timeout = config.getint("GDB", "timeout")
        self.inputs = mp.Queue()
        self.responses = mp.Queue()
        self.ready = mp.Queue()
        self.connection = self.init_connection(config, reset=False)

    def init_connection(self, config: ConfigParser, *, reset: bool) -> ConnectionBaseClass:
        match config["Connection"]["input_channel"]:
            case "serial":
                connection = SerialConnection(config, self.inputs, self.responses, self.ready)
            case unknown:
                # Here we can add other connection types
                raise ValueError(f"Unsupported connection type: {unknown}")

        connection.daemon = True
        connection.start()
        try:
            connected = self.ready.get(block=True, timeout=self.timeout)
        except queue.Empty as exc:
            raise TimeoutError("Timed out connecting to SUT") from exc
        if not connected:
            raise ConnectionError("Failed to connect to SUT")
        if reset:
            self.sut_reset_method()
        return connection

    def send_input(self, fuzz_input: bytes):
        self.inputs.put(fuzz_input)

    def input_accepted(self, fuzz_input: bytes) -> bool:
        while True:
            self.inputs.put(fuzz_input)
            try:
                return self.responses.get(block=True, timeout=self.timeout)
            except queue.Empty:
                logging.warning("Connection timeout!")
                # return False
                self.disconnect()
                self.connection = self.init_connection(self.config, reset=True)

    def disconnect(self):
        assert self.connection.pid is not None
        self.connection.terminate()
        self.connection.join(timeout=60)
        self.connection.close()
