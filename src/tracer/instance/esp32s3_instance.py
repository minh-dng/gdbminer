# ESP32-S3 hardware read observation through stock Espressif OpenOCD (Xtensa LX7).
# SPDX-License-Identifier: AGPL-3.0

import json
import logging
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast, override

from util import Config

from .esp32_instance import ESP32Instance, GDBResponse
from .esp32s3_debug import (
    DATA_BREAKPOINT_COUNT,
    DBREAKC_READ_BYTE,
    DEBUGCAUSE_DBNUM_MASK,
    DEBUGCAUSE_DBNUM_SHIFT,
    ENTRY_BYTE0,
    MASK_ROM,
    PRO_CPU_PRID,
    WATCH_MIN_DISTANCE,
    DebugCause,
    is_windowed_call,
    jx_register,
    l32r_register,
    load_size,
    load_width,
)
from .hardware_instance import MIReason

_ATTACH_ATTEMPTS = 3
"""Attaches tried before giving up, with a USB reset between two attempts."""


@dataclass
class _DataBreak:
    """One read watchpoint owned by `ESP32S3Instance`.

    GDB inserts it and OpenOCD writes it to a DBREAK pair; the adapter only reads that pair back.
    """

    number: str
    """GDB watchpoint number, also the id handed to the tracer."""
    index: int
    """Index of the watched byte within the current watchpoint window."""
    address: int
    """Byte address that the watchpoint watches (`DBREAKA`)."""
    slot: int
    """DBREAK pair that OpenOCD chose."""


