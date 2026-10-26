"""Bounded OpenOCD startup checks, with no board or USB library."""

import subprocess
from unittest.mock import Mock, patch

import pytest
from test_esp32c3_hardware import configuration

from tracer.instance import ESP32C3Instance


def test_retry_waits_for_successful_init_before_gdb_attach():
    instance = ESP32C3Instance(configuration(), "unused")
    failed, ready = Mock(), Mock()
    failed.poll.return_value = 1
    ready.poll.return_value = None
    processes = iter([failed, ready])

    def spawn(command, *, stdout, stderr):
        process = next(processes)
        assert command[-2:] == [
            "-c",
            (
                'init; if {![[target current] was_examined]} {error "target examination failed"}; '
                "echo GDBMINER_C3_READY"
            ),
        ]
        stdout.write(b"device missing\n" if process is failed else b"GDBMINER_C3_READY\n")
        stdout.flush()
        return process

    with (
        patch("tracer.instance.esp32_instance.subprocess.Popen", side_effect=spawn),
        patch("tracer.instance.esp32_instance.time.sleep"),
    ):
        instance._start_gdb_server()
    failed.terminate.assert_called_once()
    failed.wait.assert_called_once_with(timeout=5)
    ready.terminate.assert_not_called()
    assert instance.gdb_server is ready


def test_hung_startup_is_killed_and_connection_closed_on_timeout():
    instance = ESP32C3Instance(configuration(), "unused")
    instance.timeout = 0.02
    instance.config["GDB"]["esp32c3"]["startup_retry_interval"] = 0.005
    server, connection = Mock(), Mock()
    server.poll.return_value = None
    server.wait.side_effect = [subprocess.TimeoutExpired("openocd", 5), None, None]
    with (
        patch.object(instance, "init_sut_connection", return_value=connection),
        patch("tracer.instance.esp32_instance.subprocess.Popen", return_value=server),
        patch.object(instance, "init_gdb_controller") as gdb,
        pytest.raises(TimeoutError, match="OpenOCD startup timed out"),
    ):
        instance.__enter__()
    server.kill.assert_called_once()
    connection.disconnect.assert_called_once()
    gdb.assert_not_called()


def test_hung_attempt_is_stopped_and_retried_within_the_window():
    """One attempt that never exits must not use the whole `GDB.timeout` (#69)."""
    instance = ESP32C3Instance(configuration(), "unused")
    instance.timeout = 5
    settings = instance.config["GDB"]["esp32c3"]
    settings["startup_retry_interval"] = 0.005
    settings["startup_attempt_timeout"] = 0.02
    hung, ready = Mock(), Mock()
    hung.poll.return_value = None
    ready.poll.return_value = None
    processes = iter([hung, ready])

    def spawn(command, *, stdout, stderr):
        process = next(processes)
        stdout.write(b"No device matches\n" if process is hung else b"GDBMINER_C3_READY\n")
        stdout.flush()
        return process

    with patch("tracer.instance.esp32_instance.subprocess.Popen", side_effect=spawn):
        instance._start_gdb_server()
    hung.terminate.assert_called_once()
    ready.terminate.assert_not_called()
    assert instance.gdb_server is ready


def test_readiness_during_the_last_poll_interval_is_accepted():
    """The attempt reads its output once more at its limit before it stops the process."""
    instance = ESP32C3Instance(configuration(), "unused")
    instance.timeout = 5
    settings = instance.config["GDB"]["esp32c3"]
    settings["startup_retry_interval"] = 0.2
    settings["startup_attempt_timeout"] = 0.1
    server = Mock()
    server.poll.return_value = None
    clock = {"now": 0.0, "ready": False}
    outputs = []

    def spawn(command, *, stdout, stderr):
        outputs.append(stdout)
        return server

    def sleep(seconds):
        # Simulated clock: OpenOCD reports readiness 0.05 s after its start, inside the limit.
        clock["now"] += seconds
        if clock["now"] >= 0.05 and not clock["ready"]:
            clock["ready"] = True
            outputs[-1].write(b"GDBMINER_C3_READY\n")
            outputs[-1].flush()

    with (
        patch("tracer.instance.esp32_instance.subprocess.Popen", side_effect=spawn) as popen,
        patch("tracer.instance.esp32_instance.time.monotonic", side_effect=lambda: clock["now"]),
        patch("tracer.instance.esp32_instance.time.sleep", side_effect=sleep),
    ):
        instance._start_gdb_server()
    popen.assert_called_once()
    server.terminate.assert_not_called()
    assert instance.gdb_server is server
