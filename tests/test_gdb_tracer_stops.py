from unittest.mock import Mock, patch

import pytest

from tracer.gdb_tracer import GDBTracer
from tracer.instance.sut_instance import SUTInstance

CONFIG = {
    "GDB": {
        "entrypoint": "parser",
        "watchpoint_type": "(char*)",
        "input_buffer": "buf",
        "watchpoint_count": 1,
        "ignore_functions_regex": "^iscntrl_$",
    }
}
PARSER = {"addr": "0x10", "func": "parser", "args": []}
IGNORED = {"addr": "0x109253", "func": "iscntrl_", "args": []}
ENTRY = {
    "type": "notify",
    "message": "stopped",
    "payload": {"reason": "breakpoint-hit", "bkptno": "1", "frame": PARSER},
}
STACK = {
    "type": "result",
    "message": "done",
    "payload": {"stack": [PARSER, {"addr": "0x20", "func": "main"}]},
}


def stop(frame: dict, reason: str = "") -> dict:
    payload = {"frame": frame, "thread-id": "1", "stopped-threads": "all"}
    if reason:
        payload["reason"] = reason
    return {"type": "notify", "message": "stopped", "payload": payload}


class Done(Exception):
    pass


def trace(*batches: list[dict]) -> Mock:
    instance = Mock(timeout=1)
    instance.set_temporary_breakpoint.return_value = "1"
    instance.wait_for_any_stop_message.return_value = ENTRY
    instance.set_watchpoint_and_get_id.return_value = "2"
    instance.is_stack_message.side_effect = lambda r: SUTInstance.is_stack_message(instance, r)
    instance.is_stop_message.side_effect = lambda r: SUTInstance.is_stop_message(instance, r)
    instance.get_gdb_responses.side_effect = [*batches, Done()]
    with patch("tracer.gdb_tracer.time.sleep"), pytest.raises(Done):
        GDBTracer(CONFIG).trace_input_slice(instance, 1)
    return instance


def test_accepts_valgrind_finish_without_reason():
    # Valgrind's gdbserver completes -exec-finish with no stop reason.
    instance = trace([STACK], [stop(IGNORED, "end-stepping-range")], [stop(IGNORED)])

    instance.step_out_of_function.assert_called_once()
    assert instance.request_stacktrace.call_count == 2


def test_rejects_reasonless_stop_after_step():
    with pytest.raises(RuntimeError, match="Unexpected trace stop"):
        trace([STACK], [stop(IGNORED)])


# A named caller, and a namespaced entry whose caller frame has no name:
# trace entries normalise "percent::decode", GDB frames do not.
@pytest.mark.parametrize(
    "function, caller",
    [
        ("parser", {"addr": "0x20", "func": "caller"}),
        ("percent::decode", {"addr": "0x20"}),
    ],
)
def test_truncated_unwind_is_not_parser_return(function, caller):
    class FakeInstance:
        timeout = 1

        def request_stacktrace(self):
            pass

        def step_instruction(self):
            pass

        def delete_breakpoint(self, _):
            pass

        def continue_execution(self):
            pass

        def get_gdb_responses(self):
            return []

        def is_stack_message(self, response):
            return response.get("message") == "done" and "stack" in response.get("payload", {})

        def is_stop_message(self, response):
            return response.get("message") == "stopped"

    tracer = GDBTracer(CONFIG)
    instance = FakeInstance()
    entry_stop = {
        "type": "notify",
        "message": "stopped",
        "payload": {
            "reason": "breakpoint-hit",
            "bkptno": "1",
            "frame": {"addr": "0x10", "func": function, "args": []},
        },
    }
    instance.get_gdb_responses = Mock(
        side_effect=[
            [
                {
                    "type": "result",
                    "message": "done",
                    "payload": {
                        "stack": [
                            {"addr": "0x10", "func": function},
                            caller,
                            {"addr": "0x30", "func": "root"},
                        ]
                    },
                }
            ],
            [
                {
                    "type": "result",
                    "message": "done",
                    "payload": {
                        "stack": [
                            {"addr": "0x12", "func": function},
                            {"addr": "0x30", "func": "root"},
                        ]
                    },
                }
            ],
        ]
    )
    instance.wait_for_any_stop_message = Mock(return_value=entry_stop)
    instance.set_temporary_breakpoint = Mock(return_value="1")
    instance.set_watchpoint_and_get_id = Mock(return_value="c3-read-0")
    instance.continue_execution = Mock()
    instance.send_input = Mock()
    with patch("tracer.gdb_tracer.time.sleep"), pytest.raises(RuntimeError):
        tracer.trace_input_slice(instance, 1, 0)
