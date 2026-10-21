import queue
from unittest.mock import Mock, patch

import pytest

from tracer.connection import SUTConnection


def test_timeout_discards_pending_input_before_retry():
    sut = SUTConnection.__new__(SUTConnection)
    sut.config = object()
    sut.timeout = 0.001
    sut.inputs = queue.Queue()
    sut.responses = queue.Queue()
    sut.ready = queue.Queue()
    sut.inputs.put(b"stale")
    sut.disconnect = Mock()

    def reconnect(config, *, reset):
        assert reset
        sut.responses.put(True)
        return object()

    sut.init_connection = reconnect
    with patch("tracer.connection.sut_connection.mp.Queue", side_effect=queue.Queue):
        assert sut.input_accepted(b"current")

    sut.disconnect.assert_called_once()
    assert sut.inputs.get_nowait() == b"current"
    with pytest.raises(queue.Empty):
        sut.inputs.get_nowait()


def test_connection_process_error_is_raised_without_a_retry():
    sut = SUTConnection.__new__(SUTConnection)
    sut.timeout = 1
    sut.inputs = queue.Queue()
    sut.responses = queue.Queue()
    sut.responses.put(RuntimeError("firmware restarted"))
    sut.disconnect = Mock()
    sut.init_connection = Mock()

    with pytest.raises(RuntimeError, match="firmware restarted"):
        sut.input_accepted(b"((1))")

    sut.disconnect.assert_not_called()
    sut.init_connection.assert_not_called()
