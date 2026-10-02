"""Hardware-free regression check: PYTHONPATH=src python tests/test_connection_lifecycle.py."""

import queue
from unittest.mock import Mock, call, patch

from tracer.connection.sut_connection import SUTConnection
from tracer.instance.msp430_instance import MSP430Instance


def test_connection_startup():
    config = {"Connection": {"input_channel": "serial"}}
    for ready, reset_error, expected_error in (
        (queue.Empty(), None, TimeoutError),
        (False, None, ConnectionError),
        (True, RuntimeError("reset failed"), RuntimeError),
        (True, KeyboardInterrupt(), KeyboardInterrupt),
        (True, None, None),
    ):
        sut = SUTConnection.__new__(SUTConnection)
        sut.inputs = Mock()
        sut.responses = Mock()
        sut.ready = Mock()
        sut.timeout = 1
        sut.sut_reset_method = Mock(side_effect=reset_error)
        if isinstance(ready, Exception):
            sut.ready.get.side_effect = ready
        else:
            sut.ready.get.return_value = ready
        with patch("tracer.connection.sut_connection.SerialConnection") as serial:
            child = serial.return_value
            try:
                result = sut.init_connection(config, reset=True)
            except BaseException as exc:
                assert expected_error is not None and isinstance(exc, expected_error)
                assert child.mock_calls == [
                    call.start(),
                    call.terminate(),
                    call.join(),
                    call.close(),
                ]
                if isinstance(exc, TimeoutError):
                    assert isinstance(exc.__cause__, queue.Empty)
            else:
                assert expected_error is None
                assert result is child
                assert child.mock_calls == [call.start()]
            if ready is True:
                sut.sut_reset_method.assert_called_once_with()
            else:
                sut.sut_reset_method.assert_not_called()


def test_msp430_resets_after_connection():
    instance = Mock()
    with (
        patch("tracer.instance.msp430_instance.subprocess.Popen"),
        patch("tracer.instance.msp430_instance.time.sleep"),
    ):
        assert MSP430Instance.__enter__(instance) is instance
    instance.assert_has_calls(
        [call.wait_for_any_stop_message(), call.init_sut_connection(), call.reset()]
    )
    instance.reset.assert_called_once_with()


if __name__ == "__main__":
    test_connection_startup()
    test_msp430_resets_after_connection()
    print("Connection lifecycle checks passed")
