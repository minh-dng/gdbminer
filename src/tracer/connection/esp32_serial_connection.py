# Serial connection adapter for ESP32 USB serial (C3 UART or S3 USB CDC).
#
# The stock SerialConnection opens the port with pyserial defaults, which
# asserts DTR/RTS and can leave the ESP32-C3-DevKitM-1 in reset/download.
# This adapter opens with DTR released and a short EN pulse so the firmware
# boots from flash and emits the configured input request marker.
#
# SPDX-License-Identifier: AGPL-3.0

import logging as log
import struct
import time
from typing import override

import serial

from tracer.connection.connection_base_class import ConnectionBaseClass


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
    def connect(self, config):
        port = config["Connection"]["port"]
        baud_rate = config["Connection"].getint("baud_rate")
        if baud_rate is None:
            raise ValueError("Config [Connection] baud_rate must be set")

        # Leave port unset: passing it to Serial() opens immediately, before we
        # can set DTR/RTS. Their default states can reset the ESP32 or select download mode.
        self.serial = serial.Serial(baudrate=baud_rate, timeout=2)
        self.serial.port = port
        # DTR (Data Terminal Ready) and RTS (Request To Send) are control lines,
        # not data bytes. On this board they drive the boot/reset circuit.
        # True means asserted, not necessarily high voltage (often active-low).
        # PySerial has no dtr/rts constructor arguments; set them before open().
        # Its default rtscts=False and dsrdtr=False disable automatic RTS/CTS
        # (Clear To Send) and DSR/DTR (Data Set Ready) flow control, respectively;
        # those flags do not set line states. Keep them disabled for manual reset.
        self.serial.dtr = config["Connection"].getboolean("dtr", fallback=False)
        self.serial.rts = config["Connection"].getboolean("rts", fallback=True)
        self.serial.open()
        if config["Connection"].getboolean("reset_pulse", fallback=True):
            time.sleep(0.05)
            self.serial.rts = False  # Release RTS to finish the reset pulse.
            time.sleep(config["Connection"].getfloat("boot_delay", fallback=0.3))
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
        while True:
            # Read before checking the deadline: a delay of this process must not
            # turn an answer that is already buffered into silence.
            ret = self.serial.read(1)
            if not ret:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            self._last_byte = ret[0]
            if ret[0] in (0, 0xFF, self.READY_BYTE):
                return ret[0]
            # Boot noise after a reset.
            log.debug("Skip non-result byte %r", ret)

    @override
    def send_input(self, input: bytes) -> bool:
        log.debug(f"Sending input: {input}")
        max_input_size = self.config["Connection"].getint("max_input_size", fallback=0)
        oversized = max_input_size > 0 and len(input) > max_input_size
        # Keep the ready/result exchange aligned while rejecting inputs the firmware cannot hold.
        wire_input = b"" if oversized else input
        packet = struct.pack("I", len(wire_input)) + wire_input
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
        return result == 0 and not oversized

    @override
    def disconnect(self):
        self.serial.close()
