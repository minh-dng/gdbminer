"""Host-side contract checks; live hardware evidence is still required."""

import json
import signal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import pytest

from tracer.instance import HARDWARE_TRIGGER_COUNT, ESP32C3Instance
from tracer.instance.esp32c3_debug import (
    DCSR_CAUSE_OFFSET,
    MCONTROL_ACCESS_MASK,
    MCONTROL_CONTROL_MASK,
    DCSRCause,
    DCSRMask,
    MControlFlag,
)
from tracer.instance.esp32c3_instance import _ReadTrigger


def configuration():
    return {
        "BASIC": {"binary_file": "unused.elf"},
        "GDB": {
            "instance": "esp32c3",
            "timeout": 1,
            "gdb_path": "gdb",
            "gdb_server_path": "openocd",
            "gdb_server_address": ":3334",
            "watchpoint_count": 1,
            "esp32c3": {"hardware_trigger_slot": 0},
            "exitpoint": "",
            "entrypoint": "parser",
            "watchpoint_type": "(char*)",
            "input_buffer": "buf",
        },
        "Connection": {},
    }


class TestHardwareContract:
    def test_debug_values_match_openocd_rv32_encodings(self):
        # Independent reference values catch reordered auto() members and bad bit offsets.
        assert {cause.name: cause.value for cause in DCSRCause} == {
            "EBREAK": 1,
            "TRIGGER": 2,
            "HALTREQ": 3,
            "STEP": 4,
            "RESETHALTREQ": 5,
            "GROUP": 6,
            "OTHER": 7,
        }
        assert {flag.name: flag.value for flag in MControlFlag} == {
            "LOAD": 0x1,
            "STORE": 0x2,
            "EXECUTE": 0x4,
            "M": 0x40,
            "ACTION_DEBUG_MODE": 0x1000,
            "HIT": 0x100000,
            "DMODE": 0x8000000,
            "TYPE_MCONTROL": 0x20000000,
        }
        assert ESP32C3Instance._MCONTROL == 0x28001041
        assert MCONTROL_ACCESS_MASK == 0x7
        assert MCONTROL_CONTROL_MASK == 0xF81FFFFF
        assert DCSRMask.CAUSE == 0x1C0
        assert DCSRMask.STEPIE == 0x800
        assert DCSR_CAUSE_OFFSET == 6
        assert HARDWARE_TRIGGER_COUNT == 8

    def test_missing_rom_elf_cleans_up_started_resources(self):
        with TemporaryDirectory() as directory:
            config = configuration()
            config["GDB"]["esp32c3"]["rom_elf"] = str(Path(directory) / "missing.elf")
            instance = ESP32C3Instance(config, "unused")
            instance.gdb_controller = Mock()
            connection, server = Mock(), Mock()
            with (
                patch.object(instance, "init_sut_connection", return_value=connection),
                patch.object(
                    instance,
                    "_start_gdb_server",
                    side_effect=lambda: setattr(instance, "gdb_server", server),
                ),
                patch("tracer.instance.sut_instance.SUTInstance.init_gdb_controller"),
                pytest.raises(FileNotFoundError),
            ):
                instance.__enter__()
            connection.disconnect.assert_called_once_with()
            instance.gdb_controller.exit.assert_called_once_with()
            server.terminate.assert_called_once_with()
            server.wait.assert_called_once_with(timeout=5)

    def test_rom_symbols_are_added_alongside_firmware_symbols(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance._command = Mock()
        with TemporaryDirectory() as directory:
            rom = Path(directory) / "ROM symbols.elf"
            rom.touch()
            instance.config["GDB"]["esp32c3"]["rom_elf"] = str(rom)
            with patch("tracer.instance.sut_instance.SUTInstance.init_gdb_controller") as firmware:
                instance.init_gdb_controller()
            firmware.assert_called_once_with()
            command = "add-symbol-file " + json.dumps(str(rom.resolve()))
            instance._command.assert_called_once_with(
                f"-interpreter-exec console {json.dumps(command)}"
            )

    def test_reconnect_reset_resumes_the_target(self):
        instance = ESP32C3Instance(configuration(), "unused")
        target = Mock()
        instance.reset = target.reset
        instance.continue_execution = target.continue_execution
        with patch("tracer.instance.esp32c3_instance.SUTConnection") as connection:
            instance.init_sut_connection()
        reset_on_reconnect = connection.call_args.args[1]
        reset_on_reconnect()
        assert target.mock_calls == [call.reset(), call.continue_execution()]

    def test_reset_interrupts_a_running_target_without_triggers(self):
        # Synchronous MI reads no command while the target runs, so SIGINT stops it.
        instance = ESP32C3Instance(configuration(), "unused")
        instance.gdb_controller = Mock()
        instance._command = Mock(return_value=({"message": "done"}, ""))
        instance._monitor = Mock()
        instance._wait_stop = Mock()
        instance._halted = False  # Running after continue_execution().
        instance.reset()
        instance.gdb_controller.gdb_process.send_signal.assert_called_once_with(signal.SIGINT)
        instance._wait_stop.assert_called_once_with()
        instance._monitor.assert_called_once_with("reset halt")
        assert call("-exec-interrupt") not in instance._command.call_args_list

    def hardware(self, count=1, first_slot=0):
        config = configuration()
        config["GDB"]["watchpoint_count"] = count
        config["GDB"]["esp32c3"]["hardware_trigger_slot"] = first_slot
        instance = ESP32C3Instance(config, "unused")
        instance._triggers = {
            f"c3-read-{first_slot + offset}": _ReadTrigger(
                first_slot + offset, 0x100 + offset, offset, 0, 0
            )
            for offset in range(count)
        }
        instance._halted = True
        instance._pc = "0x20"
        instance._set_triggers = Mock()
        return instance

    @staticmethod
    def registers(count=1, hits=(), disabled=(), cause=4, first_slot=0):
        return (
            {
                first_slot + i: (
                    0
                    if i in disabled
                    else ESP32C3Instance._MCONTROL | (MControlFlag.HIT if i in hits else 0),
                    0x100 + i,
                )
                for i in range(count)
            },
            cause << 6,
        )

    @staticmethod
    def stop(pc):
        return {
            "type": "notify",
            "message": "stopped",
            "payload": {"reason": "end-stepping-range", "frame": {"addr": pc}},
        }

    def test_raw_stop_is_withheld_and_hit_precedes_one_successor(self):
        instance = self.hardware()
        instance._read_registers = Mock(
            side_effect=[
                self.registers(hits=[0], cause=2),
                self.registers(disabled=[0]),
            ]
        )
        successor = self.stop("0x22")  # A compressed instruction is legal.
        instance._step_stop = Mock(side_effect=[self.stop("0x20"), successor])
        instance.step_instruction()
        assert len(instance._pending) == 2
        assert instance._pending[0]["payload"] == {
            "reason": "read-watchpoint-trigger",
            "offset": 0,
        }
        assert instance._pending[1] == successor
        triggers = list(instance._triggers.values())
        assert instance._set_triggers.call_args_list == [
            ((triggers, False),),
            ((triggers, True),),
        ]

    def test_ordinary_step_and_same_pc_branch_have_no_hit(self):
        instance = self.hardware()
        instance._read_registers = Mock(return_value=self.registers())
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        instance.step_instruction()
        assert instance._pending == [self.stop("0x20")]
        instance._set_triggers.assert_not_called()

    def test_step_onto_exit_breakpoint_is_passed_to_tracer(self):
        instance = self.hardware()
        exit_hit = {
            "type": "notify",
            "message": "stopped",
            "payload": {"reason": "breakpoint-hit", "bkptno": "2", "frame": {"addr": "0x22"}},
        }
        instance._command = Mock(return_value=({"message": "running"}, ""))

        def wait_stop():
            instance._halted = True
            return exit_hit

        instance._wait_stop = Mock(side_effect=wait_stop)
        instance._read_registers = Mock(return_value=self.registers(cause=2))
        instance.step_instruction()
        assert instance._pending == [exit_hit]
        instance._set_triggers.assert_not_called()

    @pytest.mark.parametrize("cause, hit", [(4, True), (2, False), (3, False), (0, False)])
    def test_stale_hit_and_unexplained_halt_fail_closed(self, cause, hit):
        instance = self.hardware()
        instance._read_registers = Mock(
            side_effect=[self.registers(hits=[0] if hit else [], cause=cause)]
        )
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        with pytest.raises(RuntimeError):
            instance.step_instruction()
        assert instance._pending == []

    def test_failed_recovery_does_not_emit_success(self):
        instance = self.hardware()
        instance._read_registers = Mock(
            side_effect=[
                self.registers(hits=[0], cause=2),
                self.registers(disabled=[0], cause=2),
            ]
        )
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        with pytest.raises(RuntimeError):
            instance.step_instruction()
        assert instance._pending == []

    def test_transactions_keep_unrelated_results_and_stops(self):
        instance = ESP32C3Instance(configuration(), "unused")
        other = {"type": "result", "token": 99, "message": "done", "payload": {"stack": []}}
        stop = self.stop("0x20")
        result = {"type": "result", "token": 10001, "message": "done", "payload": None}
        instance.gdb_controller = Mock()
        instance.gdb_controller.get_gdb_response.side_effect = [
            [other, {"type": "console", "payload": "dcsr (/32): 0x100\n"}, stop],
            [result],
        ]
        assert instance._command("-test") == (result, "dcsr (/32): 0x100\n")
        assert instance._pending == [other, stop]

    def test_command_error_and_timeout_are_not_success(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance.gdb_controller = Mock()
        instance.gdb_controller.get_gdb_response.return_value = [
            {"type": "result", "token": 10001, "message": "error", "payload": {"msg": "bad CSR"}}
        ]
        with pytest.raises(RuntimeError):
            instance._command("-test")
        instance.timeout = 0
        with pytest.raises(TimeoutError):
            instance._command("-test")

    @pytest.mark.parametrize("count, start", [(0, 0), (9, 0), (8, 1), (1, -1)])
    def test_invalid_slot_budget_is_rejected(self, count, start):
        config = configuration()
        config["GDB"]["watchpoint_count"] = count
        config["GDB"]["esp32c3"]["hardware_trigger_slot"] = start
        with pytest.raises(ValueError):
            ESP32C3Instance(config, "unused")

    def test_failed_trigger_init_still_disables_slot(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance._halted = True
        instance._triggers = {"c3-read-0": _ReadTrigger(0, 0x100, 0, 0, 0)}
        # Partial init left an unexpected active trigger; cleanup must still disable it.
        instance._read_registers = Mock(return_value=({0: (0, 0)}, 0))
        instance._monitor = Mock()
        instance.delete_breakpoint("c3-read-0")
        assert instance._triggers == {}
        assert "tdata1 0" in instance._monitor.call_args_list[0][0][0]

    @pytest.mark.parametrize("hit", [False, True])
    def test_armed_trigger_is_validated_before_cleanup(self, hit):
        instance = self.hardware()
        instance._triggers["c3-read-0"].arm_validated = True
        instance._read_registers = Mock(return_value=self.registers(hits=[0] if hit else []))
        instance._release_slot = Mock()
        instance.delete_breakpoint("c3-read-0")
        instance._release_slot.assert_called_once_with("c3-read-0")

    def test_all_eight_matches_precede_one_successor(self):
        instance = self.hardware(8)
        instance._read_registers = Mock(
            side_effect=[
                self.registers(8, hits=range(8), cause=2),
                self.registers(8, disabled=range(8)),
            ]
        )
        successor = self.stop("0x24")
        instance._step_stop = Mock(side_effect=[self.stop("0x20"), successor])
        instance.step_instruction()
        assert [r["payload"]["offset"] for r in instance._pending[:-1]] == list(range(8))
        assert instance._pending[-1] == successor
        assert instance._step_stop.call_count == 2

    def test_priority_matches_are_replayed_without_losing_offsets(self):
        instance = self.hardware(8)
        instance._read_registers = Mock(
            side_effect=[
                self.registers(8, hits=[7], cause=2),
                self.registers(8, hits=[0, 2], disabled=[7], cause=2),
                self.registers(8, disabled=[0, 2, 7]),
            ]
        )
        instance._step_stop = Mock(
            side_effect=[self.stop("0x20"), self.stop("0x20"), self.stop("0x24")]
        )
        instance.step_instruction()
        assert [r["payload"]["offset"] for r in instance._pending[:-1]] == [0, 2, 7]
        calls = instance._set_triggers.call_args_list
        assert [t.slot for t in calls[0].args[0]] == [7]
        assert [t.slot for t in calls[1].args[0]] == [0, 2]
        assert calls[-1].args[1]

    def test_offset_is_not_hardware_slot_and_repeated_reads_are_preserved(self):
        instance = self.hardware(1, first_slot=7)
        states = [
            self.registers(hits=[0], cause=2, first_slot=7),
            self.registers(disabled=[0], first_slot=7),
        ]
        instance._read_registers = Mock(side_effect=states * 2)
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        instance.step_instruction()
        instance.step_instruction()
        assert [r["payload"].get("offset") for r in instance._pending] == [0, None, 0, None]

    def finishing(self, stop, registers):
        instance = self.hardware(7, first_slot=1)
        instance._command = Mock(return_value=({"message": "running"}, ""))

        def wait_stop():
            instance._halted = True  # As the real _wait_stop does.
            return stop

        instance._wait_stop = Mock(side_effect=wait_stop)
        instance._read_registers = Mock(side_effect=registers)
        return instance

    def test_finish_returns_function_finished_stop(self):
        stop = {"type": "notify", "message": "stopped", "payload": {"reason": "function-finished"}}
        instance = self.finishing(stop, [self.registers(7, first_slot=1)])
        instance.step_out_of_function()
        instance._command.assert_called_once_with("-exec-finish")
        assert instance._pending == [stop]

    def test_read_during_finish_is_retired_without_a_record(self):
        # A skipped function (e.g. strlen) reads a watched byte: the trigger
        # halts before the load. As in the STM32 reference traces, the read is
        # not recorded; the load is retired and skipping continues.
        trap = {"type": "notify", "message": "stopped", "payload": {"reason": "signal-received"}}
        instance = self.finishing(
            trap,
            [
                self.registers(7, hits=[3], cause=2, first_slot=1),
                self.registers(7, hits=[3], cause=2, first_slot=1),
                self.registers(7, disabled=[3], first_slot=1),
            ],
        )
        successor = self.stop("0x24")
        instance._step_stop = Mock(side_effect=[self.stop("0x20"), successor])
        instance.step_out_of_function()
        assert instance._pending == [successor]
        instance._set_triggers.assert_called()  # Disabled for the load, then re-armed.

    def test_finish_read_hit_without_trigger_cause_fails_closed(self):
        stop = {"type": "notify", "message": "stopped", "payload": {"reason": "function-finished"}}
        instance = self.finishing(stop, [self.registers(7, hits=[3], cause=4, first_slot=1)])
        instance._step = Mock()
        with pytest.raises(RuntimeError, match="Unexplained C3 finish stop"):
            instance.step_out_of_function()
        instance._step.assert_not_called()

    def test_unlabelled_rom_finish_is_the_return_breakpoint(self):
        # GDB omits the reason when the finished function has no DWARF.
        stop = {"type": "notify", "message": "stopped", "payload": {"frame": {"func": "caller"}}}
        instance = self.finishing(stop, [self.registers(7, cause=2, first_slot=1)])
        instance.step_out_of_function()
        assert instance._pending == [stop]
        assert "reason" not in stop["payload"]  # The GDB record is passed on unchanged.

    def test_finish_onto_exit_breakpoint_is_passed_to_tracer(self):
        stop = {
            "type": "notify",
            "message": "stopped",
            "payload": {"reason": "breakpoint-hit", "bkptno": "2", "frame": {"addr": "0x30"}},
        }
        instance = self.finishing(stop, [self.registers(7, cause=2, first_slot=1)])
        instance.step_out_of_function()
        assert instance._pending == [stop]

    @pytest.mark.parametrize(
        "stop, cause",
        [
            ({"type": "notify", "message": "stopped", "payload": {"reason": "signal-received"}}, 2),
            ({"type": "notify", "message": "stopped", "payload": {"frame": {"func": "f"}}}, 3),
            ({"type": "notify", "message": "stopped", "payload": {"reason": "breakpoint-hit"}}, 4),
            (
                {
                    "type": "notify",
                    "message": "stopped",
                    "payload": {"frame": {"func": "_Unwind_DebugHook"}},
                },
                2,
            ),
        ],
    )
    def test_unexplained_finish_stop_fails_closed(self, stop, cause):
        instance = self.finishing(stop, [self.registers(7, cause=cause, first_slot=1)])
        with pytest.raises(RuntimeError):
            instance.step_out_of_function()
        assert instance._pending == []

    def test_all_eight_slots_remain_available_until_parser_entry(self):
        config = configuration()
        config["GDB"]["watchpoint_count"] = 8
        config["GDB"]["esp32c3"]["breakpoint_always_inserted"] = True
        instance = ESP32C3Instance(config, "unused")
        reserved = set()

        def monitor(command):
            for slot in range(8):
                if f"riscv reserve_trigger {slot} on" in command:
                    reserved.add(slot)

        def command(command):
            if command.startswith("-break-insert"):
                if len(reserved) == 8:
                    raise RuntimeError("No slot for the entry breakpoint")
                return {"payload": {"bkpt": {"number": "1"}}}, ""
            return {"payload": {"value": "256"}}, ""

        instance._monitor = Mock(side_effect=monitor)
        instance._command = Mock(side_effect=command)
        instance._read_registers = Mock(return_value=({0: (0, 0)}, 0))
        instance._set_triggers = Mock()
        with (
            patch.object(instance, "init_sut_connection"),
            patch.object(instance, "_start_gdb_server"),
            patch.object(instance, "init_gdb_controller"),
            patch.object(instance, "wait_for_any_stop_message"),
            patch.object(instance, "reset"),
        ):
            instance.__enter__()
        instance._monitor.assert_not_called()
        assert instance.set_temporary_breakpoint("parser") == "1"
        instance._halted = True  # The temporary entry breakpoint has been consumed.
        instance.set_watchpoint_and_get_id("&buf[0]", "(char*)")
        assert reserved == set(range(8))
        assert instance._monitor.call_args_list[0].args[0] == "; ".join(
            f"riscv reserve_trigger {slot} on" for slot in range(8)
        )
        assert (
            instance._monitor.call_args_list[1].args[0]
            == "reg tselect 0; reg tdata1 0; reg tdata2 0x100"
        )
        instance._command.assert_any_call("-gdb-set breakpoint always-inserted on")

    def test_cleanup_attempts_every_slot_even_after_a_failure(self):
        instance = self.hardware(8)
        instance.delete_breakpoint = Mock(side_effect=[RuntimeError("slot 0 changed"), *[None] * 7])
        with pytest.raises(ExceptionGroup):
            instance._clear_triggers()
        assert instance.delete_breakpoint.call_count == 8

    def test_active_foreign_slot_is_not_overwritten(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance._halted = True
        instance._command = Mock(return_value=({"payload": {"value": "256"}}, ""))
        instance._read_registers = Mock(return_value=({0: (4, 0x200)}, 0))
        instance._monitor = Mock()
        with pytest.raises(RuntimeError):
            instance.set_watchpoint_and_get_id("&buf[0]", "(char*)")
        instance._monitor.assert_not_called()
        assert instance._triggers == {}

    def test_batched_registers_check_each_selected_slot(self):
        instance = self.hardware(2)
        text = ""
        for slot in [0, 1]:
            text += (
                f"tselect (/32): {slot:#x}\ntselect (/32): {slot:#x}\n"
                f"tdata1 (/32): {instance._MCONTROL:#x}\ntdata2 (/32): {0x100 + slot:#x}\n"
            )
        text += "dcsr (/32): 0x100\n"
        instance._monitor = Mock(return_value=text)
        assert instance._read_registers([0, 1]) == self.registers(2)
        instance._monitor.return_value = text.replace("tselect (/32): 0x1", "tselect (/32): 0x0")
        with pytest.raises(RuntimeError):
            instance._read_registers([0, 1])
