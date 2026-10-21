"""Check that queued input is available before consuming target readiness."""

import pickle
import unittest
from unittest.mock import Mock

import serial

from tracer.connection import ConnectionBaseClass


class ConnectionOrderTests(unittest.TestCase):
    def test_readiness_is_checked_after_dequeue_and_before_send(self):
        connection = ConnectionBaseClass.__new__(ConnectionBaseClass)
        events = []
        connection.config = {}
        connection.running = True
        connection.connect = Mock()
        connection.ready = Mock()
        connection.inputs = Mock()
        connection.inputs.get.side_effect = lambda **_: events.append("dequeue") or b"{}"
        connection.wait_for_input_request = Mock(side_effect=lambda: events.append("ready"))

        def send(data):
            self.assertEqual(data, b"{}")
            events.append("send")
            connection.running = False
            return True

        connection.send_input = Mock(side_effect=send)
        connection.response = Mock()
        connection.run()

        self.assertEqual(events, ["dequeue", "ready", "send"])
        connection.ready.put.assert_called_once_with(True)
        connection.response.put.assert_called_once_with(True)

    def test_send_error_reaches_the_response_queue(self):
        connection = ConnectionBaseClass.__new__(ConnectionBaseClass)
        connection.config = {}
        connection.running = True
        connection.connect = Mock()
        connection.ready = Mock()
        connection.inputs = Mock()
        connection.inputs.get.return_value = b"{}"
        connection.wait_for_input_request = Mock()
        # PySerial's error cannot be rebuilt from its pickle; the queue pickles every message.
        connection.send_input = Mock(side_effect=serial.PortNotOpenError())
        connection.response = Mock()

        with self.assertRaises(serial.PortNotOpenError):
            connection.run()

        (message,), _ = connection.response.put.call_args
        self.assertIn("PortNotOpenError", str(pickle.loads(pickle.dumps(message))))


if __name__ == "__main__":
    unittest.main()
