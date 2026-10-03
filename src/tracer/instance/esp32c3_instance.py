# ESP32-C3 hardware read observation through stock Espressif OpenOCD.
# SPDX-License-Identifier: AGPL-3.0

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import override

from tracer.instance.stm32_instance import STM32Instance
from tracer.instance.sut_instance import SUTInstance
from util.config import Config


@dataclass
class ReadTrigger:
    slot: int
    address: int
    offset: int
    previous_control: int
    previous_address: int
    arm_validated: bool = False


class ESP32C3Instance(STM32Instance):
    """Own raw read triggers; retire before-load halts without exposing them.

    OpenOCD removes *managed* watchpoints during stepi. Raw mcontrol registers
    remain armed. Never mix this path with ARM DWT polling.
    The C3 has eight trigger slots shared by breakpoints and watchpoints.
    Slots below GDB.esp32c3.hardware_trigger_slot stay free for GDB's managed hardware
    breakpoints: an exit point needs one, and each finish needs two (return
    address and the C++ exception hook _Unwind_DebugHook). The raw window is
    reserved in OpenOCD, so a breakpoint that does not fit fails to insert.
    Transactions are synchronous and token-correlated; unrelated MI messages
    stay queued. This keeps CSR polling out of response normalization.
    """

    # RV32 debug spec mcontrol: type=2, dmode=1, action=debug, M-mode, load.
    # Espressif OpenOCD debug_defines.h: hit bit 20, dcsr.cause trigger=2/step=4.
    MCONTROL = 0x28001041
    HIT = 1 << 20
    CONTROL_MASK = 0xF81FFFFF  # Ignore implementation maskmax/reserved high bits.
    WATCHPOINT_PREFIX = "c3-read-"
    # pygdbmi keeps reading until the timeout expires even after output
    # arrives, so the poll interval is a latency floor on every transaction.
    POLL_SEC = 0.001

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config, input_file)
        c3 = config["GDB"]["esp32c3"]
        # The serial EN pulse already restarts firmware in the example configurations.
        self.reset_on_connect = c3.get("reset_on_connect", True)
        if self.dwt_watchpoint_workaround:
            raise ValueError("C3 observes reads with RISC-V triggers, not ARM DWT polling")
        if not 1 <= self.watchpoint_count <= 8:
            raise ValueError("C3 hardware observation requires 1 <= watchpoint_count <= 8")
        self.trigger_slot = c3["hardware_trigger_slot"]
        if self.trigger_slot < 0 or self.trigger_slot + self.watchpoint_count > 8:
            raise ValueError("C3 configured trigger window must fit slots 0..7")
        self._token = 10000
        self._pending: list[dict] = []
        self._triggers: dict[str, ReadTrigger] = {}
        self._pc = "unknown"
        self._halted = False

    @override
    def init_gdb_controller(self):
        super().init_gdb_controller()
        rom_elf = self.config["GDB"]["esp32c3"].get("rom_elf", "")
        if rom_elf:
            # Name built-in ROM routines so the tracer's ignore regex can match them.
            # Symbols alone do not guarantee that GDB can unwind a ROM call.
            command = "add-symbol-file " + json.dumps(str(Path(rom_elf).resolve(strict=True)))
            self._command(f"-interpreter-exec console {json.dumps(command)}")

    def _command(self, command: str) -> tuple[dict, str]:
        """Run one bounded MI transaction, preserving other results and events."""
        self._token += 1
        token = self._token
        self.send_gdb_command(f"{token}{command}")
        deadline = time.monotonic() + self.timeout
        streams = []
        result = None
        while result is None:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"C3 command timeout: {command}; pc={self._pc}, slot={self.trigger_slot}"
                )
            responses = self.gdb_controller.get_gdb_response(
                timeout_sec=self.POLL_SEC, raise_error_on_timeout=False
            )
            for response in responses:
                if response.get("type") == "result" and response.get("token") == token:
                    result = response
                elif response.get("type") in {"console", "target", "log"}:
                    streams.append(str(response.get("payload", "")))
                else:
                    self._pending.append(response)
        if result.get("message") not in {"done", "running", "connected"}:
            raise RuntimeError(f"C3 command failed: {command}: {result}; {''.join(streams)}")
        return result, "".join(streams)

    def _monitor(self, command: str) -> str:
        # OpenOCD returns only the last Tcl result for a command list. Echo each
        # register result so fresh reads are not lost when batching a transaction.
        commands = "; ".join(f"echo [{part.strip()}]" for part in command.split(";"))
        _, text = self._command(f"-interpreter-exec console {json.dumps('monitor ' + commands)}")
        return text

    @staticmethod
    def _register(text: str, name: str) -> int:
        matches = re.findall(rf"\b{re.escape(name)} \(/32\): (0x[0-9a-fA-F]+)", text)
        if not matches:
            raise RuntimeError(f"Missing fresh C3 register {name}: {text}")
        return int(matches[-1], 16)

    def _read_registers(self, slots: list[int]) -> tuple[dict[int, tuple[int, int]], int]:
        # One serialized MI transaction for the whole window, not one round trip
        # per register/slot. Each selected slot still gets a forced readback.
        commands = [
            f"reg tselect {slot}; reg tselect force; reg tdata1 force; reg tdata2 force"
            for slot in slots
        ]
        text = self._monitor("; ".join([*commands, "reg dcsr force"]))
        values = re.findall(r"\b(tselect|tdata1|tdata2|dcsr) \(/32\): (0x[0-9a-fA-F]+)", text)
        expected_names = ["tselect", "tselect", "tdata1", "tdata2"] * len(slots) + ["dcsr"]
        if [name for name, _ in values] != expected_names:
            raise RuntimeError(f"Incomplete C3 register transaction for slots {slots}: {text}")
        states = {}
        for index, slot in enumerate(slots):
            selected, control, address = [
                int(value, 16) for _, value in values[index * 4 + 1 : index * 4 + 4]
            ]
            if selected != slot:
                raise RuntimeError(f"C3 trigger slot {slot} is unavailable (read back {selected})")
            states[slot] = (control, address)
        return states, int(values[-1][1], 16)

    def _registers(self) -> tuple[int, int, int]:
        """Read one selected slot (also used by the standalone capability probe)."""
        states, dcsr = self._read_registers([self.trigger_slot])
        return *states[self.trigger_slot], dcsr

    def _check_armed(self, trigger: ReadTrigger, control: int, address: int, *, hit: bool = False):
        expected = self.MCONTROL | (self.HIT if hit else 0)
        if control & self.CONTROL_MASK != expected or address != trigger.address:
            raise RuntimeError(
                f"C3 trigger changed/stale: pc={self._pc}, slot={trigger.slot}, "
                f"tdata1={control:#x}, tdata2={address:#x}, expected={expected:#x}"
            )

    def _set_triggers(self, triggers: list[ReadTrigger], enabled: bool):
        value = self.MCONTROL if enabled else 0
        self._monitor("; ".join(f"reg tselect {t.slot}; reg tdata1 {value:#x}" for t in triggers))
        states, _ = self._read_registers([t.slot for t in triggers])
        for trigger in triggers:
            control, address = states[trigger.slot]
            if enabled:
                self._check_armed(trigger, control, address)
                trigger.arm_validated = True
            elif control & 7 or address != trigger.address:
                raise RuntimeError(
                    f"C3 trigger {trigger.slot} did not disable: {control:#x}/{address:#x}"
                )
            else:
                trigger.arm_validated = False

    @override
    def set_watchpoint_and_get_id(self, address, watchpoint_type) -> str:
        if not self._halted or len(self._triggers) >= self.watchpoint_count:
            raise RuntimeError(
                "Allocate C3 triggers within the configured budget at a halted entry"
            )
        if watchpoint_type != "(char*)":
            raise ValueError("C3 currently supports byte watchpoint expressions only")
        result, _ = self._command(
            f"-data-evaluate-expression {json.dumps('(unsigned int)(' + address + ')')}"
        )
        watch_address = int(result["payload"]["value"], 0)
        offset = len(self._triggers)
        slot = self.trigger_slot + offset
        states, dcsr = self._read_registers([slot])
        control, old_address = states[slot]
        if control & 7:
            raise RuntimeError(f"C3 slot {slot} already has an active owner")
        if dcsr & (1 << 11):
            raise RuntimeError("C3 requires dcsr.stepie=0 (interrupts masked during stepping)")
        watchpoint_id = f"{self.WATCHPOINT_PREFIX}{slot}"
        trigger = ReadTrigger(slot, watch_address, offset, control, old_address)
        self._triggers[watchpoint_id] = trigger  # Reserve before writes for partial-init cleanup.
        try:
            self._monitor(f"reg tselect {slot}; reg tdata1 0; reg tdata2 {watch_address:#x}")
            self._set_triggers([trigger], True)
        except BaseException:
            self._release_slot(watchpoint_id)
            raise
        logging.info("C3 owns slot %d at %#x (window offset %d)", slot, watch_address, offset)
        return watchpoint_id

    def _wait_stop(self) -> dict:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            for i, response in enumerate(self._pending):
                if self.is_stop_message(response):
                    self._pending.pop(i)
                    self._halted = True
                    self._pc = response["payload"].get("frame", {}).get("addr", "unknown")
                    return response
                if response.get("type") == "result" and response.get("message") == "error":
                    raise RuntimeError(f"C3 asynchronous command failed: {response}")
            self._pending.extend(
                self.gdb_controller.get_gdb_response(
                    timeout_sec=self.POLL_SEC, raise_error_on_timeout=False
                )
            )
        raise TimeoutError(f"C3 stop timeout: pc={self._pc}, slot={self.trigger_slot}")

    def _step_stop(self) -> dict:
        self._halted = False
        self._command("-exec-step-instruction")
        stop = self._wait_stop()
        # A step that lands on the exit breakpoint is reported as its hit;
        # the tracer checks the breakpoint number and ends the window.
        if stop["payload"].get("reason") not in {"end-stepping-range", "breakpoint-hit"}:
            raise RuntimeError(f"Unexpected C3 step stop: {stop}")
        return stop

    @override
    def step_instruction(self):
        self._step(report=True)

    def _step(self, *, report: bool):
        """Execute one instruction, retiring before-load trigger halts.

        report=False retires reads without exposing them to the tracer.
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("C3 logical step needs a halted target and owned triggers")
        # No pre-step readback: the previous step, finish, or arming already
        # validated every trigger, and stack requests do not write CSRs.
        triggers = list(self._triggers.values())
        slots = [t.slot for t in triggers]
        before_pc = self._pc
        observed: dict[int, ReadTrigger] = {}
        # Each before-load halt must reveal at least one new hardware match.
        # Keep unmatched triggers armed during recovery; never infer wide-load
        # byte hits from address arithmetic. At most N hits plus one retirement.
        for _ in range(len(triggers) + 1):
            stop = self._step_stop()
            states, dcsr = self._read_registers(slots)
            hits = []
            for trigger in triggers:
                control, address = states[trigger.slot]
                if trigger.slot in observed:
                    if control & (7 | self.HIT) or address != trigger.address:
                        raise RuntimeError(
                            f"C3 disabled trigger changed: slot={trigger.slot}, {states}"
                        )
                else:
                    hit = bool(control & self.HIT)
                    self._check_armed(trigger, control, address, hit=hit)
                    if hit:
                        hits.append(trigger)
            cause = (dcsr >> 6) & 7
            if dcsr & (1 << 11):
                raise RuntimeError("C3 interrupts became enabled during stepping")
            if cause == 4 and not hits:
                break
            if cause != 2 or not hits or self._pc != before_pc:
                raise RuntimeError(
                    f"Unexplained C3 halt: pc={before_pc}->{self._pc}, dcsr={dcsr:#x}, {states}"
                )
            for trigger in hits:
                observed[trigger.slot] = trigger
                logging.info(
                    "C3 hardware read pc=%s address=%#x slot=%d offset=%d",
                    before_pc,
                    trigger.address,
                    trigger.slot,
                    trigger.offset,
                )
            self._set_triggers(hits, False)
        else:
            raise RuntimeError(f"C3 load recovery exhausted its slot budget at {before_pc}")
        if observed:
            self._set_triggers(list(observed.values()), True)
        for trigger in sorted(observed.values(), key=lambda t: t.offset) if report else ():
            self._pending.append(
                {
                    "type": "notify",
                    "message": "stopped",
                    "payload": {
                        "reason": "read-watchpoint-trigger",
                        "offset": trigger.offset,
                    },
                }
            )
        self._pending.append(stop)

    @override
    def request_stacktrace(self):
        result, _ = self._command("-stack-list-frames")
        if not result.get("payload", {}).get("stack"):
            raise RuntimeError("C3 returned an empty stack")
        self._pending.append(result)

    @override
    def set_temporary_breakpoint(self, breakpoint_address):
        location = (
            "*" + breakpoint_address if breakpoint_address.startswith("0x") else breakpoint_address
        )
        result, _ = self._command(f"-break-insert -t -h {json.dumps(location)}")
        return result["payload"]["bkpt"]["number"]

    @override
    def step_out_of_function(self):
        """GDB finish, as the paper skips ignored functions (Section 4.1).

        The read triggers stay armed while the function runs, so a read inside
        it halts before the load. That read is retired but not recorded, and
        the tracer resumes skipping from there. This matches the authors'
        published STM32 traces (evaluation/stm32_applications): bytes read only
        by the skipped strlen never appear in them.
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("C3 finish needs a halted target and owned triggers")
        self._halted = False
        self._command("-exec-finish")
        stop = self._wait_stop()
        triggers = list(self._triggers.values())
        states, dcsr = self._read_registers([t.slot for t in triggers])
        hit = False
        for trigger in triggers:
            control, address = states[trigger.slot]
            self._check_armed(trigger, control, address, hit=bool(control & self.HIT))
            hit |= bool(control & self.HIT)
        if hit:
            if (dcsr >> 6) & 7 != 2 and stop["payload"].get("reason") != "function-finished":
                raise RuntimeError(f"Unexplained C3 finish stop: dcsr={dcsr:#x}, {stop}")
            # The load has not executed yet; stepping re-fires and retires it.
            self._step(report=False)
            return
        reason = stop["payload"].get("reason")
        if (
            reason is None
            and (dcsr >> 6) & 7 == 2
            and stop["payload"].get("frame", {}).get("func") != "_Unwind_DebugHook"
        ):
            # GDB labels a finish only if the finished function has debug info
            # (finish_command_fsm::should_stop). ROM routines have symbols but
            # no DWARF, so their return-breakpoint stop arrives unlabelled.
            # A trigger halt with no read hit is that breakpoint.
            stop["payload"]["reason"] = reason = "function-finished"
        if reason != "function-finished":
            raise RuntimeError(f"Unexpected C3 finish stop: dcsr={dcsr:#x}, {stop}")
        self._pending.append(stop)

    def _release_slot(self, watchpoint_id: str) -> None:
        trigger = self._triggers[watchpoint_id]
        # Force-disable a reserved slot even if initialization failed mid-write.
        self._monitor(f"reg tselect {trigger.slot}; reg tdata1 0")
        states, _ = self._read_registers([trigger.slot])
        if states[trigger.slot][0] & 7:
            raise RuntimeError(f"C3 trigger {trigger.slot} cleanup did not disable: {states}")
        trigger.arm_validated = False
        self._monitor(
            f"reg tselect {trigger.slot}; reg tdata2 {trigger.previous_address:#x}; "
            f"reg tdata1 {trigger.previous_control:#x}"
        )
        states, _ = self._read_registers([trigger.slot])
        restored, restored_address = states[trigger.slot]
        if restored & 7 or restored_address != trigger.previous_address:
            raise RuntimeError(
                f"C3 trigger {trigger.slot} cleanup did not restore the inactive slot"
            )
        del self._triggers[watchpoint_id]
        logging.info("C3 released slot %d", trigger.slot)

    def _clear_triggers(self):
        errors = []
        for watchpoint_id in list(self._triggers):
            try:
                self.delete_breakpoint(watchpoint_id)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("C3 trigger cleanup failed", errors)

    @override
    def delete_breakpoint(self, breakpoint_id):
        if not breakpoint_id.startswith(self.WATCHPOINT_PREFIX):
            self._command(f"-break-delete {breakpoint_id}")
            return
        trigger = self._triggers.get(breakpoint_id)
        if trigger is None:
            return
        if trigger.arm_validated:
            states, _ = self._read_registers([trigger.slot])
            control, address = states[trigger.slot]
            if control & 7:
                self._check_armed(trigger, control, address, hit=bool(control & self.HIT))
            elif address not in {trigger.previous_address, trigger.address}:
                raise RuntimeError("C3 slot changed owner during cleanup; refusing to overwrite")
        self._release_slot(breakpoint_id)

    @override
    def continue_execution(self):
        if self._triggers:
            raise RuntimeError("Release C3 data triggers before continuing outside the parser")
        self._command("-exec-continue")
        self._halted = False

    @override
    def get_gdb_responses(self) -> list[dict]:
        responses, self._pending = self._pending, []
        responses.extend(SUTInstance.get_gdb_responses(self))
        for response in responses:
            if self.is_stop_message(response) and "frame" in response["payload"]:
                self._halted = True
                self._pc = response["payload"]["frame"]["addr"]
        return responses

    @override
    def wait_for_any_stop_message(self):
        return self._wait_stop()

    @override
    def wait_for_any_gdb_response(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            responses = self.get_gdb_responses()
            if responses:
                return responses
            time.sleep(0.001)
        raise TimeoutError("C3 response timeout")

    @override
    def reset(self):
        if self._triggers:
            if not self._halted:
                self._command("-exec-interrupt")
                self._wait_stop()
            self._clear_triggers()
        self._monitor("reset halt")
        self._command('-interpreter-exec console "flushregs"')
        self._pending.clear()
        self._halted = True

    @override
    def __enter__(self):
        try:
            super().__enter__()
            # Keep OpenOCD's breakpoint allocator out of the raw trigger window.
            # An over-subscribed finish/exit breakpoint then fails to insert
            # instead of overwriting a read trigger.
            window = range(self.trigger_slot, self.trigger_slot + self.watchpoint_count)
            self._monitor("; ".join(f"riscv reserve_trigger {slot} on" for slot in window))
            if self.config["GDB"]["esp32c3"].get("breakpoint_always_inserted", False):
                # Same breakpoints, written once: by default GDB removes every
                # breakpoint after each stop and re-inserts it before the next
                # stepi (infrun.c maybe_remove_breakpoints).
                self._command("-gdb-set breakpoint always-inserted on")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    @override
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._triggers:
                if not self._halted:
                    self._command("-exec-interrupt")
                    self._wait_stop()
                self._clear_triggers()
        finally:
            self._pending.clear()
            try:
                if hasattr(self, "connection"):
                    self.connection.disconnect()
            finally:
                try:
                    if hasattr(self, "gdb_controller"):
                        self.gdb_controller.exit()
                finally:
                    if hasattr(self, "gdb_server"):
                        self.gdb_server.terminate()
                        try:
                            self.gdb_server.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.gdb_server.kill()
                            self.gdb_server.wait()
