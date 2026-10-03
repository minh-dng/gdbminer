"""Host-side contract checks; live hardware evidence is still required."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from tracer.gdb_tracer import GDBTracer
from tracer.instance.esp32c3_instance import ESP32C3Instance, ReadTrigger


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


def entry(address="0x10", function="parser", hits=()):
    return GDBTracer.TraceEntry(address, function, [], ["0x20", "0x0"], list(hits))


class HardwareContractTest(unittest.TestCase):
    def test_missing_rom_elf_cleans_up_started_resources(self):
        with TemporaryDirectory() as directory:
            config = configuration()
            config["GDB"]["esp32c3"]["rom_elf"] = str(Path(directory) / "missing.elf")
            instance = ESP32C3Instance(config, "unused")
            instance.gdb_controller = Mock()
            connection, server = Mock(), Mock()
            with (
                patch.object(
                    ESP32C3Instance.__mro__[1], "init_sut_connection", return_value=connection
                ),
                patch("tracer.instance.stm32_instance.subprocess.Popen", return_value=server),
                patch("tracer.instance.stm32_instance.time.sleep"),
                patch("tracer.instance.sut_instance.SUTInstance.init_gdb_controller"),
                self.assertRaises(FileNotFoundError),
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

    def hardware(self, count=1, first_slot=0):
        config = configuration()
        config["GDB"]["watchpoint_count"] = count
        config["GDB"]["esp32c3"]["hardware_trigger_slot"] = first_slot
        instance = ESP32C3Instance(config, "unused")
        instance._triggers = {
            f"c3-read-{first_slot + offset}": ReadTrigger(
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
                    else ESP32C3Instance.MCONTROL | (ESP32C3Instance.HIT if i in hits else 0),
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
        self.assertEqual(len(instance._pending), 2)
        self.assertEqual(
            instance._pending[0]["payload"],
            {
                "reason": "read-watchpoint-trigger",
                "offset": 0,
            },
        )
        self.assertEqual(instance._pending[1], successor)
        triggers = list(instance._triggers.values())
        self.assertEqual(
            instance._set_triggers.call_args_list, [((triggers, False),), ((triggers, True),)]
        )

    def test_ordinary_step_and_same_pc_branch_have_no_hit(self):
        instance = self.hardware()
        instance._read_registers = Mock(return_value=self.registers())
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        instance.step_instruction()
        self.assertEqual(instance._pending, [self.stop("0x20")])
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
        instance._read_registers = Mock(return_value=self.registers())
        instance.step_instruction()
        self.assertEqual(instance._pending, [exit_hit])

    def test_stale_hit_and_unexplained_halt_fail_closed(self):
        for cause, hit in [(4, True), (2, False), (3, False)]:
            instance = self.hardware()
            instance._read_registers = Mock(
                side_effect=[self.registers(hits=[0] if hit else [], cause=cause)]
            )
            instance._step_stop = Mock(return_value=self.stop("0x20"))
            with self.subTest(cause=cause, hit=hit), self.assertRaises(RuntimeError):
                instance.step_instruction()
            self.assertEqual(instance._pending, [])

    def test_failed_recovery_does_not_emit_success(self):
        instance = self.hardware()
        instance._read_registers = Mock(
            side_effect=[
                self.registers(hits=[0], cause=2),
                self.registers(disabled=[0], cause=2),
            ]
        )
        instance._step_stop = Mock(return_value=self.stop("0x20"))
        with self.assertRaises(RuntimeError):
            instance.step_instruction()
        self.assertEqual(instance._pending, [])

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
        self.assertEqual(instance._command("-test"), (result, "dcsr (/32): 0x100\n"))
        self.assertEqual(instance._pending, [other, stop])

    def test_command_error_and_timeout_are_not_success(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance.gdb_controller = Mock()
        instance.gdb_controller.get_gdb_response.return_value = [
            {"type": "result", "token": 10001, "message": "error", "payload": {"msg": "bad CSR"}}
        ]
        with self.assertRaises(RuntimeError):
            instance._command("-test")
        instance.timeout = 0
        with self.assertRaises(TimeoutError):
            instance._command("-test")

    def test_dwt_polling_configuration_is_rejected(self):
        config = configuration()
        config["GDB"]["stm32"] = {"dwt_watchpoint_workaround": True}
        with self.assertRaises(ValueError):
            ESP32C3Instance(config, "unused")

    def test_invalid_slot_budget_is_rejected(self):
        for count, start in [(0, 0), (9, 0), (8, 1), (1, -1)]:
            config = configuration()
            config["GDB"]["watchpoint_count"] = count
            config["GDB"]["esp32c3"]["hardware_trigger_slot"] = start
            with self.subTest(count=count, start=start), self.assertRaises(ValueError):
                ESP32C3Instance(config, "unused")

    def test_merge_rejects_partial_and_divergent_windows(self):
        for other in [[], [entry(), entry()], [entry(function="different")]]:
            with self.subTest(other=other), self.assertRaises(ValueError):
                GDBTracer.merge_traces([entry()], other)

    def test_merge_does_not_mutate_previous_window(self):
        first = [entry(hits=[0])]
        merged = GDBTracer.merge_traces(first, [entry(hits=[1])])
        self.assertEqual(merged[0].watchpoint_hits, [0, 1])
        self.assertEqual(first[0].watchpoint_hits, [0])

    def test_failed_trigger_init_still_disables_slot(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance._halted = True
        instance._triggers = {"c3-read-0": ReadTrigger(0, 0x100, 0, 0, 0)}
        # Partial init left an unexpected active trigger; cleanup must still disable it.
        instance._read_registers = Mock(return_value=({0: (0, 0)}, 0))
        instance._monitor = Mock()
        instance.delete_breakpoint("c3-read-0")
        self.assertEqual(instance._triggers, {})
        self.assertIn("tdata1 0", instance._monitor.call_args_list[0][0][0])

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
        self.assertEqual([r["payload"]["offset"] for r in instance._pending[:-1]], list(range(8)))
        self.assertEqual(instance._pending[-1], successor)
        self.assertEqual(instance._step_stop.call_count, 2)

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
        self.assertEqual([r["payload"]["offset"] for r in instance._pending[:-1]], [0, 2, 7])
        calls = instance._set_triggers.call_args_list
        self.assertEqual([t.slot for t in calls[0].args[0]], [7])
        self.assertEqual([t.slot for t in calls[1].args[0]], [0, 2])
        self.assertTrue(calls[-1].args[1])

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
        self.assertEqual(
            [r["payload"].get("offset") for r in instance._pending], [0, None, 0, None]
        )

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
        self.assertEqual(instance._pending, [stop])

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
        self.assertEqual(instance._pending, [successor])
        instance._set_triggers.assert_called()  # Disabled for the load, then re-armed.

    def test_unlabelled_rom_finish_is_the_return_breakpoint(self):
        # GDB omits the reason when the finished function has no DWARF.
        stop = {"type": "notify", "message": "stopped", "payload": {"frame": {"func": "caller"}}}
        instance = self.finishing(stop, [self.registers(7, cause=2, first_slot=1)])
        instance.step_out_of_function()
        self.assertEqual(instance._pending[0]["payload"]["reason"], "function-finished")

    def test_unexplained_finish_stop_fails_closed(self):
        trap = {"type": "notify", "message": "stopped", "payload": {"reason": "signal-received"}}
        unlabelled = {"type": "notify", "message": "stopped", "payload": {"frame": {"func": "f"}}}
        exception = {
            "type": "notify",
            "message": "stopped",
            "payload": {"frame": {"func": "_Unwind_DebugHook"}},
        }
        for stop, cause in [(trap, 2), (unlabelled, 3), (exception, 2)]:
            instance = self.finishing(stop, [self.registers(7, cause=cause, first_slot=1)])
            with self.subTest(stop=stop, cause=cause), self.assertRaises(RuntimeError):
                instance.step_out_of_function()
            self.assertEqual(instance._pending, [])

    def test_raw_window_is_reserved_from_openocd(self):
        config = configuration()
        config["GDB"]["watchpoint_count"] = 6
        config["GDB"]["esp32c3"]["hardware_trigger_slot"] = 2
        config["GDB"]["esp32c3"]["breakpoint_always_inserted"] = True
        instance = ESP32C3Instance(config, "unused")
        instance._monitor = Mock()
        instance._command = Mock()
        with patch.object(ESP32C3Instance.__mro__[1], "__enter__", return_value=instance):
            instance.__enter__()
        self.assertEqual(
            instance._monitor.call_args_list[0].args[0],
            "; ".join(f"riscv reserve_trigger {slot} on" for slot in range(2, 8)),
        )
        instance._command.assert_called_once_with("-gdb-set breakpoint always-inserted on")

    def test_cleanup_attempts_every_slot_even_after_a_failure(self):
        instance = self.hardware(8)
        instance.delete_breakpoint = Mock(side_effect=[RuntimeError("slot 0 changed"), *[None] * 7])
        with self.assertRaises(ExceptionGroup):
            instance._clear_triggers()
        self.assertEqual(instance.delete_breakpoint.call_count, 8)

    def test_active_foreign_slot_is_not_overwritten(self):
        instance = ESP32C3Instance(configuration(), "unused")
        instance._halted = True
        instance._command = Mock(return_value=({"payload": {"value": "256"}}, ""))
        instance._read_registers = Mock(return_value=({0: (4, 0x200)}, 0))
        instance._monitor = Mock()
        with self.assertRaises(RuntimeError):
            instance.set_watchpoint_and_get_id("&buf[0]", "(char*)")
        instance._monitor.assert_not_called()
        self.assertEqual(instance._triggers, {})

    def test_batched_registers_check_each_selected_slot(self):
        instance = self.hardware(2)
        text = ""
        for slot in [0, 1]:
            text += (
                f"tselect (/32): {slot:#x}\ntselect (/32): {slot:#x}\n"
                f"tdata1 (/32): {instance.MCONTROL:#x}\ntdata2 (/32): {0x100 + slot:#x}\n"
            )
        text += "dcsr (/32): 0x100\n"
        instance._monitor = Mock(return_value=text)
        self.assertEqual(instance._read_registers([0, 1]), self.registers(2))
        instance._monitor.return_value = text.replace("tselect (/32): 0x1", "tselect (/32): 0x0")
        with self.assertRaises(RuntimeError):
            instance._read_registers([0, 1])

    def test_truncated_unwind_is_not_parser_return(self):
        # A named caller, and a namespaced entry whose caller frame has no name:
        # trace entries normalise "percent::decode", GDB frames do not.
        for function, caller in [
            ("parser", {"addr": "0x20", "func": "caller"}),
            ("percent::decode", {"addr": "0x20"}),
        ]:
            with self.subTest(function=function):
                self.check_truncated_unwind_is_not_parser_return(function, caller)

    def check_truncated_unwind_is_not_parser_return(self, function, caller):
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

        tracer = GDBTracer(configuration())
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
        with patch("tracer.gdb_tracer.time.sleep"), self.assertRaises(RuntimeError):
            tracer.trace_input_slice(instance, 1, 0)


if __name__ == "__main__":
    unittest.main()
