# ESP32-C3 hardware read observation through stock Espressif OpenOCD.
# SPDX-License-Identifier: AGPL-3.0

import json
import logging
import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast, override

from tracer.connection import SUTConnection
from util import Config

from .esp32c3_debug import (
    DCSR_CAUSE_OFFSET,
    HARDWARE_TRIGGER_COUNT,
    MCONTROL_ACCESS_MASK,
    MCONTROL_CONTROL_MASK,
    DCSRCause,
    DCSRMask,
    MControlFlag,
)
from .hardware_instance import HardwareInstance, MIReason


class StopFrame(TypedDict, total=False):
    """Frame fields read from a stopped notification; GDB may provide others."""

    addr: str
    func: str


class Breakpoint(TypedDict):
    """Breakpoint field read from a successful insertion result."""

    number: str


class MIPayload(TypedDict, total=False):
    """Dictionary payload fields used here; GDB may provide others."""

    reason: str
    frame: StopFrame
    offset: int
    value: str
    bkpt: Breakpoint
    stack: list[StopFrame]


class GDBResponse(TypedDict):
    """Queued MI record; payload shape depends on the GDB command or event."""

    type: str
    message: str | None
    payload: MIPayload | str | None
    token: NotRequired[int | None]
    stream: NotRequired[str]


@dataclass
class ReadTrigger:
    """One raw read trigger owned by `ESP32C3Instance`."""

    slot: int
    """Trigger slot (`tselect` index)."""
    address: int
    """Byte address that the trigger watches (`tdata2`)."""
    offset: int
    """Index of the watched byte within the current watchpoint window."""
    previous_control: int
    """`tdata1` before this adapter took the slot, restored on release."""
    previous_address: int
    """`tdata2` before this adapter took the slot, restored on release."""
    arm_validated: bool = False
    """The armed state was read back and checked, so cleanup can tell whether the slot still
    holds this trigger."""


