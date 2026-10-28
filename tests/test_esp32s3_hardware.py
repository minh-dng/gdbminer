"""Host-side contract checks for the ESP32-S3 backend; live hardware evidence is still required."""

from unittest.mock import Mock, call, patch

import pytest

from tracer.instance.esp32s3_debug import (
    DATA_BREAKPOINT_COUNT,
    DBREAKC_READ_BYTE,
    DEBUGCAUSE_DBNUM_MASK,
    DEBUGCAUSE_DBNUM_SHIFT,
    ENTRY_BYTE0,
    MASK_ROM,
    PRO_CPU_PRID,
    WATCH_MIN_DISTANCE,
    DBreakC,
    DebugCause,
    is_windowed_call,
    jx_register,
    l32r_register,
    load_size,
    load_width,
)
from tracer.instance.esp32s3_instance import ESP32S3Instance, _DataBreak

IC, IB, DB = DebugCause.IC, DebugCause.IB, DebugCause.DB
PC = 0x42000010
WATCHED = (0x3FC80000, 0x3FC80004)
L8UI = bytes([0x82, 0x03, 0x00])  # l8ui a8, a3, 0
L32I_N = bytes([0x88, 0x13, 0x00])  # l32i.n a8, a3, 4
ADD = bytes([0xA0, 0x88, 0x80])  # add a8, a8, a10 (op0 = 0, not a load)
CALL8 = bytes([0x65, 0x00, 0x00])
ENTRY = bytes([ENTRY_BYTE0, 0x41, 0x00])
L32R_A9 = bytes([0x91, 0x00, 0xFF])
JX_A9 = bytes([0xA0, 0x09, 0x00])


def configuration():
    return {
        "BASIC": {"binary_file": "unused.elf"},
        "GDB": {
            "instance": "esp32s3",
            "timeout": 1,
            "gdb_path": "gdb",
            "gdb_server_path": "openocd",
            "gdb_port": 3333,
            "watchpoint_count": 2,
            "esp32s3": {"watchpoint_min_distance": 4},
            "exitpoint": "",
            "entrypoint": "parser",
            "watchpoint_type": "(char*)",
            "input_buffer": "buf",
        },
        "Connection": {},
    }


def state(cause=IC, windowstart=1, dbreaks=WATCHED, lbeg=0, lend=0):
    registers = {"debugcause": int(cause), "windowstart": windowstart, "lbeg": lbeg, "lend": lend}
    registers["lcount"] = 0
    for slot in range(DATA_BREAKPOINT_COUNT):
        address = dbreaks[slot] if slot < len(dbreaks) else 0
        registers[f"dbreaka{slot}"] = address
        registers[f"dbreakc{slot}"] = DBREAKC_READ_BYTE if address else 0
    return registers


def stop(pc, reason="end-stepping-range", **payload):
    return {
        "type": "notify",
        "message": "stopped",
        "payload": {"reason": reason, "frame": {"addr": hex(pc), "func": "parser"}, **payload},
    }


def hit_cause(slot):
    return DB | slot << DEBUGCAUSE_DBNUM_SHIFT


def hardware(code=None, *, count=2):
    """An instance halted at `PC` that owns `count` watchpoints, with code at given addresses."""
    instance = ESP32S3Instance(configuration(), "unused")
    for index in range(count):
        number = str(index + 2)
        instance._triggers[number] = _DataBreak(number, index, WATCHED[index], index)
    instance._halted = True
    instance._pc = hex(PC)
    instance._state = state()
    memory = {PC: L8UI, **(code or {})}
    instance._code_at = Mock(side_effect=lambda address: memory[address])
    return instance


def run(instance, steps):
    """Answer each step with the next (stop, state) pair."""
    answers = iter(steps)

    def step_stop():
        response, registers = next(answers)
        instance._pc = response["payload"]["frame"]["addr"]
        instance._next_state = registers
        return response

    instance._step_stop = Mock(side_effect=step_stop)
    instance._debug_state = Mock(side_effect=lambda: instance._next_state)
    instance.step_instruction()


