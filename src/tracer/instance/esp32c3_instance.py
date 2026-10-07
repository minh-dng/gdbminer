# ESP32-C3 hardware read observation through stock Espressif OpenOCD.
# SPDX-License-Identifier: AGPL-3.0

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import override

from util import Config

from .esp32_instance import ESP32Instance
from .esp32c3_debug import (
    DCSR_CAUSE_OFFSET,
    HARDWARE_TRIGGER_COUNT,
    MCONTROL_ACCESS_MASK,
    MCONTROL_CONTROL_MASK,
    DCSRCause,
    DCSRMask,
    MControlFlag,
)
from .hardware_instance import MIReason


@dataclass
class _ReadTrigger:
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


class ESP32C3Instance(ESP32Instance[_ReadTrigger]):
    """Own raw read triggers; retire before-load halts without exposing them.

    OpenOCD removes *managed* watchpoints during `stepi`. Raw `mcontrol` registers remain armed.
    Never mix this path with ARM DWT polling. The C3 has eight trigger slots shared by breakpoints
    and watchpoints. Slots below `GDB.esp32c3.hardware_trigger_slot` stay free for GDB's managed
    hardware breakpoints: an exit point needs one, and each `finish` needs two (return address and
    the C++ exception hook `_Unwind_DebugHook`). The raw window is reserved in OpenOCD, so a
    breakpoint that does not fit fails to insert.
    """

    CHIP = "C3"
    CONFIG_TABLE = "esp32c3"

    _MCONTROL = (
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
    _WATCHPOINT_PREFIX = "c3-read-"
    """Prefix of the ids of raw triggers handed to the tracer.

    GDB does not know these triggers, so `delete_breakpoint` tells them apart from GDB breakpoint
    numbers.
    """

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config, input_file)
        if not 1 <= self.watchpoint_count <= HARDWARE_TRIGGER_COUNT:
            raise ValueError(
                f"C3 hardware observation requires 1 <= watchpoint_count <= {HARDWARE_TRIGGER_COUNT}"
            )
        self.trigger_slot = self.chip_config["hardware_trigger_slot"]
        """First slot of the read window (`GDB.esp32c3.hardware_trigger_slot`)."""
        if (
            self.trigger_slot < 0
            or self.trigger_slot + self.watchpoint_count > HARDWARE_TRIGGER_COUNT
        ):
            raise ValueError(
                f"C3 configured trigger window must fit slots 0..{HARDWARE_TRIGGER_COUNT - 1}"
            )

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

    def _check_armed(self, trigger: _ReadTrigger, control: int, address: int, *, hit: bool = False):
        """Fail unless the slot holds `trigger`, armed.

        Compares the control bits that this adapter wrote, without the read-only `maskmax` field.
        `HIT` is allowed only where the caller expects a match.
        """
        expected = self._MCONTROL | (MControlFlag.HIT if hit else 0)
        if control & MCONTROL_CONTROL_MASK != expected or address != trigger.address:
            raise RuntimeError(
                f"C3 trigger changed/stale: pc={self._pc}, slot={trigger.slot}, "
                f"tdata1={control:#x}, tdata2={address:#x}, expected={expected:#x}"
            )

    def _set_triggers(self, triggers: list[_ReadTrigger], enabled: bool):
        """Arm or disable `triggers`, and verify each slot by readback.

        `tdata1` = 0 (type 0, no trigger) disables a slot. The C3 keeps `tdata2`, which the readback
        checks, so re-arming only rewrites `tdata1`.
        """
        value = self._MCONTROL if enabled else 0
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
        watchpoint_id = f"{self._WATCHPOINT_PREFIX}{slot}"
        trigger = _ReadTrigger(slot, watch_address, offset, control, old_address)
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
        observed: dict[int, _ReadTrigger] = {}
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

    @override
    def delete_breakpoint(self, breakpoint_id):
        """Delete a GDB breakpoint, or release a raw trigger by its `_WATCHPOINT_PREFIX` id."""
        if not breakpoint_id.startswith(self._WATCHPOINT_PREFIX):
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
