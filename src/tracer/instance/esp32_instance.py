# Synchronous GDB/MI session with Espressif OpenOCD, shared by the ESP32 targets.
# SPDX-License-Identifier: AGPL-3.0

import json
import logging
import os
import signal
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, NotRequired, TypedDict, cast, override

from tracer.connection import SUTConnection
from util import Config

from .hardware_instance import HardwareInstance, MIReason


class _StopFrame(TypedDict, total=False):
    """Frame fields read from a stopped notification; GDB may provide others."""

    addr: str
    func: str


class _Breakpoint(TypedDict):
    """Breakpoint field read from a successful insertion result."""

    number: str


class _MIPayload(TypedDict, total=False):
    """Dictionary payload fields used here; GDB may provide others."""

    reason: str
    frame: _StopFrame
    offset: int
    value: str
    bkpt: _Breakpoint
    stack: list[_StopFrame]


class GDBResponse(TypedDict):
    """Queued MI record; payload shape depends on the GDB command or event."""

    type: str
    message: str | None
    payload: _MIPayload | str | None
    token: NotRequired[int | None]
    stream: NotRequired[str]


class ESP32Instance[Trigger](HardwareInstance, ABC):
    """Bounded GDB/MI transactions with an Espressif OpenOCD target.

    Transactions are synchronous and token-correlated; unrelated MI messages stay queued for
    `_wait_stop` and for the tracer. This keeps debug-register polling out of response
    normalization. Subclasses own the chip's read observation: they hold their read triggers in
    `_triggers`, by the id handed to the tracer, and release them in `delete_breakpoint`.
    """

    CHIP: ClassVar[str]
    """Short chip name in log and error messages, such as `C3`."""
    CONFIG_TABLE: ClassVar[str]
    """Table under `[GDB]` with the chip's settings, such as `esp32c3`."""
    _POLL_SEC = 0.001
    """Timeout of each pygdbmi read.

    pygdbmi keeps reading until the timeout expires, even after output arrives, so this is a latency
    floor on every transaction.
    """

    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config, input_file)
        self.chip_config: Config = config["GDB"][self.CONFIG_TABLE]
        """The chip's settings table, `[GDB.<CONFIG_TABLE>]`."""
        self.reset_on_connect = self.chip_config.get("reset_on_connect", True)
        """Reset the target through GDB after the attach and after a serial reconnect.

        The C3 configurations set it to true. OpenOCD's target examination halts and resumes a
        running C3, and its failed probes of absent CSRs leave register `a0` at the debug module's
        base address. A firmware that is still booting after the serial reset pulse then faults.
        The reset starts the traced boot after the examination.
        """
        self.breakpoint_always_inserted = self.chip_config.get("breakpoint_always_inserted", False)
        """Keep breakpoints inserted while the target is halted (`set breakpoint always-inserted`).

        By default GDB removes every breakpoint after each stop and re-inserts it before the next
        `stepi` (`infrun.c`, `maybe_remove_breakpoints`).
        """
        self._token = 10000
        """Last MI token used by `_command`.

        GDB echoes the token on the matching result record (`10001^done`), which separates that
        result from stop records and from the results of earlier commands.
        """
        self._pending: list[GDBResponse] = []
        """MI records read while waiting for something else, in arrival order, for `_wait_stop`
        and for the tracer (`get_gdb_responses`)."""
        self._triggers: dict[str, Trigger] = {}
        """Read triggers owned by this instance, by watchpoint id."""
        self._pc = "unknown"
        """Program counter of the last reported stop."""
        self._halted = False
        """GDB last reported the core halted. While the target runs, GDB reads no MI command (see
        `_interrupt`)."""

    @override
    def init_gdb_controller(self):
        super().init_gdb_controller()
        rom_elf = self.chip_config.get("rom_elf", "")
        if rom_elf:
            # Name built-in ROM routines so the tracer's ignore regex can match them. Symbols alone
            # do not guarantee that GDB can unwind a ROM call.
            command = "add-symbol-file " + json.dumps(
                str(Path(rom_elf).expanduser().resolve(strict=True))
            )
            self._command(f"-interpreter-exec console {json.dumps(command)}")

    def _payload(self, response: GDBResponse) -> _MIPayload:
        payload = response["payload"]
        if not isinstance(payload, dict):
            raise TypeError(f"Expected a {self.CHIP} MI dictionary payload: {response}")
        return payload

    def _read_responses(self) -> list[GDBResponse]:
        # pygdbmi is untyped; keep the assertion at the parser boundary.
        return cast(
            list[GDBResponse],
            self.gdb_controller.get_gdb_response(
                timeout_sec=self._POLL_SEC, raise_error_on_timeout=False
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
                raise TimeoutError(f"{self.CHIP} command timeout: {command}; pc={self._pc}")
            responses = self._read_responses()
            for response in responses:
                # Only the first result answers the command. An execution command that GDB aborts
                # after `^running` gets a second, `^error`, which may arrive in the same read; it
                # is queued for `_wait_stop`, as when it arrives later.
                if (
                    result is None
                    and response.get("type") == "result"
                    and response.get("token") == token
                ):
                    result = response
                elif response.get("type") in {"console", "target", "log"}:
                    streams.append(str(response.get("payload", "")))
                else:
                    self._pending.append(response)
        if result.get("message") not in {"done", "running", "connected"}:
            raise RuntimeError(
                f"{self.CHIP} command failed: {command}: {result}; {''.join(streams)}"
            )
        return result, "".join(streams)

    def _monitor(self, command: str) -> str:
        """Run `;`-separated OpenOCD commands through GDB's `monitor` and return their output.

        OpenOCD returns only the last Tcl result of a command list, so each command is wrapped in
        `echo [...]`: register reads are not lost when a transaction is batched.
        """
        commands = "; ".join(f"echo [{part.strip()}]" for part in command.split(";"))
        _, text = self._command(f"-interpreter-exec console {json.dumps('monitor ' + commands)}")
        return text

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
                    # GDB rejected the execution command before resuming the target, for example
                    # when a breakpoint finds no free trigger, so the target is still halted and
                    # `__exit__` can release the triggers without interrupting it.
                    self._pending.pop(i)
                    self._halted = True
                    raise RuntimeError(f"{self.CHIP} asynchronous command failed: {response}")
            self._pending.extend(self._read_responses())
        raise TimeoutError(f"{self.CHIP} stop timeout: pc={self._pc}")

    def _step_stop(self) -> GDBResponse:
        self._halted = False
        self._command("-exec-step-instruction")
        stop = self._wait_stop()
        # A step that lands on the exit breakpoint is reported as its hit; the tracer checks the
        # breakpoint number and ends the window.
        reason = self._payload(stop).get("reason")
        if reason not in {MIReason.END_STEPPING_RANGE, MIReason.BREAKPOINT_HIT}:
            raise RuntimeError(f"Unexpected {self.CHIP} step stop: {stop}")
        return stop

    @override
    def request_stacktrace(self):
        """Request the stack; the tracer reads the result from `get_gdb_responses`, as it does
        for the other backends."""
        result, _ = self._command("-stack-list-frames")
        if not self._payload(result).get("stack"):
            raise RuntimeError(f"{self.CHIP} returned an empty stack")
        self._pending.append(result)

    @override
    def set_temporary_breakpoint(self, breakpoint_address):
        """Insert a temporary hardware breakpoint and return its GDB number.

        `*0x...` is a code address; anything else is a GDB location (function or `file:line`). `-t`
        deletes the breakpoint once hit. `-h` asks for a hardware breakpoint, so no breakpoint
        instruction is written into code that runs from flash.
        """
        location = (
            "*" + breakpoint_address if breakpoint_address.startswith("0x") else breakpoint_address
        )
        result, _ = self._command(f"-break-insert -t -h {json.dumps(location)}")
        payload = self._payload(result)
        if "bkpt" not in payload:
            raise RuntimeError(f"{self.CHIP} breakpoint insertion returned no breakpoint: {result}")
        return payload["bkpt"]["number"]

    @abstractmethod
    @override
    def delete_breakpoint(self, breakpoint_id):
        """Delete a GDB breakpoint, or release a read trigger by the id handed to the tracer."""

    def _clear_triggers(self):
        """Release every owned trigger; all are attempted before any failure is raised."""
        errors = []
        for watchpoint_id in list(self._triggers):
            try:
                self.delete_breakpoint(watchpoint_id)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup(f"{self.CHIP} trigger cleanup failed", errors)

    @override
    def continue_execution(self):
        """Resume the target; refused while read triggers are armed.

        An armed trigger would halt the core on the next matching load outside tracing, with
        nothing to retire it: the firmware would stop answering the serial connection.
        """
        if self._triggers:
            raise RuntimeError(
                f"Release {self.CHIP} data triggers before continuing outside the parser"
            )
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
            time.sleep(self._POLL_SEC)
        raise TimeoutError(f"{self.CHIP} response timeout")

    def _interrupt(self) -> None:
        """Stop the running target.

        GDB's MI runs synchronously here: while the target runs, GDB reads no command,
        `-exec-interrupt` included. On the C3 board, both `-exec-interrupt` and `monitor reset halt`
        timed out on a running target. SIGINT to the GDB process works as the CLI's Ctrl-C does: GDB
        asks OpenOCD to halt the core and reports the stop.
        """
        process = self.gdb_controller.gdb_process
        if process is None:
            raise RuntimeError(f"{self.CHIP} cannot interrupt the target: GDB is not running")
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

        Only a UART bridge resets the chip through EN. The USB-Serial/JTAG port resets it through
        the controller, which stayed connected in the recorded C3 runs; the retry still covers a
        target that is not yet ready for examination.
        """
        interval = self.chip_config.get("startup_retry_interval", 0.2)
        deadline = time.monotonic() + self.timeout
        # OpenOCD runs `-c` commands in order, so the marker follows `init` and the GDB listener.
        # `init` also returns when target examination fails (openocd-esp32, `src/openocd.c`,
        # `handle_init_command`), and a GDB attach then aborts OpenOCD. The state check raises an
        # error first; OpenOCD exits on it (`openocd_thread`), and the loop below retries.
        # `was_examined` is an internal target command, absent from the OpenOCD manual; OpenOCD's
        # reset procedure uses it the same way (`src/target/startup.tcl`, `ocd_process_reset_inner`).
        # A temporary file avoids blocking on a full pipe and retains failure diagnostics.
        marker = f"GDBMINER_{self.CHIP}_READY"
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
            with tempfile.TemporaryFile() as output:
                self.gdb_server = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
                while time.monotonic() < deadline:
                    last_output = os.pread(output.fileno(), 1024 * 1024, 0).decode(errors="replace")
                    if marker in last_output and self.gdb_server.poll() is None:
                        logging.info("%s OpenOCD initialized: %s", self.CHIP, last_output.strip())
                        return
                    if self.gdb_server.poll() is not None:
                        break
                    time.sleep(min(interval, max(0, deadline - time.monotonic())))
                self._stop_gdb_server()
                del self.gdb_server  # __exit__ must not stop a failed attempt again.
                logging.warning("%s OpenOCD startup retry: %s", self.CHIP, last_output.strip())
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise TimeoutError(
            f"{self.CHIP} OpenOCD startup timed out after {self.timeout}s: {last_output}"
        )

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
            # a UART bridge the pulse drives EN, and the native USB-JTAG device re-enumerates;
            # `_start_gdb_server` retries until OpenOCD reaches the JTAG function again.
            self.connection = self.init_sut_connection()
            self._start_gdb_server()
            self.init_gdb_controller()
            # Attaching halts the core; wait for that stop record.
            self._command(f"-target-select extended-remote {self.gdb_server_address}")
            self.wait_for_any_stop_message()
            if self.reset_on_connect:
                # OpenOCD has examined the core; restart the firmware from a clean boot.
                self.reset()
            if self.breakpoint_always_inserted:
                # Same breakpoints, written once instead of around every stop.
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