class TestDebugValues:
    def test_values_match_openocd_and_esp_idf(self):
        # Independent reference values catch reordered auto() members and bad bit offsets.
        assert {flag.name: flag.value for flag in DebugCause} == {
            "IC": 0x1,
            "IB": 0x2,
            "DB": 0x4,
            "BI": 0x8,
            "BN": 0x10,
            "DI": 0x20,
        }
        assert (DEBUGCAUSE_DBNUM_SHIFT, DEBUGCAUSE_DBNUM_MASK) == (8, 0xF)
        assert (DBreakC.LOAD, DBreakC.STORE) == (0x40000000, 0x80000000)
        assert DBREAKC_READ_BYTE == 0x4000003F
        assert (DATA_BREAKPOINT_COUNT, WATCH_MIN_DISTANCE, PRO_CPU_PRID) == (2, 4, 0xCDCD)
        assert (MASK_ROM.start, MASK_ROM.stop) == (0x40000000, 0x40060000)

    @pytest.mark.parametrize(
        "insn, width, size",
        [
            (L8UI, 1, 3),
            (bytes([0x82, 0x13, 0x00]), 2, 3),  # l16ui
            (bytes([0x82, 0x93, 0x00]), 2, 3),  # l16si
            (bytes([0x82, 0x23, 0x00]), 4, 3),  # l32i
            (bytes([0x82, 0xB3, 0x00]), 4, 3),  # l32ai
            (L32I_N, 4, 2),
        ],
    )
    def test_scalar_loads_and_their_sizes(self, insn, width, size):
        assert load_width(insn) == width
        assert load_size(insn) == size

    @pytest.mark.parametrize("insn", [ADD, bytes([0x82, 0x43, 0x00]), CALL8, L32R_A9])
    def test_other_instructions_are_not_loads(self, insn):
        # 0x82 0x43: LSAI r = 4 is s8i, a store.
        assert load_width(insn) is None

    def test_call_and_jump_stub_decoding(self):
        assert is_windowed_call(CALL8)
        assert is_windowed_call(bytes([0xE0, 0x0A, 0x00]))  # callx8 a10
        assert not is_windowed_call(bytes([0x05, 0x00, 0x00]))  # call0
        assert not is_windowed_call(JX_A9)
        assert l32r_register(L32R_A9) == 9
        assert l32r_register(JX_A9) is None
        assert jx_register(JX_A9) == 9
        assert jx_register(CALL8) is None


class TestStep:
    def test_read_precedes_the_one_successor(self):
        instance = hardware()
        successor = stop(PC + 3)
        run(instance, [(stop(PC), state(hit_cause(1))), (successor, state())])
        assert instance._pending == [
            {
                "type": "notify",
                "message": "stopped",
                "payload": {"reason": "read-watchpoint-trigger", "offset": 1},
            },
            successor,
        ]

    def test_ordinary_step_has_no_read(self):
        instance = hardware({PC: ADD})
        run(instance, [(stop(PC + 3), state())])
        assert instance._pending == [stop(PC + 3)]

    def test_same_pc_with_unchanged_window_is_one_executed_instruction(self):
        # A loop wrap or a branch to itself.
        instance = hardware({PC: ADD})
        run(instance, [(stop(PC), state())])
        assert instance._pending == [stop(PC)]

    def test_register_window_exception_is_stepped_again(self):
        instance = hardware({PC: ADD})
        run(instance, [(stop(PC), state(windowstart=3)), (stop(PC + 3), state(windowstart=3))])
        assert instance._step_stop.call_count == 2
        assert instance._pending == [stop(PC + 3)]

    def test_hit_repeated_after_a_window_exception_is_one_read(self):
        instance = hardware()
        run(
            instance,
            [
                (stop(PC), state(hit_cause(0))),
                (stop(PC), state(windowstart=3)),
                (stop(PC), state(hit_cause(0), windowstart=3)),
                (stop(PC + 3), state(windowstart=3)),
            ],
        )
        assert [response["payload"]["reason"] for response in instance._pending] == [
            "read-watchpoint-trigger",
            "end-stepping-range",
        ]

    def test_load_at_a_zero_overhead_loop_end_retires_to_lbeg(self):
        instance = hardware({PC: L32I_N})
        loop = state(lbeg=0x42000000, lend=PC + 2)
        run(instance, [(stop(PC), state(hit_cause(0))), (stop(0x42000000), loop)])
        assert len(instance._pending) == 2

    def test_step_onto_the_exit_breakpoint_is_passed_to_the_tracer(self):
        instance = hardware({PC: ADD})
        exit_hit = stop(PC + 3, "breakpoint-hit", bkptno="3")
        run(instance, [(exit_hit, state(IB))])
        assert instance._pending == [exit_hit]

    @pytest.mark.parametrize(
        "code, steps",
        [
            # A data breakpoint halt on an instruction that is not a load.
            (ADD, [(stop(PC), state(hit_cause(0)))]),
            # A load that does not retire to its successor.
            (L8UI, [(stop(PC), state(hit_cause(0))), (stop(PC + 8), state())]),
            # The same slot twice without a window exception in between.
            (L8UI, [(stop(PC), state(hit_cause(0))), (stop(PC), state(hit_cause(0)))]),
            # A halt with no recognised cause.
            (ADD, [(stop(PC + 3), state(DebugCause.DI))]),
            # The firmware rewrote DBREAK1 during the step.
            (ADD, [(stop(PC + 3), state(dbreaks=(WATCHED[0], 0x3FCEA160)))]),
        ],
    )
    def test_unexplained_halts_fail_closed(self, code, steps):
        instance = hardware({PC: code})
        with pytest.raises(RuntimeError):
            run(instance, steps)
        assert instance._pending == []

    def test_rom_jump_stub_is_followed_to_the_routine_entry(self):
        stub, routine = 0x40001000, 0x40002000
        instance = hardware({PC: CALL8, stub: L32R_A9, stub + 3: JX_A9, routine: ENTRY})
        entry = stop(routine)
        run(
            instance,
            [(stop(stub), state()), (stop(stub + 3), state()), (entry, state())],
        )
        assert instance._pending == [entry]

    def test_call_target_without_entry_outside_rom_fails_closed(self):
        target = 0x42001000
        instance = hardware({PC: CALL8, target: L32R_A9, target + 3: JX_A9})
        with pytest.raises(RuntimeError, match="no ENTRY"):
            run(instance, [(stop(target), state())])


