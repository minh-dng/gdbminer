# Serial adapters with ESP32 boot/reset control and restart recovery.
#
# SPDX-License-Identifier: AGPL-3.0

import logging as log
import time
from abc import ABC, abstractmethod
from typing import override

import serial

from util import Config

from .connection_base_class import ConnectionBaseClass
from .sut_connection import LENGTH_PREFIX, READY_BYTE, ParserResult

UART_BITS_PER_BYTE = 10
"""Bits on the wire per byte with PySerial's default 8N1: one start, eight data, one stop bit."""

USB_PACKET_SIZE = 64
"""Largest data payload of a USB full-speed bulk packet, and of one packet that the
USB-Serial/JTAG controller accepts from the host (ESP32-C3 TRM v1.4, §30.3.1)."""


class ESP32SerialConnection(ConnectionBaseClass, ABC):
    """Request/response exchange that survives target resets between packets.

    When GDB attaches while the C3's memory protection is enabled, OpenOCD resets the core to
    disable it, after this process may already have seen the firmware's first ready marker. The
    firmware then reboots, prints boot noise and a new marker. A packet sent during the reboot can
    be lost; one that arrives after the serial port is set up is still answered. Resending on every
    marker therefore made the firmware answer one packet twice, and every later answer belonged to
    the previous query.

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

    Limits: the protocol has no framing, so the recovery assumes a restart loses a packet whole.
    If the restarted firmware receives only the rest of a packet, it reads payload bytes as the next
    length, and the answers that follow are misaligned. A restart while `_synced`, between two
    queries, is taken for readiness at the first 'A' of its boot text. GDBMiner's own resets (port
    open, OpenOCD attach, `reset` after a reconnect) all happen before the first readiness, so only
    an unplanned restart, such as a crash or a watchdog reset, meets these limits.

    Both ESP32-C3 input ports use this exchange and reset control. Subclasses, named after the
    port, define how the port is configured (`_configure`), how a packet goes on the wire (`_write`)
    and how long it may still travel afterwards (`_transfer_sec`).
    """

    @override
    def connect(self, config: Config):
        settings = config["Connection"]
        self.quiet_sec = settings.get("quiet_sec", 0.2)
        """Silence after an 'A' that marks the first readiness (`Connection.quiet_sec`)."""
        self.grace_sec = settings.get("grace_sec", 1.0)
        """Wait for a result after a restart, beyond the packet's transfer time, before the
        packet counts as lost (`Connection.grace_sec`)."""
        self.reset_pulse_sec = settings.get("reset_pulse_sec", 0.05)
        """Length of the RTS pulse that resets the chip (`Connection.reset_pulse_sec`)."""

        # Leave port unset: passing it to `Serial()` opens immediately, before we can set DTR/RTS.
        # Their default states can reset the ESP32 or select download mode.
        self.serial = serial.Serial(timeout=2)
        self.serial.port = settings["port"]
        self._configure(settings)
        # DTR/RTS drive the chip's boot/reset logic; True means asserted. Set them before `open()`,
        # with automatic flow control left disabled.
        self.serial.dtr = settings.get("dtr", False)
        self.serial.rts = settings.get("rts", True)
        self.serial.open()
        if settings.get("reset_pulse", True):
            time.sleep(self.reset_pulse_sec)
            self.serial.rts = False  # Release RTS; `send_input` waits for firmware readiness.
        log.info(f"Established connection with ESP32 SUT via Serial at {self.serial.name}")
        self._synced = False
        """The first readiness has been seen. Until then, a reset may still follow (OpenOCD can
        reset the core when GDB attaches)."""
        self._last_byte: int | None = None
        """Last byte received. Before `_synced`, `wait_for_input_request` treats an 'A' followed
        by `quiet_sec` of silence as firmware readiness."""

    @abstractmethod
    def _configure(self, settings: Config) -> None:
        """Apply the `[Connection]` settings of this port type to the closed `self.serial`.

        Called before the port opens, because opening applies the port's settings.
        """

    @abstractmethod
    def _write(self, packet: bytes) -> None:
        """Write the whole packet; return once the host has drained it (`flush`, `tcdrain`)."""

    @abstractmethod
    def _transfer_sec(self, size: int) -> float:
        """Time a packet of `size` bytes may still need to reach the firmware after `_write`."""

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
        transfer = self._transfer_sec(len(packet))

        self._write(packet)
        # Tracing can hold the parser at a breakpoint for much longer than any timeout.
        result = self._read_result(None)
        while result == READY_BYTE:
            self._synced = False
            # The firmware restarted. If it still received the packet, the result follows; silence
            # is taken as loss and the packet is sent again. A parser halted at a breakpoint is
            # silent too, so this path assumes no tracing stop after a restart.
            result = self._read_result(time.monotonic() + self.grace_sec + transfer)
            if result is None:
                self._write(packet)
                result = self._read_result(None)
        return result == ParserResult.ACCEPTED

    @override
    def disconnect(self):
        self.serial.close()