class ESP32S3Instance(ESP32Instance[_DataBreak]):
    """Read the debug unit after every single step, as the paper does on ARMv7 (Section 4.1).

    Each core has two instruction breakpoints (IBREAK) and two data breakpoints (DBREAK), separate
    units. GDB manages the read watchpoints, and OpenOCD writes them to DBREAK. A matching load
    halts the core *before* it executes, but OpenOCD reports that halt as an ordinary single step
    (`xtensa_do_step`): GDB shows `end-stepping-range` with an unchanged pc. `DEBUGCAUSE` keeps the
    cause, `DB` set and `DBNUM` naming one slot. On the next step OpenOCD disables every DBREAK,
    executes the load and re-arms them. This adapter reads `DEBUGCAUSE` after every step, reports
    the read on the load's trace entry, and executes the load with that next step.

    `DBNUM` names one slot only, so a load covering both watched bytes would lose one read. The
    adapter rejects watched bytes closer than `WATCH_MIN_DISTANCE`, and the TOML sets
    `GDB.esp32s3.watchpoint_min_distance` so that the tracer never asks for them. Every hit must
    come from a scalar load of at most 4 bytes.

    OpenOCD debugs core 0 only (`ESP_ONLYCPU 1`), and the firmware runs `loop()` on core 0
    (`LoopCore=0`). `ESP_FLASH_SIZE 0` makes every breakpoint a hardware breakpoint, so a third
    breakpoint fails instead of rewriting flash.
    """

    CHIP = "S3"
    CONFIG_TABLE = "esp32s3"
    _MAX_HALTS_PER_INSTRUCTION = 6
    """Halts before one instruction completes: register-window exceptions, each slot's read, and
    the step that executes the load."""
    _code: ClassVar[dict[tuple[str, int], bytes]] = {}
    """First three code bytes by (ELF, address); code does not change during a run."""

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config, input_file)
        if not 1 <= self.watchpoint_count <= DATA_BREAKPOINT_COUNT:
            raise ValueError(
                f"S3 hardware observation requires 1 <= watchpoint_count <= {DATA_BREAKPOINT_COUNT}"
            )
        # GDB inserts the watchpoints, so they must stay in DBREAK while the core is halted: every
        # step reads them back. GDB would otherwise remove them at each stop.
        self.breakpoint_always_inserted = True
        # After OpenOCD's `reset halt`, the USB device re-enumerated on the board and the open serial
        # port failed ("Device not configured"). The serial reset pulse restarts the firmware
        # instead, at start-up and after a reconnect.
        if self.chip_config.get("reset_on_connect", False):
            raise ValueError("S3 reset_on_connect must be false: a reset closes the serial port")
        self.reset_on_connect = False
        self.startup_delay = self.chip_config.get("startup_delay", 3.0)
        """Seconds between the serial reset and OpenOCD's start (`GDB.esp32s3.startup_delay`).

        Opening the JTAG function while the firmware was still starting its USB serial port wedged
        the USB-Serial/JTAG device in 1 of 17 attaches with 1 s; 3 s passed 40 of 40.
        """
        self.usb_reset_command = self.chip_config.get("usb_reset_command", "")
        """Command that resets the board's USB device before the next attach attempt
        (`GDB.esp32s3.usb_reset_command`); empty to attach once."""
        self._state: dict[str, int] = {}
        """Debug registers at the current halt, from `_debug_state`."""

    def _registers(self, *names: str) -> dict[str, int]:
        """Read registers from OpenOCD's register cache in one transaction.

        OpenOCD refetches every register after each halt (`xtensa_fetch_all_regs`), so the cache
        describes the current halt without more JTAG traffic. OpenOCD returns only the last Tcl
        result of a command list, so all values come back as one Tcl `list`; `echo` would also print
        every value into OpenOCD's own log, about 280 bytes per step.
        """
        commands = " ".join(f"[reg {name}]" for name in names)
        _, text = self._command(
            f"-interpreter-exec console {json.dumps('monitor list ' + commands)}"
        )
        values = dict(re.findall(r"\b(\w+) \(/32\): (0x[0-9a-fA-F]+)", text))
        if missing := [name for name in names if name not in values]:
            raise RuntimeError(f"Missing S3 registers {missing}: {text}")
        return {name: int(values[name], 16) for name in names}

    def _debug_state(self) -> dict[str, int]:
        """Read and keep the registers that every step checks."""
        names = ["debugcause", "windowstart", "lbeg", "lend", "lcount"]
        for slot in range(DATA_BREAKPOINT_COUNT):
            names += [f"dbreaka{slot}", f"dbreakc{slot}"]
        self._state = self._registers(*names)
        return self._state

    def _code_at(self, address: int) -> bytes:
        """First three code bytes at `address`, enough for every instruction decoded here."""
        key = (self.elf_file, address)
        if key not in self._code:
            result, _ = self._command(f"-data-read-memory-bytes {address:#x} 3")
            payload = cast(dict[str, Any], self._payload(result))
            self._code[key] = bytes.fromhex(payload["memory"][0]["contents"])
        return self._code[key]

    def _check_armed(self, state: dict[str, int]):
        """Fail unless every owned DBREAK pair still holds its watchpoint.

        The firmware's FreeRTOS stack guard can rewrite DBREAK1 (see `_rearm`).
        """
        for wp in self._triggers.values():
            control, address = state[f"dbreakc{wp.slot}"], state[f"dbreaka{wp.slot}"]
            if control != DBREAKC_READ_BYTE or address != wp.address:
                raise RuntimeError(
                    f"S3 DBREAK{wp.slot} changed: pc={self._pc}, "
                    f"dbreakc={control:#x}, dbreaka={address:#x}, expected {wp.address:#x}"
                )

    @override
    def set_watchpoint_and_get_id(self, address, watchpoint_type) -> str:
        if not self._halted or len(self._triggers) >= self.watchpoint_count:
            raise RuntimeError("Set S3 watchpoints within the budget at the halted entry")
        if not self._triggers:
            # `ESP_ONLYCPU 1` exposes core 0 only; the parser must run there (`LoopCore=0`).
            prid = self._registers("prid")["prid"]
            if prid != PRO_CPU_PRID:
                raise RuntimeError(f"S3 entry stop on core PRID {prid:#x}, expected core 0")
        watch_address = self._address(address)
        # One halt names one slot: two watched bytes read by one load would lose a read. Checked
        # here whatever window the caller chose.
        for wp in self._triggers.values():
            if abs(wp.address - watch_address) < WATCH_MIN_DISTANCE:
                raise ValueError(
                    f"S3 watchpoints {wp.address:#x} and {watch_address:#x} are closer than "
                    f"{WATCH_MIN_DISTANCE} bytes; set GDB.esp32s3.watchpoint_min_distance"
                )
        # `-location` watches the memory the expression names once evaluated. Without it, GDB would
        # delete the watchpoint when the frame of a local such as `data` returns, and would also
        # watch `data` itself. MI's -break-watch has no such option. The type of the expression
        # sets the watched size; a type wider than a byte arms a wider data breakpoint, which the
        # slot check below rejects. With `breakpoint always-inserted`, OpenOCD writes the DBREAK
        # pair now.
        command = f"rwatch -location *{watchpoint_type}({address})"
        self._command(f"-interpreter-exec console {json.dumps(command)}")
        result, _ = self._command("-data-evaluate-expression $bpnum")
        number = self._payload(result).get("value", "")
        state = self._debug_state()
        used = {wp.slot for wp in self._triggers.values()}
        slots = [
            slot
            for slot in range(DATA_BREAKPOINT_COUNT)
            if slot not in used
            and state[f"dbreakc{slot}"] == DBREAKC_READ_BYTE
            and state[f"dbreaka{slot}"] == watch_address
        ]
        if len(slots) != 1:
            self._command(f"-break-delete {number}")
            raise RuntimeError(f"S3 watchpoint {number} at {watch_address:#x} not armed: {state}")
        index = len(self._triggers)
        self._triggers[number] = _DataBreak(number, index, watch_address, slots[0])
        logging.info("S3 DBREAK%d reads %#x (window index %d)", slots[0], watch_address, index)
        return number

    def _step_and_read(self) -> tuple[GDBResponse, dict[str, int], int]:
        """Step once, then read and check the debug registers; return the stop, them and the pc."""
        stop = self._step_stop()
        state = self._debug_state()
        self._check_armed(state)
        return stop, state, int(self._pc, 16)

    @override
    def step_instruction(self):
        """Execute the instruction at the pc; report its reads, then its successor.

        A step can end with the pc unchanged although the instruction has not executed:

        - `DEBUGCAUSE.DB`: a load halted before reading a watched byte. Record the read; OpenOCD
          disables the DBREAKs for the next step.
        - A register-window exception (WindowOverflow, or WindowUnderflow at `retw`). With
          interrupts masked, OpenOCD steps through the handler, which returns to re-execute the
          instruction; `WindowStart` shows the spill or refill.

        Stepping again keeps one trace entry per executed instruction, as on the single-window
        STM32 and C3. A windowed call into a ROM jump stub is followed to the routine's `ENTRY`, as
        if it were called directly (`_enter_routine`).
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("S3 step needs a halted target and armed watchpoints")
        before_pc = int(self._pc, 16)
        before = self._state
        code = self._code_at(before_pc)
        hits: list[_DataBreak] = []
        window_exception = False
        for _ in range(self._MAX_HALTS_PER_INSTRUCTION):
            stop, state, pc = self._step_and_read()
            cause = state["debugcause"]
            # A step onto the exit breakpoint can report IBREAK instead of ICOUNT; the tracer checks
            # the breakpoint number.
            completed = cause & DebugCause.IC or (
                cause & DebugCause.IB
                and self._payload(stop).get("reason") == MIReason.BREAKPOINT_HIT
            )
            if cause & DebugCause.DB:
                hit = self._hit(before_pc, pc, code, cause)
                if hit in hits and not window_exception:
                    raise RuntimeError(f"S3 DBREAK{hit.slot} hit twice at {before_pc:#x}")
                if hit not in hits:  # A re-hit after a window exception is the same read.
                    hits.append(hit)
            elif not completed:
                raise RuntimeError(f"Unexplained S3 halt at {before_pc:#x}: {state}")
            elif pc == before_pc and state["windowstart"] != before["windowstart"]:
                logging.debug("S3 register-window exception at %#x", before_pc)
                before = state
                window_exception = True
            else:
                break
        else:
            raise RuntimeError(f"S3 instruction at {before_pc:#x} did not complete")
        if hits:
            # The load executed exactly once: next address, or LBEG at a zero-overhead loop end.
            follows = before_pc + load_size(code)
            if pc != follows and not (follows == state["lend"] and pc == state["lbeg"]):
                raise RuntimeError(f"S3 load at {before_pc:#x} retired to {pc:#x}: {state}")
        if is_windowed_call(code):
            stop = self._enter_routine(stop, pc)
        # Report each read as GDB reports a watchpoint: a stop record before the successor's stop.
        # `offset` is the byte index within this window.
        for hit in hits:
            self._pending.append(
                {
                    "type": "notify",
                    "message": "stopped",
                    "payload": {"reason": MIReason.READ_WATCHPOINT_TRIGGER, "offset": hit.index},
                }
            )
        self._pending.append(stop)

    def _hit(self, load_pc: int, pc: int, code: bytes, cause: int) -> _DataBreak:
        """The watchpoint that halted a load at `load_pc`; fail unless the halt is explained."""
        slot = cause >> DEBUGCAUSE_DBNUM_SHIFT & DEBUGCAUSE_DBNUM_MASK
        hit = [wp for wp in self._triggers.values() if wp.slot == slot]
        width = load_width(code)
        # Watched bytes are at least 4 apart, so a load of at most 4 bytes matches one slot.
        if pc != load_pc or len(hit) != 1 or width is None:
            raise RuntimeError(
                f"Unexplained S3 DBREAK halt at {load_pc:#x}->{pc:#x}, "
                f"code {code.hex()}, debugcause {cause:#x}"
            )
        logging.info(
            "S3 hardware read pc=%#x width=%d address=%#x slot=%d index=%d",
            load_pc,
            width,
            hit[0].address,
            slot,
            hit[0].index,
        )
        return hit[0]

    def _enter_routine(self, stop: GDBResponse, pc: int) -> GDBResponse:
        """Follow a ROM jump stub (`l32r aN, <routine>; jx aN`) to the routine's `ENTRY`.

        The S3 reaches ROM routines (`strlen`, `strncmp`, `memcpy`, ...) through such stubs. A stub
        has no `ENTRY`, so GDB unwinds it wrongly: it shows the caller's stack and takes the wrong
        return address for `finish`. Recording it would also add the same stub to every caller's
        control-flow graph, which makes repeated calls look like a loop. Its two instructions load a
        ROM literal and jump; they are executed but not reported. Any other call target without
        `ENTRY` stops the trace.
        """
        if self._code_at(pc)[0] == ENTRY_BYTE0:
            return stop
        load, jump = self._code_at(pc), self._code_at(pc + 3)
        register = l32r_register(load)
        is_stub = pc in MASK_ROM and register is not None and jx_register(jump) == register
        if not is_stub:
            raise RuntimeError(f"S3 call target {pc:#x} has no ENTRY and is no ROM jump stub")
        for expected in (pc + 3, None):
            stop, state, pc = self._step_and_read()
            if state["debugcause"] != DebugCause.IC or expected not in (None, pc):
                raise RuntimeError(f"Unexpected S3 halt in a ROM jump stub at {pc:#x}: {state}")
        if self._code_at(pc)[0] != ENTRY_BYTE0:
            raise RuntimeError(f"S3 ROM jump stub jumped to {pc:#x}, which has no ENTRY")
        return stop

    @override
    def step_out_of_function(self):
        """GDB `finish`, as the paper skips ignored functions (Section 4.1).

        Reads by the skipped function are not recorded, as on the C3: the authors' published STM32
        traces never show bytes read only by the skipped `strlen`. GDB treats Xtensa watchpoints as
        nonsteppable: on a watchpoint halt during `finish` it removes the watchpoints, steps over
        the load and reports `read-watchpoint-trigger`. That stop is passed on as
        `end-stepping-range`, after which the tracer asks for the stack and keeps skipping. GDB
        inserts the watchpoints again at the next resume, writing both DBREAK pairs afresh, and the
        next step checks them.
        """
        if not self._triggers or not self._halted:
            raise RuntimeError("S3 finish needs a halted target and armed watchpoints")
        self._halted = False
        self._command("-exec-finish")
        stop = self._wait_stop()
        payload = self._payload(stop)
        state = self._debug_state()
        cause = state["debugcause"]
        reason = payload.get("reason")
        if reason == MIReason.READ_WATCHPOINT_TRIGGER and cause & DebugCause.IC:
            logging.info("S3 read inside a skipped function retired at %s", self._pc)
            # The watchpoints are removed here (DBREAKC reads 0), so `_rearm` must not run.
            self._pending.append(
                {
                    "type": "notify",
                    "message": "stopped",
                    "payload": {
                        "reason": MIReason.END_STEPPING_RANGE,
                        "frame": payload.get("frame", {}),
                    },
                }
            )
            return
        # The finish return breakpoint and the exit breakpoint are IBREAKs. GDB labels a finish only
        # if the finished function has debug info (`finish_command_fsm::should_stop`); ROM routines
        # have symbols but no DWARF, so their return stop arrives unlabelled. The tracer accepts a
        # stop without a reason while a finish is pending, and checks an exit breakpoint's number.
        if (
            reason not in {MIReason.FUNCTION_FINISHED, MIReason.BREAKPOINT_HIT, None}
            or not cause & DebugCause.IB
        ):
            raise RuntimeError(f"Unexpected S3 finish stop: debugcause={cause:#x}, {stop}")
        self._rearm(state)
        self._pending.append(stop)

    def _rearm(self, state: dict[str, int]):
        """Re-insert watchpoints that the firmware overwrote while the core ran freely.

        The Arduino-ESP32 SDK is built with `CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK`: every task
        switch (`vTaskSwitchContext`) writes a stack-guard watchpoint into DBREAK1. A switch happens
        at interrupt exit, which OpenOCD masks while stepping, or at a direct `vPortYield`, which
        needs no interrupt. During `finish` both can happen. Its reads are not recorded anyway, so
        re-inserting before the next step loses no observation; a change across a single step still
        stops the trace in `_step_and_read`.
        """
        for wp in self._triggers.values():
            control, address = state[f"dbreakc{wp.slot}"], state[f"dbreaka{wp.slot}"]
            if control == DBREAKC_READ_BYTE and address == wp.address:
                continue
            logging.warning(
                "S3 DBREAK%d overwritten during finish (dbreakc=%#x, dbreaka=%#x); re-inserting",
                wp.slot,
                control,
                address,
            )
            self._command(f"-break-disable {wp.number}")
            self._command(f"-break-enable {wp.number}")
        self._check_armed(self._debug_state())

    @override
    def delete_breakpoint(self, breakpoint_id):
        """Delete a GDB breakpoint or watchpoint; a watchpoint's DBREAK pair is freed with it."""
        self._command(f"-break-delete {breakpoint_id}")
        self._triggers.pop(breakpoint_id, None)

    @override
    def _start_gdb_server(self):
        """Wait `startup_delay` after the serial reset, then start OpenOCD."""
        time.sleep(self.startup_delay)
        super()._start_gdb_server()

    @override
    def __enter__(self):
        """Attach; if that fails, reset the USB device and attach again.

        OpenOCD sometimes cannot open the USB-Serial/JTAG device after a restart
        (`libusb_get_string_descriptor_ascii() failed`), and the serial port stops answering too. A
        USB port reset recovers it. Nothing has been traced yet, so a repeated attach cannot change
        a trace.
        """
        for attempt in range(1, _ATTACH_ATTEMPTS + 1):
            try:
                return super().__enter__()
            except Exception as error:
                if not self.usb_reset_command or attempt == _ATTACH_ATTEMPTS:
                    raise
                logging.warning("S3 attach attempt %d failed: %s; USB reset", attempt, error)
            # `super().__enter__` released this attempt's resources; forget them so the next
            # attempt's clean-up does not release them again.
            for name in ("connection", "gdb_controller", "gdb_server"):
                if hasattr(self, name):
                    delattr(self, name)
            subprocess.run(shlex.split(self.usb_reset_command), check=True, timeout=120)
        raise AssertionError("unreachable")
