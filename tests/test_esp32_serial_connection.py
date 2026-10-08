import struct
from unittest.mock import Mock, call, patch

import pytest

from tracer.connection import (
    READY_BYTE,
    ESP32SerialConnection,
    ESP32UARTConnection,
    ESP32USBSerialJTAGConnection,
)

READY = bytes([READY_BYTE])


def connection(bulk, single, cls: type[ESP32SerialConnection] = ESP32UARTConnection):
    """bulk: chunks for the readiness drain (read(256)); single: bytes for read(1)."""
    conn = cls.__new__(cls)
    conn.serial = Mock(baudrate=9600, timeout=2)
    conn.write_gap_sec = 0.0  # Unpaced; the pacing tests set their own gap.
    conn._synced = False
    conn._last_byte = None
    conn.quiet_sec, conn.grace_sec = 0.2, 1.0
    bulk, single = list(bulk), list(single)
    conn.serial.read.side_effect = lambda n: (
        (bulk if n > 1 else single).pop(0) if (bulk if n > 1 else single) else b""
    )
    return conn


def exchange(conn, data: bytes) -> bool:
    """Follow the shared loop: consume readiness once, then send the packet."""
    conn.wait_for_input_request()
    return conn.send_input(data)


def packet(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def sent(conn) -> bytes:
    """Bytes written, joined across the chunks of each packet."""
    return b"".join(write.args[0] for write in conn.serial.write.call_args_list)


PORTS = pytest.mark.parametrize("cls", [ESP32UARTConnection, ESP32USBSerialJTAGConnection])
"""The exchange scenarios hold for both input ports."""


def test_connect_sets_control_lines_before_open_and_only_waits_for_reset_pulse():
    config = {"Connection": {"port": "/dev/test", "baud_rate": 9600}}
    conn = ESP32UARTConnection.__new__(ESP32UARTConnection)
    port = Mock()
    opened = []
    port.open.side_effect = lambda: opened.append((port.port, port.baudrate, port.dtr, port.rts))
    with (
        patch(
            "tracer.connection.esp32_serial_connection.serial.Serial", return_value=port
        ) as serial_class,
        patch("tracer.connection.esp32_serial_connection.time.sleep") as sleep,
    ):
        conn.connect(config)
    serial_class.assert_called_once_with(timeout=2)
    assert opened == [("/dev/test", 9600, False, True)]
    assert not port.rts
    assert not conn._synced
    sleep.assert_called_once_with(0.05)


def test_configured_timings_are_used():
    conn = ESP32UARTConnection.__new__(ESP32UARTConnection)
    config = {
        "Connection": {
            "port": "/dev/test",
            "baud_rate": 9600,
            "quiet_sec": 0.3,
            "grace_sec": 0.7,
            "reset_pulse_sec": 0.1,
        }
    }
    with (
        patch("tracer.connection.esp32_serial_connection.serial.Serial"),
        patch("tracer.connection.esp32_serial_connection.time.sleep") as sleep,
    ):
        conn.connect(config)
    sleep.assert_called_once_with(0.1)
    assert (conn.quiet_sec, conn.grace_sec) == (0.3, 0.7)
    conn.serial.read.side_effect = [READY, b""]
    observed = []
    conn.serial.read.side_effect = lambda _: (
        observed.append(conn.serial.timeout) or (READY if len(observed) == 1 else b"")
    )
    conn.wait_for_input_request()
    assert observed == [0.3, 0.3]


@pytest.mark.parametrize(
    ("cls", "transfer"),
    [(ESP32UARTConnection, len(packet(b"abc")) * 10 / 9600), (ESP32USBSerialJTAGConnection, 0)],
)
def test_restart_grace_adds_the_ports_transfer_time(cls, transfer):
    conn = connection([READY, b""], [], cls)
    conn.grace_sec = 0.7
    with (
        patch.object(conn, "_read_result", side_effect=[READY_BYTE, 0]) as read,
        patch("tracer.connection.esp32_serial_connection.time.monotonic", return_value=10),
    ):
        assert exchange(conn, b"abc")
    assert read.call_args_list[-1].args[0] == 10 + 0.7 + transfer


@PORTS
def test_sends_only_after_the_latest_marker_and_a_quiet_line(cls):
    # Marker from the reset-pulse boot, then OpenOCD's reset: noise, new marker.
    conn = connection([READY + b"\x12\x9c", READY, b""], [b"\x00"], cls)
    assert exchange(conn, b"{}")
    assert sent(conn) == packet(b"{}")


@PORTS
def test_result_bytes_in_boot_noise_are_not_parser_results(cls):
    # Captured UART boot prefix: the embedded 0x00 caused a false acceptance.
    noise = bytes.fromhex("0cbcf588eddd4eef2e00") + b"\xff\x8d"
    conn = connection([READY, b""], [bytes([byte]) for byte in noise] + [READY, b"\xff"], cls)
    assert not exchange(conn, b"?")
    assert sent(conn) == packet(b"?")


@PORTS
def test_marker_then_result_is_not_resent(cls):
    # The packet arrived after the reboot set up the port: it is answered.
    conn = connection([READY, b""], [READY, b"\x00"], cls)
    assert exchange(conn, b"abc")
    assert sent(conn) == packet(b"abc")


@PORTS
def test_marker_then_silence_resends_once(cls):
    # The packet was lost in the reboot: no result follows the marker.
    conn = connection([READY, b""], [READY, *[b""] * 5, b"\xff"], cls)
    clock = iter(range(100))
    with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
        assert not exchange(conn, b"abc")
    assert sent(conn) == packet(b"abc") * 2


@PORTS
def test_buffered_result_after_a_host_delay_is_not_resent(cls):
    # This process stalls past the grace deadline; the answer is already buffered.
    conn = connection([READY, b""], [READY, b"\x00"], cls)
    clock = iter([0, 100])
    with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
        assert exchange(conn, b"abc")
    assert sent(conn) == packet(b"abc")


@PORTS
def test_steady_state_takes_the_marker_after_each_result(cls):
    conn = connection([READY, b""], [b"\x00", READY, b"\xff"], cls)
    assert exchange(conn, b"[]")
    assert not exchange(conn, b"[")
    assert conn.serial.read.call_args_list[-2:] == [((1,),), ((1,),)]


@PORTS
def test_rejection_answer_keeps_the_next_packet_aligned(cls):
    # The mock supplies the firmware's answers: this checks the host's byte accounting only.
    oversized = b"a" * 2049
    conn = connection([READY, b""], [b"\xff", READY, b"\x00"], cls)
    assert not exchange(conn, oversized)
    assert exchange(conn, b"ab")
    assert sent(conn) == packet(oversized) + packet(b"ab")


@pytest.mark.parametrize(("settings", "gap"), [({}, 0.002), ({"write_gap_sec": 0.004}, 0.004)])
def test_usb_serial_jtag_connect_sets_no_baud_rate_and_reads_the_write_gap(settings, gap):
    conn = ESP32USBSerialJTAGConnection.__new__(ESP32USBSerialJTAGConnection)
    port = Mock(baudrate=None)
    opened = []
    port.open.side_effect = lambda: opened.append((port.port, port.baudrate, port.dtr, port.rts))
    with (
        patch(
            "tracer.connection.esp32_serial_connection.serial.Serial", return_value=port
        ) as serial_class,
        patch("tracer.connection.esp32_serial_connection.time.sleep"),
    ):
        conn.connect({"Connection": {"port": "/dev/test", **settings}})
    serial_class.assert_called_once_with(timeout=2)
    # The controller ignores the line coding, so the port keeps PySerial's default.
    assert opened == [("/dev/test", None, False, True)]
    assert conn.write_gap_sec == gap
    assert conn._transfer_sec(2052) == 0


@pytest.mark.parametrize(
    ("size", "chunks"),
    [(0, [4]), (60, [64]), (61, [64, 1]), (124, [64, 64]), (200, [64, 64, 64, 12])],
)
def test_usb_serial_jtag_paces_64_byte_chunks(size, chunks):
    data = bytes(range(256))[:size]
    conn = connection([READY, b""], [b"\x00"], ESP32USBSerialJTAGConnection)
    conn.write_gap_sec = 0.002
    events = Mock()
    conn.serial.write.side_effect = events.write
    conn.serial.flush.side_effect = events.flush
    with patch("tracer.connection.esp32_serial_connection.time.sleep", events.sleep):
        assert exchange(conn, data)
    expected, start = [], 0
    for index, length in enumerate(chunks):
        if index:
            expected.append(call.sleep(0.002))
        expected += [call.write(packet(data)[start : start + length]), call.flush()]
        start += length
    # One event log: each chunk is drained before the pause that follows it.
    assert events.mock_calls == expected


def test_usb_serial_jtag_resends_a_lost_multi_chunk_packet_paced():
    data = b"a" * 100
    conn = connection([READY, b""], [READY, b"", b"", b"\xff"], ESP32USBSerialJTAGConnection)
    conn.write_gap_sec = 0.002
    clock = iter([0, 0.5, 2])  # Deadline 1.0: the second empty read is past it.
    events = Mock()
    conn.serial.write.side_effect = events.write
    with (
        patch("tracer.connection.esp32_serial_connection.time.sleep", events.sleep),
        patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)),
    ):
        assert not exchange(conn, data)
    chunks = [packet(data)[:64], packet(data)[64:]]
    paced = [call.write(chunks[0]), call.sleep(0.002), call.write(chunks[1])]
    assert events.mock_calls == paced * 2
