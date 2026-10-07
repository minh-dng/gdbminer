import struct
from unittest.mock import Mock, patch

from tracer.connection.esp32_serial_connection import ESP32UARTConnection
from tracer.connection.sut_connection import READY_BYTE

READY = bytes([READY_BYTE])


def connection(bulk, single):
    """bulk: chunks for the readiness drain (read(256)); single: bytes for read(1)."""
    conn = ESP32UARTConnection.__new__(ESP32UARTConnection)
    conn.serial = Mock(baudrate=9600, timeout=2)
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

    conn = connection([READY, b""], [READY, b"\x00"])
    conn.grace_sec = 0.7
    with (
        patch.object(conn, "_read_result", side_effect=[READY_BYTE, 0]) as read,
        patch("tracer.connection.esp32_serial_connection.time.monotonic", return_value=10),
    ):
        assert exchange(conn, b"abc")
    assert read.call_args_list[-1].args[0] == 10 + 0.7 + len(packet(b"abc")) * 10 / 9600


def test_sends_only_after_the_latest_marker_and_a_quiet_line():
    # Marker from the EN-pulse boot, then OpenOCD's reset: noise, new marker.
    conn = connection([READY + b"\x12\x9c", READY, b""], [b"\x00"])
    assert exchange(conn, b"{}")
    assert conn.serial.write.call_args_list == [((packet(b"{}"),),)]


def test_result_bytes_in_boot_noise_are_not_parser_results():
    # Captured UART boot prefix: the embedded 0x00 caused a false acceptance.
    noise = bytes.fromhex("0cbcf588eddd4eef2e00") + b"\xff\x8d"
    conn = connection([READY, b""], [bytes([byte]) for byte in noise] + [READY, b"\xff"])
    assert not exchange(conn, b"?")
    assert conn.serial.write.call_args_list == [((packet(b"?"),),)]


def test_marker_then_result_is_not_resent():
    # The packet arrived after the reboot set up the UART: it is answered.
    conn = connection([READY, b""], [READY, b"\x00"])
    assert exchange(conn, b"abc")
    assert conn.serial.write.call_args_list == [((packet(b"abc"),),)]


def test_marker_then_silence_resends_once():
    # The packet was lost in the reboot: no result follows the marker.
    conn = connection([READY, b""], [READY, *[b""] * 5, b"\xff"])
    clock = iter(range(100))
    with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
        assert not exchange(conn, b"abc")
    assert conn.serial.write.call_args_list == [((packet(b"abc"),),)] * 2


def test_buffered_result_after_a_host_delay_is_not_resent():
    # This process stalls past the grace deadline; the answer is already buffered.
    conn = connection([READY, b""], [READY, b"\x00"])
    clock = iter([0, 100])
    with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
        assert exchange(conn, b"abc")
    assert conn.serial.write.call_args_list == [((packet(b"abc"),),)]


def test_steady_state_takes_the_marker_after_each_result():
    conn = connection([READY, b""], [b"\x00", READY, b"\xff"])
    assert exchange(conn, b"[]")
    assert not exchange(conn, b"[")
    assert conn.serial.read.call_args_list[-2:] == [((1,),), ((1,),)]


def test_firmware_rejection_keeps_the_next_packet_aligned():
    oversized = b"a" * 2049
    conn = connection([READY, b""], [b"\xff", READY, b"\x00"])
    assert not exchange(conn, oversized)
    assert exchange(conn, b"ab")
    assert conn.serial.write.call_args_list == [
        ((packet(oversized),),),
        ((packet(b"ab"),),),
    ]
