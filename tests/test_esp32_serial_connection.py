import struct
import unittest
from unittest.mock import Mock, patch

from tracer.connection.esp32_serial_connection import ESP32SerialConnection

READY = b"A"


def connection(bulk, single):
    """bulk: chunks for the readiness drain (read(256)); single: bytes for read(1)."""
    conn = ESP32SerialConnection.__new__(ESP32SerialConnection)
    conn.serial = Mock(baudrate=9600, timeout=2)
    conn._synced = False
    bulk, single = list(bulk), list(single)
    conn.serial.read.side_effect = lambda n: (
        (bulk if n > 1 else single).pop(0) if (bulk if n > 1 else single) else b""
    )
    return conn


def packet(data: bytes) -> bytes:
    return struct.pack("I", len(data)) + data


class ESP32SerialConnectionTest(unittest.TestCase):
    def test_connect_sets_control_lines_before_open_and_only_waits_for_reset_pulse(self):
        config = {"Connection": {"port": "/dev/test", "baud_rate": 9600}}
        conn = ESP32SerialConnection.__new__(ESP32SerialConnection)
        port = Mock()
        opened = []
        port.open.side_effect = lambda: opened.append((port.port, port.dtr, port.rts))
        with (
            patch(
                "tracer.connection.esp32_serial_connection.serial.Serial", return_value=port
            ) as serial_class,
            patch("tracer.connection.esp32_serial_connection.time.sleep") as sleep,
        ):
            conn.connect(config)
        serial_class.assert_called_once_with(baudrate=9600, timeout=2)
        self.assertEqual(opened, [("/dev/test", False, True)])
        self.assertFalse(port.rts)
        self.assertFalse(conn._synced)
        sleep.assert_called_once_with(0.05)

    def test_sends_only_after_the_latest_marker_and_a_quiet_line(self):
        # Marker from the EN-pulse boot, then OpenOCD's reset: noise, new marker.
        conn = connection([READY + b"\x12\x9c", READY, b""], [b"\x00"])
        self.assertTrue(conn.send_input(b"{}"))
        self.assertEqual(conn.serial.write.call_args_list, [((packet(b"{}"),),)])

    def test_result_bytes_in_boot_noise_are_not_parser_results(self):
        # Captured UART boot prefix: the embedded 0x00 caused a false acceptance.
        noise = bytes.fromhex("0cbcf588eddd4eef2e00") + b"\xff\x8d"
        conn = connection([READY, b""], [bytes([byte]) for byte in noise] + [READY, b"\xff"])
        self.assertFalse(conn.send_input(b"?"))
        self.assertEqual(conn.serial.write.call_args_list, [((packet(b"?"),),)])

    def test_marker_then_result_is_not_resent(self):
        # The packet arrived after the reboot set up the UART: it is answered.
        conn = connection([READY, b""], [READY, b"\x00"])
        self.assertTrue(conn.send_input(b"abc"))
        self.assertEqual(conn.serial.write.call_args_list, [((packet(b"abc"),),)])

    def test_marker_then_silence_resends_once(self):
        # The packet was lost in the reboot: no result follows the marker.
        conn = connection([READY, b""], [READY, *[b""] * 5, b"\xff"])
        clock = iter(range(100))
        with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
            self.assertFalse(conn.send_input(b"abc"))
        self.assertEqual(conn.serial.write.call_args_list, [((packet(b"abc"),),)] * 2)

    def test_buffered_result_after_a_host_delay_is_not_resent(self):
        # This process stalls past the grace deadline; the answer is already buffered.
        conn = connection([READY, b""], [READY, b"\x00"])
        clock = iter([0, 100])
        with patch("tracer.connection.esp32_serial_connection.time.monotonic", lambda: next(clock)):
            self.assertTrue(conn.send_input(b"abc"))
        self.assertEqual(conn.serial.write.call_args_list, [((packet(b"abc"),),)])

    def test_steady_state_takes_the_marker_after_each_result(self):
        conn = connection([READY, b""], [b"\x00", READY, b"\xff"])
        self.assertTrue(conn.send_input(b"[]"))
        self.assertFalse(conn.send_input(b"["))
        self.assertEqual(conn.serial.read.call_args_list[-2:], [((1,),), ((1,),)])

    def test_firmware_rejection_keeps_the_next_packet_aligned(self):
        oversized = b"a" * 2049
        conn = connection([READY, b""], [b"\xff", READY, b"\x00"])
        self.assertFalse(conn.send_input(oversized))
        self.assertTrue(conn.send_input(b"ab"))
        self.assertEqual(
            conn.serial.write.call_args_list,
            [((packet(oversized),),), ((packet(b"ab"),),)],
        )


if __name__ == "__main__":
    unittest.main()
