"""Check that queued input is available before consuming target readiness."""

import unittest
from unittest.mock import Mock

from tracer.connection.connection_base_class import ConnectionBaseClass


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


if __name__ == "__main__":
    unittest.main()