class ESP32UARTConnection(ESP32SerialConnection):
    """Inputs over UART0, through a USB-to-UART bridge such as the DevKitM-1's CP2102N.

    The bridge's RTS and DTR lines drive the board's auto-program circuit: RTS asserted with DTR
    released holds EN low and resets the chip, and the chip boots from flash once RTS is released.
    The firmware fixes the baud rate (`Serial.begin`); `Connection.baud_rate` must match it.
    """

    @override
    def _configure(self, settings: Config) -> None:
        self.serial.baudrate = settings["baud_rate"]

    @override
    def _write(self, packet: bytes) -> None:
        self.serial.write(packet)
        self.serial.flush()

    @override
    def _transfer_sec(self, size: int) -> float:
        """Wire time at the baud rate: the bridge buffers what the host sent and shifts it out."""
        return size * UART_BITS_PER_BYTE / self.serial.baudrate


class ESP32USBSerialJTAGConnection(ESP32SerialConnection):
    """Inputs over the CDC-ACM serial port of the chip's USB-Serial/JTAG controller.

    The controller is one USB device with two functions: a CDC-ACM serial port, used here for the
    inputs, and a JTAG adapter, used by OpenOCD (ESP32-C3 TRM v1.4, §30.2). Both share the one
    cable to the chip's native USB pins. The firmware selects this port by building with the
    Arduino-ESP32 option `CDCOnBoot=cdc`, which makes `Serial` the `HWCDC` driver.

    Reset: the controller maps the virtual RTS and DTR lines like the UART bridge's auto-program
    circuit. RTS asserted with DTR released resets the chip, and the chip boots from flash once RTS
    is released (TRM Tables 30.3-2 and 30.4-2), so `Connection.rts`, `dtr` and `reset_pulse` mean
    the same on both ports. The reset is a core reset (TRM Table 6.1-1, code 0x15). On the recorded
    Mac the controller kept its USB connection through it: the port stayed open and kept its name.

    No baud rate: the controller accepts and ignores the CDC line coding (TRM Table 30.3-1), and
    data moves at USB full speed. Configuration validation therefore rejects `Connection.baud_rate`
    for this port.

    Pacing: `HWCDC` copies every received USB packet from the controller into a receive
    queue of 256 bytes and drops what does not fit (Arduino-ESP32 3.3.12, `HWCDC.cpp`, the
    `USB_SERIAL_JTAG_INTR_SERIAL_OUT_RECV_PKT` handler). While the firmware runs, the handler frees
    the controller's buffer at once, so USB does not hold the host back: an input packet of more
    than 256 bytes written at once can lose bytes, and did in the json measurements. `_write`
    therefore writes 64-byte chunks, `write_gap_sec` apart, so that the wrapper's read loop can
    drain each chunk before the next arrives. This is open-loop pacing: no message from the
    firmware confirms the drain.
    """

    @override
    def _configure(self, settings: Config) -> None:
        self.write_gap_sec = settings.get("write_gap_sec", 0.002)
        """Pause between two 64-byte chunks of one packet (`Connection.write_gap_sec`).

        The C3 wrappers wait in `delay(1)`, one 1 ms FreeRTOS tick, while no byte is available. The
        2 ms default lost no byte in the recorded corpus checks, up to 2,048-byte inputs; a shorter
        gap leaves that tested range.
        """

    @override
    def _write(self, packet: bytes) -> None:
        for start in range(0, len(packet), USB_PACKET_SIZE):
            if start:
                time.sleep(self.write_gap_sec)
            self.serial.write(packet[start : start + USB_PACKET_SIZE])
            # Drain this chunk to the device before the pause starts.
            self.serial.flush()

    @override
    def _transfer_sec(self, size: int) -> float:
        """Zero: there is no line rate, and the pacing has elapsed when `_write` returns.

        `grace_sec` alone sets the deadline for a result after a restart; a read in progress can
        overrun it by the port's read timeout.
        """
        return 0.0
