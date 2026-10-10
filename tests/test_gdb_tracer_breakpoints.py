"""Managed C3 stops must still pass the shared exit-breakpoint identity check."""

from unittest.mock import Mock, patch

import pytest

from tracer import GDBTracer
from tracer.instance import SUTInstance


@pytest.mark.parametrize("breakpoint", ["2", "99", None])
def test_exit_breakpoint_identity(breakpoint):
    frame = {"addr": "0x10", "func": "parser", "args": []}
    instance = Mock(timeout=1)
    instance.set_temporary_breakpoint.side_effect = ["1", "2"]
    instance.wait_for_any_stop_message.return_value = {
        "type": "notify",
        "message": "stopped",
        "payload": {"reason": "breakpoint-hit", "bkptno": "1", "frame": frame},
    }
    instance.is_stack_message.side_effect = lambda r: SUTInstance.is_stack_message(instance, r)
    instance.is_stop_message.side_effect = lambda r: SUTInstance.is_stop_message(instance, r)
    instance.get_gdb_responses.side_effect = [
        [
            {
                "type": "result",
                "message": "done",
                "payload": {
                    "stack": [frame, {"addr": "0x20", "func": "main"}],
                },
            }
        ],
        [
            {
                "type": "notify",
                "message": "stopped",
                "payload": {
                    "reason": "breakpoint-hit",
                    "bkptno": breakpoint,
                    "frame": frame,
                },
            }
        ],
    ]
    tracer = GDBTracer(
        {
            "GDB": {
                "entrypoint": "parser",
                "exitpoint": "exit",
                "input_buffer": "buf",
                "watchpoint_type": "(char*)",
                "watchpoint_count": 1,
            }
        }
    )
    with patch("tracer.gdb_tracer.time.sleep"):
        if breakpoint == "2":
            tracer.trace_input_slice(instance, 1)
            instance.delete_breakpoint.assert_called_once()
        else:
            with pytest.raises(RuntimeError, match="Unexpected exit breakpoint"):
                tracer.trace_input_slice(instance, 1)
            instance.delete_breakpoint.assert_not_called()
