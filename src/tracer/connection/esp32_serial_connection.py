# Serial adapter with ESP32 boot/reset control and restart recovery.
#
# SPDX-License-Identifier: AGPL-3.0

import logging as log
import struct
import time
from typing import override

import serial

from tracer.connection.connection_base_class import ConnectionBaseClass
from util.config import Config


class ESP32SerialConnection(ConnectionBaseClass):
    """Request/response exchange that survives target resets between packets.

    OpenOCD resets the C3 core when GDB attaches (to disable memory protection),
    after this process may already have seen the firmware's first ready marker.
    The firmware then reboots, prints boot noise and a new marker. A packet sent
    during the reboot is lost; one that arrives after the UART is set up is still
    answered. Resending on every marker therefore made the firmware answer one
    packet twice, and every later answer belonged to the previous query.
    """

    READY_BYTE = ord("A")
    QUIET_SEC = 0.2  # After a (possible) reset: ready = last byte is the marker, then quiet.
    GRACE_SEC = 1.0  # After a marker, wait this long (plus transfer time) for a result.

    @override
    def connect(self, config: Config):
        port = config["Connection"]["port"]
        baud_rate = config["Connection"]["baud_rate"]

        # Leave port unset: passing it to Serial() opens immediately, before we
        # can set DTR/RTS. Their default states can reset the ESP32 or select download mode.
        self.serial = serial.Serial(baudrate=baud_rate, timeout=2)
        self.serial.port = port
        # DTR/RTS drive the board's boot/reset circuit; True means asserted.
        # Set them before open(), with automatic flow control left disabled.
        self.serial.dtr = config["Connection"].get("dtr", False)
        self.serial.rts = config["Connection"].get("rts", True)
        self.serial.open()
        if config["Connection"].get("reset_pulse", True):
            time.sleep(0.05)
            self.serial.rts = False  # Release RTS; send_input waits for firmware readiness.
        log.info(f"Established connection with ESP32 SUT via Serial at {self.serial.name}")
        self._synced = False  # A reset may still follow (OpenOCD attach).

    @override
    def wait_for_input_request(self):
        # Checked in send_input, immediately before each packet: a marker read
        # here, before a later reset, would be stale.
        pass

    def _wait_until_ready(self):
        if self._synced:
            # Steady state: the marker directly follows the previous result.
            while self._read_result(None) != self.READY_BYTE:
                pass
            return
        timeout, self.serial.timeout = self.serial.timeout, self.QUIET_SEC
        try:
            while True:
                data = self.serial.read(256)
                if data:
                    self._last_byte = data[-1]
                elif getattr(self, "_last_byte", None) == self.READY_BYTE:
                    self._synced = True
                    return
        finally:
            self.serial.timeout = timeout

    def _read_result(self, deadline: float | None) -> int | None:
        """Return the next result byte, or the marker; None on silence past the deadline."""
        # ponytail: unframed; noise starting with 0/0xFF needs a firmware protocol change.
        boot_noise = False
        while True:
            # Read before checking the deadline: a delay of this process must not
            # turn an answer that is already buffered into silence.
            ret = self.serial.read(1)
            if not ret:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            self._last_byte = ret[0]
            if ret[0] == self.READY_BYTE or (not boot_noise and ret[0] in (0, 0xFF)):
                return ret[0]
            # Once boot noise starts, even 0/0xFF are noise until the ready marker.
            boot_noise = True
            log.debug("Skip boot byte %r", ret)

    @override
    def send_input(self, input: bytes) -> bool:
        log.debug(f"Sending input: {input}")
        packet = struct.pack("I", len(input)) + input
        transfer = len(packet) * 10 / self.serial.baudrate

        self._wait_until_ready()
        self.serial.write(packet)
        self.serial.flush()
        # Tracing can hold the parser at a breakpoint for much longer than any timeout.
        result = self._read_result(None)
        while result == self.READY_BYTE:
            self._synced = False
            # The firmware restarted. If it still received the packet, the
            # result follows; only silence means the packet was lost.
            result = self._read_result(time.monotonic() + self.GRACE_SEC + transfer)
            if result is None:
                self.serial.write(packet)
                self.serial.flush()
                result = self._read_result(None)
        return result == 0

    @override
    def disconnect(self):
        self.serial.close()
