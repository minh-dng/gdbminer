# Serial adapter with ESP32 boot/reset control and restart recovery.
#
# SPDX-License-Identifier: AGPL-3.0

import logging as log
import time
from typing import override

import serial

from tracer.connection.connection_base_class import ConnectionBaseClass
from tracer.connection.sut_connection import LENGTH_PREFIX, READY_BYTE, ParserResult
from util import Config

UART_BITS_PER_BYTE = 10
"""Bits on the wire per byte with PySerial's default 8N1: one start, eight data, one stop bit."""


class ESP32UARTConnection(ConnectionBaseClass):
    """Request/response exchange that survives target resets between packets.

    OpenOCD resets the C3 core when GDB attaches (to disable memory protection), after this process
    may already have seen the firmware's first ready marker. The firmware then reboots, prints boot
    noise and a new marker. A packet sent during the reboot is lost; one that arrives after the UART
    is set up is still answered. Resending on every marker therefore made the firmware answer one
    packet twice, and every later answer belonged to the previous query.

    Connection process                     ESP32 / debugger
            │                                      │
            │ Wait for queued input...             │ Initial 'A' may be buffered
            │                                      │ Reset / boot output may follow
            │ Input arrives                        │
            │ wait_for_input_request()             │
            │ ◀──────── boot bytes / 'A' ──────────│
            │ Wait for quiet after the final 'A'   │
            │ ───────── length + input ───────────▶│ Receive and parse
            │ ◀──────── 0x00 / 0xFF ───────────────│
            │ Queue acceptance result              │

    After synchronisation, readiness is the next 'A' after the previous result. A restart during
    transmission is handled by `send_input`'s recovery loop.
    """

    @override
    def connect(self, config: Config):
        settings = config["Connection"]
        port = settings["port"]
        baud_rate = settings["baud_rate"]
        self.quiet_sec = settings.get("quiet_sec", 0.2)
        """Silence after an 'A' that marks the first readiness (`Connection.quiet_sec`)."""
        self.grace_sec = settings.get("grace_sec", 1.0)
        """Wait for a result after a restart, beyond the packet's transfer time, before the
        packet counts as lost (`Connection.grace_sec`)."""
        self.reset_pulse_sec = settings.get("reset_pulse_sec", 0.05)
        """Length of the RTS pulse on EN (`Connection.reset_pulse_sec`)."""

        # Leave port unset: passing it to `Serial()` opens immediately, before we can set DTR/RTS.
        # Their default states can reset the ESP32 or select download mode.
        self.serial = serial.Serial(baudrate=baud_rate, timeout=2)
        self.serial.port = port
        # DTR/RTS drive the board's boot/reset circuit; True means asserted. Set them before
        # `open()`, with automatic flow control left disabled.
        self.serial.dtr = settings.get("dtr", False)
        self.serial.rts = settings.get("rts", True)
        self.serial.open()
        if settings.get("reset_pulse", True):
            time.sleep(self.reset_pulse_sec)
            self.serial.rts = False  # Release RTS; `send_input` waits for firmware readiness.
        log.info(f"Established connection with ESP32 SUT via Serial at {self.serial.name}")
        self._synced = False
        """The first readiness has been seen. Until then, a reset may still follow (OpenOCD
        resets the core when GDB attaches)."""
        self._last_byte: int | None = None
        """Last byte received. Before `_synced`, `wait_for_input_request` treats an 'A' followed
        by `quiet_sec` of silence as firmware readiness."""

    @override
    def wait_for_input_request(self):
        """Consume readiness after dequeueing input, immediately before sending."""
        if self._synced:
            # Steady state: the marker directly follows the previous result.
            while self._read_result(None) != READY_BYTE:
                pass
            return
        timeout, self.serial.timeout = self.serial.timeout, self.quiet_sec
        try:
            while True:
                data = self.serial.read(256)
                if data:
                    self._last_byte = data[-1]
                elif self._last_byte == READY_BYTE:
                    self._synced = True
                    return
        finally:
            self.serial.timeout = timeout

    def _read_result(self, deadline: float | None) -> int | None:
        """Return the next result byte, or the marker; None on silence past the deadline."""
        # ponytail: unframed; noise starting with 0/0xFF needs a firmware protocol change.
        boot_noise = False
        while True:
            # Read before checking the deadline: a delay of this process must not turn an answer
            # that is already buffered into silence.
            ret = self.serial.read(1)
            if not ret:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            self._last_byte = ret[0]
            if ret[0] == READY_BYTE or (not boot_noise and ret[0] in ParserResult):
                return ret[0]
            # Once boot noise starts, even 0/0xFF are noise until the ready marker.
            boot_noise = True
            log.debug("Skip boot byte %r", ret)

    @override
    def send_input(self, input: bytes) -> bool:
        log.debug(f"Sending input: {input}")
        packet = LENGTH_PREFIX.pack(len(input)) + input
        transfer = len(packet) * UART_BITS_PER_BYTE / self.serial.baudrate

        self.serial.write(packet)
        self.serial.flush()
        # Tracing can hold the parser at a breakpoint for much longer than any timeout.
        result = self._read_result(None)
        while result == READY_BYTE:
            self._synced = False
            # The firmware restarted. If it still received the packet, the result follows; only
            # silence means the packet was lost.
            result = self._read_result(time.monotonic() + self.grace_sec + transfer)
            if result is None:
                self.serial.write(packet)
                self.serial.flush()
                result = self._read_result(None)
        return result == ParserResult.ACCEPTED

    @override
    def disconnect(self):
        self.serial.close()
