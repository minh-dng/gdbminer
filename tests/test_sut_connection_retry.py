import queue
from unittest.mock import Mock, patch

import pytest

from tracer.connection.sut_connection import SUTConnection


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
