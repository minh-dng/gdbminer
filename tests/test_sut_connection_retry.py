import queue
import unittest
from unittest.mock import Mock, patch

from tracer.connection.sut_connection import SUTConnection


class SUTConnectionRetryTest(unittest.TestCase):
    def test_timeout_discards_pending_input_before_retry(self):
        sut = SUTConnection.__new__(SUTConnection)
        sut.config = object()
        sut.timeout = 0.001
        sut.inputs = queue.Queue()
        sut.responses = queue.Queue()
        sut.ready = queue.Queue()
        sut.inputs.put(b"stale")
        sut.disconnect = Mock()

        def reconnect(config, *, reset):
            self.assertTrue(reset)
            sut.responses.put(True)
            return object()

        sut.init_connection = reconnect
        with patch("tracer.connection.sut_connection.mp.Queue", side_effect=queue.Queue):
            self.assertTrue(sut.input_accepted(b"current"))

        sut.disconnect.assert_called_once()
        self.assertEqual(sut.inputs.get_nowait(), b"current")
        with self.assertRaises(queue.Empty):
            sut.inputs.get_nowait()


if __name__ == "__main__":
    unittest.main()
