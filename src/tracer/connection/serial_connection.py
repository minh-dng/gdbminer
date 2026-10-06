# This code enables serial connections to a target
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import logging as log
import time
from typing import override

import serial

from tracer.connection.connection_base_class import ConnectionBaseClass
from tracer.connection.sut_connection import LENGTH_PREFIX, READY_BYTE, ParserResult


class SerialConnection(ConnectionBaseClass):
    """Exchange length-prefixed inputs after the firmware's 'A' readiness byte.

    Connection process                     Serial target
            │                                      │
            │ Wait for queued input...             │ Send 'A', then wait for input
            │ 'A' may remain in the receive buffer │
            │ Input arrives                        │
            │ wait_for_input_request()             │
            │ ◀──────── buffered or new 'A' ───────│
            │ ───────── 4-byte length ────────────▶│
            │ ───────── input bytes ──────────────▶│ Receive and parse
            │ ◀──────── 0x00 / 0xFF ───────────────│
            │ Queue acceptance result              │ Send next 'A'

    Unlike the ESP32 adapter, this exchange has no explicit restart recovery.
    """

    @override
    def connect(self, config):
        port = config["Connection"]["port"]
        baud_rate = config["Connection"]["baud_rate"]
        self.serial = serial.Serial(port, baud_rate)
        time.sleep(1)  # Give a bit time to open connection
        self.serial.reset_input_buffer()
        log.info(f"Established connection with SUT via Serial at port {self.serial.name}")

    @override
    def wait_for_input_request(self):
        read = ""
        while not read or read[-1] != READY_BYTE:
            read = self.serial.read(1)
        log.debug(f"READ: {read}")

    @override
    def send_input(self, input: bytes) -> bool:
        # First send length
        log.debug(f"Sending input: {input}")
        input_len = LENGTH_PREFIX.pack(len(input))
        self.serial.write(input_len)

        # After that input
        self.serial.write(input)

        self.serial.flush()

        ret = self.serial.read(1)
        log.debug(f"Received: {ret}")
        if ret[0] == ParserResult.ACCEPTED:
            return True
        elif ret[0] == ParserResult.REJECTED:
            return False
        else:
            log.error(f"Unexpected return value {ret[0]}")
            return True  # Let's consider it accepted

    @override
    def disconnect(self):
        self.serial.close()