class TestFinish:
    def finish(self, response, registers, after=None):
        instance = hardware()
        instance._command = Mock(return_value=({"message": "done"}, ""))
        instance._wait_stop = Mock(return_value=response)
        instance._debug_state = Mock(side_effect=[registers, after or state()])
        instance.step_out_of_function()
        return instance

    @pytest.mark.parametrize("reason", ["function-finished", "breakpoint-hit", None])
    def test_instruction_breakpoint_stops_are_passed_on(self, reason):
        response = stop(PC, reason)
        if reason is None:
            del response["payload"]["reason"]
        instance = self.finish(response, state(IB))
        assert instance._pending == [response]

    def test_finish_that_returns_after_one_step_is_passed_on(self):
        # The return stop ends with ICOUNT instead of IBREAK; GDB still names it.
        response = stop(PC, "function-finished")
        instance = self.finish(response, state(IC))
        assert instance._pending == [response]

    def test_read_inside_a_skipped_function_is_not_recorded(self):
        # GDB stepped over the load with its watchpoints removed; it inserts them at the next
        # resume, so the adapter must not re-insert them.
        response = stop(PC, "read-watchpoint-trigger", **{"hw-rwpt": {"number": "2"}})
        instance = self.finish(response, state(IC, dbreaks=()))
        assert instance._pending == [stop(PC)]
        assert instance._command.call_args_list == [call("-exec-finish")]

    @pytest.mark.parametrize(
        "reason, cause",
        [
            ("read-watchpoint-trigger", DB),
            ("signal-received", DebugCause.DI),
            (None, IC),
        ],
    )
    def test_unexplained_finish_stops_fail_closed(self, reason, cause):
        with pytest.raises(RuntimeError, match="Unexpected S3 finish stop"):
            self.finish(stop(PC, reason), state(cause))

    def test_overwritten_watchpoint_is_inserted_again(self):
        guard = state(IB, dbreaks=(WATCHED[0], 0x3FCEA160))
        guard["dbreakc1"] = DBreakC.STORE | 0x20
        instance = self.finish(stop(PC, "function-finished"), guard)
        assert instance._command.call_args_list[1:] == [
            call("-break-disable 3"),
            call("-break-enable 3"),
        ]

    def test_watchpoint_not_restored_fails_closed(self):
        guard = state(IB, dbreaks=(WATCHED[0], 0x3FCEA160))
        with pytest.raises(RuntimeError, match="DBREAK1 changed"):
            self.finish(stop(PC, "function-finished"), guard, after=guard)


