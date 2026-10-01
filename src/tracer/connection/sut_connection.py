# This code contains the main logic for connecting to a target device
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import logging
import multiprocessing as mp
import queue
import struct
from collections.abc import Callable
from enum import IntEnum, StrEnum, unique

from tracer.connection.connection_base_class import ConnectionBaseClass
from util.config import Config

READY_BYTE = ord("A")
"""Byte ('A') that the SUT sends whenever it requests an input."""

LENGTH_PREFIX = struct.Struct("<I")
"""Length sent before each input: an unsigned 32-bit little-endian integer, the byte order of
the STM32 and ESP32 firmware that reads it."""


@unique
class ParserResult(IntEnum):
    """Result byte the firmware sends after parsing an input.

    See `example_firmware/ESP32-C3 DevKitM-1-N4X.md#serial-protocol-values`.
    """

    ACCEPTED = 0
    REJECTED = 0xFF


@unique
class InputChannel(StrEnum):
    """Values of the `Connection.input_channel` configuration key."""

    SERIAL = "serial"
    ESP32_UART = "esp32-uart"


class SUTConnection:
    """
    Create Process for a Connection component, and this instance forwards
    generated inputs to this Connection component.
    """

    def __init__(self, config: Config, sut_reset_method: Callable[[], None]):
        """`sut_reset_method` runs after a reconnect (`input_accepted`), so it must leave the
        target able to answer inputs; see `HardwareInstance.reset`."""
        self.config = config
        self.sut_reset_method = sut_reset_method
        self.timeout = config["GDB"]["timeout"]
        self.inputs = mp.Queue()
        self.responses = mp.Queue()
        self.ready = mp.Queue()
        self.connection = self.init_connection(config, reset=False)

    def init_connection(self, config: Config, *, reset: bool) -> ConnectionBaseClass:
        match InputChannel(config["Connection"]["input_channel"]):
            case InputChannel.SERIAL:
                from tracer.connection.serial_connection import SerialConnection

                connection = SerialConnection(config, self.inputs, self.responses, self.ready)
            case InputChannel.ESP32_UART:
                from tracer.connection.esp32_serial_connection import ESP32UARTConnection

                connection = ESP32UARTConnection(config, self.inputs, self.responses, self.ready)

        connection.daemon = True
        connection.start()
        try:
            try:
                connected = self.ready.get(block=True, timeout=self.timeout)
            except queue.Empty as exc:
                raise TimeoutError("Timed out connecting to SUT") from exc
            if not connected:
                raise ConnectionError("Failed to connect to SUT")
            if reset:
                self.sut_reset_method()
        except BaseException:
            # The caller cannot clean up a process that has not been returned yet.
            connection.terminate()
            connection.join()
            connection.close()
            raise
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
                self.disconnect()
                # Discard any unconsumed input or late response from the old process.
                self.inputs = mp.Queue()
                self.responses = mp.Queue()
                self.ready = mp.Queue()
                self.connection = self.init_connection(self.config, reset=True)

    def disconnect(self):
        assert self.connection.pid is not None
        self.connection.terminate()
        self.connection.join(timeout=60)
        self.connection.close()