class ESP32C3Instance(HardwareInstance):
    """Own raw read triggers; retire before-load halts without exposing them.

    OpenOCD removes *managed* watchpoints during `stepi`. Raw `mcontrol` registers remain armed.
    Never mix this path with ARM DWT polling. The C3 has eight trigger slots shared by breakpoints
    and watchpoints. Slots below `GDB.esp32c3.hardware_trigger_slot` stay free for GDB's managed
    hardware breakpoints: an exit point needs one, and each `finish` needs two (return address and
    the C++ exception hook `_Unwind_DebugHook`). The raw window is reserved in OpenOCD, so a
    breakpoint that does not fit fails to insert. Transactions are synchronous and token-correlated;
    unrelated MI messages stay queued. This keeps CSR polling out of response normalization.
    """

    MCONTROL = (
        MControlFlag.TYPE_MCONTROL
        | MControlFlag.DMODE
        | MControlFlag.ACTION_DEBUG_MODE
        | MControlFlag.M
        | MControlFlag.LOAD
    )
    """`tdata1` of an armed read trigger; see the `MControlFlag` members.

    A load match trigger that only debug mode can write, and that halts into debug mode on a match
    in machine mode. The fields left at zero select `timing` = before and `match` = equal: the hart
    halts before a load from the address in `tdata2` executes.
    """
    WATCHPOINT_PREFIX = "c3-read-"
    """Prefix of the ids of raw triggers handed to the tracer.

    GDB does not know these triggers, so `delete_breakpoint` tells them apart from GDB breakpoint
    numbers.
    """
    POLL_SEC = 0.001
    """Timeout of each pygdbmi read.

    pygdbmi keeps reading until the timeout expires, even after output arrives, so this is a latency
    floor on every transaction.
    """

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config, input_file)
        c3 = config["GDB"]["esp32c3"]
        self.reset_on_connect = c3.get("reset_on_connect", True)
        """Reset the target through GDB at start-up and after a serial reconnect.

        The example configurations set it to false: the serial connection's reset pulse already
        restarts the firmware.
        """
        if not 1 <= self.watchpoint_count <= HARDWARE_TRIGGER_COUNT:
            raise ValueError(
                f"C3 hardware observation requires 1 <= watchpoint_count <= {HARDWARE_TRIGGER_COUNT}"
            )
        self.trigger_slot = c3["hardware_trigger_slot"]
        """First slot of the read window (`GDB.esp32c3.hardware_trigger_slot`)."""
        if (
            self.trigger_slot < 0
            or self.trigger_slot + self.watchpoint_count > HARDWARE_TRIGGER_COUNT
        ):
            raise ValueError(
                f"C3 configured trigger window must fit slots 0..{HARDWARE_TRIGGER_COUNT - 1}"
            )
        self._token = 10000
        """Last MI token used by `_command`.

        GDB echoes the token on the matching result record (`10001^done`), which separates that
        result from stop records and from the results of earlier commands.
        """
        self._pending: list[GDBResponse] = []
        """MI records read while waiting for something else, in arrival order, for `_wait_stop`
        and for the tracer (`get_gdb_responses`)."""
        self._triggers: dict[str, ReadTrigger] = {}
        """Raw read triggers owned by this instance, by watchpoint id."""
        self._pc = "unknown"
        """Program counter of the last reported stop."""
        self._halted = False
        """GDB last reported the hart halted. While the target runs, GDB reads no MI command (see
        `_interrupt`)."""

    @override
    def init_gdb_controller(self):
        super().init_gdb_controller()
        rom_elf = self.config["GDB"]["esp32c3"].get("rom_elf", "")
        if rom_elf:
            # Name built-in ROM routines so the tracer's ignore regex can match them. Symbols alone
            # do not guarantee that GDB can unwind a ROM call.
            command = "add-symbol-file " + json.dumps(str(Path(rom_elf).resolve(strict=True)))
            self._command(f"-interpreter-exec console {json.dumps(command)}")

    @staticmethod
    def _payload(response: GDBResponse) -> MIPayload:
        payload = response["payload"]
        if not isinstance(payload, dict):
            raise TypeError(f"Expected a C3 MI dictionary payload: {response}")
        return payload

    def _read_responses(self) -> list[GDBResponse]:
        # pygdbmi is untyped; keep the assertion at the parser boundary.
        return cast(
            list[GDBResponse],
            self.gdb_controller.get_gdb_response(
                timeout_sec=self.POLL_SEC, raise_error_on_timeout=False
            ),
        )

    def _command(self, command: str) -> tuple[GDBResponse, str]:
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
            responses = self._read_responses()
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
        """Run `;`-separated OpenOCD commands through GDB's `monitor` and return their output.

        OpenOCD returns only the last Tcl result of a command list, so each command is wrapped in
        `echo [...]`: register reads are not lost when a transaction is batched.
        """
        commands = "; ".join(f"echo [{part.strip()}]" for part in command.split(";"))
        _, text = self._command(f"-interpreter-exec console {json.dumps('monitor ' + commands)}")
        return text

    def _read_registers(self, slots: list[int]) -> tuple[dict[int, tuple[int, int]], int]:
        """Read `(tdata1, tdata2)` of each slot, and `dcsr`, in one MI transaction.

        One serialized transaction for the whole window, not one round trip per register or slot.
        `reg <name> force` makes OpenOCD read the CSR from the hart instead of its register cache,
        which a trigger hit or a reset can make stale. `tselect` is read back because writing an
        index that the hardware does not implement leaves a different value selected (RISC-V debug
        specification).
        """
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

    def _check_armed(self, trigger: ReadTrigger, control: int, address: int, *, hit: bool = False):
        """Fail unless the slot holds `trigger`, armed.

        Compares the control bits that this adapter wrote, without the read-only `maskmax` field.
        `HIT` is allowed only where the caller expects a match.
        """
        expected = self.MCONTROL | (MControlFlag.HIT if hit else 0)
        if control & MCONTROL_CONTROL_MASK != expected or address != trigger.address:
            raise RuntimeError(
                f"C3 trigger changed/stale: pc={self._pc}, slot={trigger.slot}, "
                f"tdata1={control:#x}, tdata2={address:#x}, expected={expected:#x}"
            )

    def _set_triggers(self, triggers: list[ReadTrigger], enabled: bool):
        """Arm or disable `triggers`, and verify each slot by readback.

        `tdata1` = 0 (type 0, no trigger) disables a slot. The C3 keeps `tdata2`, which the readback
        checks, so re-arming only rewrites `tdata1`.
        """
        value = self.MCONTROL if enabled else 0
        self._monitor("; ".join(f"reg tselect {t.slot}; reg tdata1 {value:#x}" for t in triggers))
        states, _ = self._read_registers([t.slot for t in triggers])
        for trigger in triggers:
            control, address = states[trigger.slot]
            if enabled:
                self._check_armed(trigger, control, address)
                trigger.arm_validated = True
            elif control & MCONTROL_ACCESS_MASK or address != trigger.address:
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
        # GDB resolves the configured expression (e.g. `&buf[3]`) to the byte address that the
        # trigger compares against.
        result, _ = self._command(
            f"-data-evaluate-expression {json.dumps('(unsigned int)(' + address + ')')}"
        )
        payload = self._payload(result)
        if "value" not in payload:
            raise RuntimeError(f"C3 address evaluation returned no value: {result}")
        watch_address = int(payload["value"], 0)
        offset = len(self._triggers)
        slot = self.trigger_slot + offset
        states, dcsr = self._read_registers([slot])
        control, old_address = states[slot]
        if control & MCONTROL_ACCESS_MASK:
            raise RuntimeError(f"C3 slot {slot} already has an active owner")
        # With `dcsr.stepie` = 1 an interrupt could run during each single step, and the handler's
        # instructions and loads would enter the trace.
        if dcsr & DCSRMask.STEPIE:
            raise RuntimeError("C3 requires dcsr.stepie=0 (interrupts masked during stepping)")
        if not self._triggers:
            # The temporary entry breakpoint has fired and released its slot. Reserve only now so
            # CGI can use all eight slots after reaching entry. Later exit/finish breakpoints must
            # stay outside this raw window. `riscv reserve_trigger N on` stops OpenOCD from using
            # slot N for the breakpoints and watchpoints that GDB asks it to insert.
            window = range(self.trigger_slot, self.trigger_slot + self.watchpoint_count)
            self._monitor("; ".join(f"riscv reserve_trigger {index} on" for index in window))
        watchpoint_id = f"{self.WATCHPOINT_PREFIX}{slot}"
        trigger = ReadTrigger(slot, watch_address, offset, control, old_address)
        self._triggers[watchpoint_id] = trigger  # Reserve before writes for partial-init cleanup.
        try:
            # Disable the slot before changing `tdata2`, so it never matches a half-written address;
            # `_set_triggers` then arms and verifies it.
            self._monitor(f"reg tselect {slot}; reg tdata1 0; reg tdata2 {watch_address:#x}")
            self._set_triggers([trigger], True)
        except BaseException:
            self._release_slot(watchpoint_id)
            raise
        logging.info("C3 owns slot %d at %#x (window offset %d)", slot, watch_address, offset)
        return watchpoint_id

    def _wait_stop(self) -> GDBResponse:
        """Return the next stop record within `timeout`, from the queue or from GDB.

        `_command` queues every record that is not its own result, so a stop may already be waiting;
        the queue is searched before reading more.
        """
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            for i, response in enumerate(self._pending):
                if self.is_stop_message(response):
                    self._pending.pop(i)
                    self._halted = True
                    payload = self._payload(response)
                    self._pc = payload.get("frame", {}).get("addr", "unknown")
                    return response
                if response.get("type") == "result" and response.get("message") == "error":
                    raise RuntimeError(f"C3 asynchronous command failed: {response}")
            self._pending.extend(self._read_responses())
        raise TimeoutError(f"C3 stop timeout: pc={self._pc}, slot={self.trigger_slot}")

    def _step_stop(self) -> GDBResponse:
        self._halted = False
        self._command("-exec-step-instruction")
        stop = self._wait_stop()
        # A step that lands on the exit breakpoint is reported as its hit; the tracer checks the
        # breakpoint number and ends the window.
        reason = self._payload(stop).get("reason")
        if reason not in {MIReason.END_STEPPING_RANGE, MIReason.BREAKPOINT_HIT}:
            raise RuntimeError(f"Unexpected C3 step stop: {stop}")
        return stop

    @override
    def step_instruction(self):
        self._step(report=True)

    def _step(self, *, report: bool):
        """Execute one instruction, retiring before-load trigger halts.

        Every armed trigger has `timing` = before: a matching load halts the hart before it
        executes, with the pc unchanged and `dcsr.cause` = trigger. To let the load run, the
        triggers that matched are disabled and the instruction is stepped again; they are re-armed
        once it has retired.

        `report=False` retires reads without exposing them to the tracer.
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("C3 logical step needs a halted target and owned triggers")
        # No pre-step readback: the previous step, finish, or arming already validated every
        # trigger, and stack requests do not write CSRs.
        triggers = list(self._triggers.values())
        slots = [t.slot for t in triggers]
        before_pc = self._pc
        observed: dict[int, ReadTrigger] = {}
        # Each before-load halt must reveal at least one new hardware match. Keep unmatched triggers
        # armed during recovery; never infer wide-load byte hits from address arithmetic. At most N
        # hits plus one retirement.
        for _ in range(len(triggers) + 1):
            stop = self._step_stop()
            states, dcsr = self._read_registers(slots)
            hits = []
            for trigger in triggers:
                control, address = states[trigger.slot]
                if trigger.slot in observed:
                    if (
                        control & (MCONTROL_ACCESS_MASK | MControlFlag.HIT)
                        or address != trigger.address
                    ):
                        raise RuntimeError(
                            f"C3 disabled trigger changed: slot={trigger.slot}, {states}"
                        )
                else:
                    hit = bool(control & MControlFlag.HIT)
                    self._check_armed(trigger, control, address, hit=hit)
                    if hit:
                        hits.append(trigger)
            cause = (dcsr & DCSRMask.CAUSE) >> DCSR_CAUSE_OFFSET
            if dcsr & DCSRMask.STEPIE:
                raise RuntimeError("C3 interrupts became enabled during stepping")
            if not hits and (
                cause == DCSRCause.STEP
                or (
                    cause == DCSRCause.TRIGGER
                    and self._payload(stop).get("reason") == MIReason.BREAKPOINT_HIT
                )
            ):
                # Managed instruction breakpoints also use RISC-V triggers. The shared tracer
                # validates their breakpoint number.
                break
            if cause != DCSRCause.TRIGGER or not hits or self._pc != before_pc:
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
        # Report each read as GDB reports a watchpoint: a stop record before the successor's stop.
        # `offset` is the byte index within this window.
        for trigger in sorted(observed.values(), key=lambda t: t.offset) if report else ():
            self._pending.append(
                {
                    "type": "notify",
                    "message": "stopped",
                    "payload": {
                        "reason": MIReason.READ_WATCHPOINT_TRIGGER,
                        "offset": trigger.offset,
                    },
                }
            )
        self._pending.append(stop)

    @override
    def request_stacktrace(self):
        """Request the stack; the tracer reads the result from `get_gdb_responses`, as it does
        for the other backends."""
        result, _ = self._command("-stack-list-frames")
        if not self._payload(result).get("stack"):
            raise RuntimeError("C3 returned an empty stack")
        self._pending.append(result)

    @override
    def set_temporary_breakpoint(self, breakpoint_address):
        """Insert a temporary hardware breakpoint and return its GDB number.

        `*0x...` is a code address; anything else is a GDB location (function or `file:line`). `-t`
        deletes the breakpoint once hit. `-h` asks for a hardware breakpoint, a trigger slot, so no
        `ebreak` is written into code that runs from flash.
        """
        location = (
            "*" + breakpoint_address if breakpoint_address.startswith("0x") else breakpoint_address
        )
        result, _ = self._command(f"-break-insert -t -h {json.dumps(location)}")
        payload = self._payload(result)
        if "bkpt" not in payload:
            raise RuntimeError(f"C3 breakpoint insertion returned no breakpoint: {result}")
        return payload["bkpt"]["number"]

    @override
    def step_out_of_function(self):
        """GDB `finish`, as the paper skips ignored functions (Section 4.1).

        The read triggers stay armed while the function runs, so a read inside it halts before the
        load. That read is retired but not recorded, and the tracer resumes skipping from there.
        This matches the authors' published STM32 traces (`evaluation/stm32_applications`): bytes
        read only by the skipped `strlen` never appear in them.
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("C3 finish needs a halted target and owned triggers")
        # `finish` runs to the caller. GDB inserts breakpoints at the return address and at
        # `_Unwind_DebugHook` (C++ exceptions); both take trigger slots outside the reserved read
        # window. If no slot is free, GDB fails the command and `_command` raises.
        self._halted = False
        self._command("-exec-finish")
        stop = self._wait_stop()
        payload = self._payload(stop)
        # Classify the stop by the hardware state (`dcsr.cause` and each trigger's `HIT` bit), not
        # by GDB's reason alone: GDB does not know the raw triggers.
        triggers = list(self._triggers.values())
        states, dcsr = self._read_registers([t.slot for t in triggers])
        cause = (dcsr & DCSRMask.CAUSE) >> DCSR_CAUSE_OFFSET
        hit = False
        for trigger in triggers:
            control, address = states[trigger.slot]
            self._check_armed(trigger, control, address, hit=bool(control & MControlFlag.HIT))
            hit |= bool(control & MControlFlag.HIT)
        if hit:
            # A load trigger halts in debug mode, so any other cause leaves the hit unexplained.
            if cause != DCSRCause.TRIGGER:
                raise RuntimeError(f"Unexplained C3 finish stop: dcsr={dcsr:#x}, {stop}")
            # The load has not executed yet; stepping re-fires and retires it.
            self._step(report=False)
            return
        reason = payload.get("reason")
        # GDB labels a finish only if the finished function has debug info
        # (`finish_command_fsm::should_stop`). ROM routines have symbols but no DWARF, so their
        # return-breakpoint stop arrives unlabelled. A trigger halt with no read hit is that
        # breakpoint. The tracer accepts a stop without a reason while a finish is pending.
        unlabelled_return = (
            reason is None
            and cause == DCSRCause.TRIGGER
            and payload.get("frame", {}).get("func") != "_Unwind_DebugHook"
        )
        # As in `_step_stop`: code run by the skipped function can reach the exit breakpoint; the
        # tracer checks its number and ends the window.
        exit_hit = reason == MIReason.BREAKPOINT_HIT and cause == DCSRCause.TRIGGER
        if reason != MIReason.FUNCTION_FINISHED and not unlabelled_return and not exit_hit:
            raise RuntimeError(f"Unexpected C3 finish stop: dcsr={dcsr:#x}, {stop}")
        self._pending.append(stop)

    def _release_slot(self, watchpoint_id: str) -> None:
        """Disable the slot and restore its previous contents.

        Two verified writes: the slot is disabled first, so it is never armed with a mix of old and
        new values.
        """
        trigger = self._triggers[watchpoint_id]
        # Force-disable a reserved slot even if initialization failed mid-write.
        self._monitor(f"reg tselect {trigger.slot}; reg tdata1 0")
        states, _ = self._read_registers([trigger.slot])
        if states[trigger.slot][0] & MCONTROL_ACCESS_MASK:
            raise RuntimeError(f"C3 trigger {trigger.slot} cleanup did not disable: {states}")
        trigger.arm_validated = False
        self._monitor(
            f"reg tselect {trigger.slot}; reg tdata2 {trigger.previous_address:#x}; "
            f"reg tdata1 {trigger.previous_control:#x}"
        )
        states, _ = self._read_registers([trigger.slot])
        restored, restored_address = states[trigger.slot]
        if restored & MCONTROL_ACCESS_MASK or restored_address != trigger.previous_address:
            raise RuntimeError(
                f"C3 trigger {trigger.slot} cleanup did not restore the inactive slot"
            )
        del self._triggers[watchpoint_id]
        logging.info("C3 released slot %d", trigger.slot)

    def _clear_triggers(self):
        """Release every owned trigger; all are attempted before any failure is raised."""
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
        """Delete a GDB breakpoint, or release a raw trigger by its `WATCHPOINT_PREFIX` id."""
        if not breakpoint_id.startswith(self.WATCHPOINT_PREFIX):
            self._command(f"-break-delete {breakpoint_id}")
            return
        trigger = self._triggers.get(breakpoint_id)
        if trigger is None:
            return
        # An armed slot must still hold this adapter's trigger. Otherwise OpenOCD or GDB has taken
        # it, and writing it would break their breakpoint.
        if trigger.arm_validated:
            states, _ = self._read_registers([trigger.slot])
            control, address = states[trigger.slot]
            if control & MCONTROL_ACCESS_MASK:
                self._check_armed(trigger, control, address, hit=bool(control & MControlFlag.HIT))
            elif address not in {trigger.previous_address, trigger.address}:
                raise RuntimeError("C3 slot changed owner during cleanup; refusing to overwrite")
        self._release_slot(breakpoint_id)

    @override
    def continue_execution(self):
        """Resume the target; refused while read triggers are armed.

        An armed raw trigger would halt the hart on the next matching load outside tracing, with
        nothing to retire it: the firmware would stop answering the serial connection.
        """
        if self._triggers:
            raise RuntimeError("Release C3 data triggers before continuing outside the parser")
        self._command("-exec-continue")
        self._halted = False

    @override
    def get_gdb_responses(self) -> list[dict]:
        """Return queued records first, then new ones, so the tracer sees events in the order GDB
        sent them."""
        responses = self._pending
        self._pending = []
        responses.extend(cast(list[GDBResponse], super().get_gdb_responses()))
        for response in responses:
            if self.is_stop_message(response):
                payload = self._payload(response)
                if "frame" in payload:
                    self._halted = True
                    self._pc = payload["frame"].get("addr", "unknown")
        # The shared `SUTInstance` interface still exposes untyped dictionaries.
        return cast(list[dict], responses)

    @override
    def wait_for_any_stop_message(self) -> dict:
        # Preserve the shared `SUTInstance` return contract at this boundary.
        return cast(dict, self._wait_stop())

    @override
    def wait_for_any_gdb_response(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            responses = self.get_gdb_responses()
            if responses:
                return responses
            time.sleep(self.POLL_SEC)
        raise TimeoutError("C3 response timeout")

    def _interrupt(self) -> None:
        """Stop the running target.

        GDB's MI runs synchronously here: while the target runs, GDB reads no command,
        `-exec-interrupt` included. On the board, both `-exec-interrupt` and `monitor reset halt`
        timed out on a running target. SIGINT to the GDB process works as the CLI's Ctrl-C does: GDB
        asks OpenOCD to halt the hart and reports the stop.
        """
        process = self.gdb_controller.gdb_process
        if process is None:
            raise RuntimeError("C3 cannot interrupt the target: GDB is not running")
        process.send_signal(signal.SIGINT)
        self._wait_stop()

    @override
    def reset(self) -> None:
        """Reset the target and leave it halted before the firmware runs.

        Called by `__enter__`, and by `SUTConnection` after a serial reconnect. A reconnect during
        evaluation resets a running target that owns no triggers, so it is interrupted first.
        """
        if not self._halted:
            self._interrupt()
        # Release owned read triggers through the checked path first.
        self._clear_triggers()
        # OpenOCD resets the target and halts it before the firmware runs. GDB's register cache
        # still describes the old state, so flush it (`flushregs`), and drop stop records from
        # before the reset.
        self._monitor("reset halt")
        self._command('-interpreter-exec console "flushregs"')
        self._pending.clear()
        self._halted = True

    def _start_gdb_server(self):
        """Retry OpenOCD initialization while native USB/JTAG returns after an EN reset.

        Only the UART bridge resets the chip through EN. The USB-Serial/JTAG port resets it through
        the controller, which stayed connected in the recorded runs; the retry still covers a target
        that is not yet ready for examination.
        """
        c3 = self.config["GDB"]["esp32c3"]
        interval = c3.get("startup_retry_interval", 0.2)
        deadline = time.monotonic() + self.timeout
        # OpenOCD runs `-c` commands in order, so the marker follows `init` and the GDB listener.
        # `init` also returns when target examination fails (openocd-esp32, `src/openocd.c`,
        # `handle_init_command`), and a GDB attach then aborts OpenOCD. The state check raises an
        # error first; OpenOCD exits on it (`openocd_thread`), and the loop below retries.
        # `was_examined` is an internal target command, absent from the OpenOCD manual; OpenOCD's
        # reset procedure uses it the same way (`src/target/startup.tcl`, `ocd_process_reset_inner`).
        # A temporary file avoids blocking on a full pipe and retains failure diagnostics.
        marker = "GDBMINER_C3_READY"
        command = [
            *self.gdb_server_path_with_args,
            "-c",
            (
                'init; if {![[target current] was_examined]} {error "target examination failed"}; '
                f"echo {marker}"
            ),
        ]
        last_output = ""
        while time.monotonic() < deadline:
            with tempfile.TemporaryFile(mode="w+b") as output:
                self.gdb_server = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
                while time.monotonic() < deadline:
                    last_output = os.pread(output.fileno(), 1024 * 1024, 0).decode(errors="replace")
                    if marker in last_output and self.gdb_server.poll() is None:
                        logging.info("C3 OpenOCD initialized: %s", last_output.strip())
                        return
                    if self.gdb_server.poll() is not None:
                        break
                    time.sleep(min(interval, max(0, deadline - time.monotonic())))
                self._stop_gdb_server()
                del self.gdb_server  # __exit__ must not stop a failed attempt again.
                logging.warning("C3 OpenOCD startup retry: %s", last_output.strip())
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"C3 OpenOCD startup timed out after {self.timeout}s: {last_output}")

    def _reset_and_resume(self) -> None:
        """Reset callback for a serial reconnect when `reset_on_connect` is set.

        Tracing needs the halt after `reset` to insert its entry breakpoint. A reconnect happens
        only while inputs are tested on a running target, so it is resumed: a halted target would
        leave every later input unanswered.
        """
        self.reset()
        self.continue_execution()

    @override
    def init_sut_connection(self):
        # Also skips the GDB reset when the serial connection reconnects after a timeout.
        return SUTConnection(
            self.config, self._reset_and_resume if self.reset_on_connect else lambda: None
        )

    @override
    def __enter__(self):
        try:
            # Open the serial port first: with `rts` and `reset_pulse`, it restarts the chip. Over
            # the UART bridge the pulse drives EN, and the native USB-JTAG device re-enumerates;
            # `_start_gdb_server` retries until OpenOCD reaches the JTAG function again.
            self.connection = self.init_sut_connection()
            self._start_gdb_server()
            self.init_gdb_controller()
            # Attaching halts the hart; wait for that stop record.
            self._command(f"-target-select extended-remote {self.gdb_server_address}")
            self.wait_for_any_stop_message()
            if self.reset_on_connect:
                self.reset()
            if self.config["GDB"]["esp32c3"].get("breakpoint_always_inserted", False):
                # Same breakpoints, written once: by default GDB removes every breakpoint after each
                # stop and re-inserts it before the next `stepi` (`infrun.c`,
                # `maybe_remove_breakpoints`).
                self._command("-gdb-set breakpoint always-inserted on")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    @override
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the read triggers while GDB and OpenOCD still run, then close the serial port,
        GDB and OpenOCD in that order. Each step runs even if an earlier one fails."""
        try:
            if self._triggers:
                if not self._halted:
                    self._interrupt()
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
                        self._stop_gdb_server()