class TestWatchpoints:
    def allocator(self, prid=PRO_CPU_PRID):
        instance = ESP32S3Instance(configuration(), "unused")
        instance._halted = True
        addresses = iter(WATCHED)
        numbers = iter(["2", "3"])

        def command(text):
            if text == "-data-evaluate-expression $bpnum":
                return {"payload": {"value": next(numbers)}}, ""
            if text.startswith("-data-evaluate-expression"):
                return {"payload": {"value": f"{next(addresses):#x} <buf>"}}, ""
            return {"payload": {}}, ""

        instance._command = Mock(side_effect=command)
        instance._registers = Mock(return_value={"prid": prid})
        armed = iter([state(dbreaks=WATCHED[:1]), state()])
        instance._debug_state = Mock(side_effect=lambda: next(armed))
        return instance

    def test_watchpoints_are_found_in_their_dbreak_pairs(self):
        instance = self.allocator()
        assert instance.set_watchpoint_and_get_id("&buf[0]", "(char*)") == "2"
        assert instance.set_watchpoint_and_get_id("&buf[4]", "(char*)") == "3"
        assert [(wp.index, wp.slot) for wp in instance._triggers.values()] == [(0, 0), (1, 1)]
        # The byte is watched by location, so a local such as `data` neither scopes it nor is
        # watched itself; no C cast, so the commands also parse in a Rust frame.
        instance._command.assert_any_call('-data-evaluate-expression "&buf[4]"')
        instance._command.assert_any_call(
            '-interpreter-exec console "rwatch -location *(char*)(&buf[4])"'
        )

    def test_entry_on_the_other_core_is_rejected(self):
        with pytest.raises(RuntimeError, match="expected core 0"):
            self.allocator(prid=0xABAB).set_watchpoint_and_get_id("&buf[0]", "(char*)")

    def test_watched_bytes_closer_than_a_word_are_rejected(self):
        instance = self.allocator()
        instance._triggers["2"] = _DataBreak("2", 0, WATCHED[1] - 3, 0)
        with pytest.raises(ValueError, match="watchpoint_min_distance"):
            instance.set_watchpoint_and_get_id("&buf[1]", "(char*)")

    def test_budget_is_checked(self):
        config = configuration()
        config["GDB"]["watchpoint_count"] = 3
        with pytest.raises(ValueError, match="watchpoint_count"):
            ESP32S3Instance(config, "unused")


class TestAttach:
    def test_failed_attach_resets_usb_and_attaches_again(self):
        config = configuration()
        config["GDB"]["esp32s3"]["usb_reset_command"] = "reset-usb --serial E8"
        instance = ESP32S3Instance(config, "unused")
        enter = Mock(side_effect=[TimeoutError("OpenOCD startup timed out"), instance])
        with (
            patch("tracer.instance.esp32_instance.ESP32Instance.__enter__", enter),
            patch("tracer.instance.esp32s3_instance.subprocess.run") as run_command,
        ):
            assert instance.__enter__() is instance
        run_command.assert_called_once_with(
            ["reset-usb", "--serial", "E8"], check=True, timeout=120
        )

    def test_without_a_reset_command_the_first_failure_is_raised(self):
        instance = ESP32S3Instance(configuration(), "unused")
        enter = Mock(side_effect=TimeoutError("OpenOCD startup timed out"))
        with (
            patch("tracer.instance.esp32_instance.ESP32Instance.__enter__", enter),
            patch("tracer.instance.esp32s3_instance.subprocess.run") as run_command,
            pytest.raises(TimeoutError),
        ):
            instance.__enter__()
        run_command.assert_not_called()

    def test_openocd_starts_after_the_startup_delay(self):
        config = configuration()
        config["GDB"]["esp32s3"]["startup_delay"] = 2.5
        instance = ESP32S3Instance(config, "unused")
        order = Mock()
        with (
            patch("tracer.instance.esp32s3_instance.time.sleep", order.sleep),
            patch("tracer.instance.esp32_instance.ESP32Instance._start_gdb_server", order.start),
        ):
            instance._start_gdb_server()
        assert order.mock_calls == [call.sleep(2.5), call.start()]

    def test_watchpoints_stay_inserted_while_halted(self):
        assert ESP32S3Instance(configuration(), "unused").breakpoint_always_inserted

    def test_no_debugger_reset_by_default_and_none_allowed(self):
        # OpenOCD's reset re-enumerates the USB device and closes the serial port.
        assert not ESP32S3Instance(configuration(), "unused").reset_on_connect
        config = configuration()
        config["GDB"]["esp32s3"]["reset_on_connect"] = True
        with pytest.raises(ValueError, match="reset_on_connect"):
            ESP32S3Instance(config, "unused")
