# This code contains the main logic for controlling GDB
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from tracer.instance.esp32c3_instance import ESP32C3Instance
from tracer.instance.msp430_instance import MSP430Instance
from tracer.instance.stm32_instance import STM32Instance
from tracer.instance.sut_instance import GDBInstance, SUTInstance
from tracer.instance.valgrind_instance import ValgrindInstance
from util.config import Config


class GDBTracer:
    @dataclass(slots=True)
    class TraceEntry:
        address: str
        function_name: str
        function_args: list[str]
        stack: list[str]
        watchpoint_hits: list[int]

    def __init__(self, config: Config):
        self.entrypoint = config["GDB"]["entrypoint"]
        self.exitpoint = config["GDB"].get("exitpoint", "")
        self.watchpoint_type = config["GDB"]["watchpoint_type"]
        self.input_buffer = config["GDB"]["input_buffer"]
        self.ignore_functions_regex = config["GDB"].get("ignore_functions_regex", "")
        self.watchpoint_count = config["GDB"]["watchpoint_count"]
        self.config = config

    def trace_instruction(
        self, response: dict, instance: SUTInstance, execution_trace: list[TraceEntry]
    ) -> None:
        address = response["payload"]["frame"]["addr"]
        func_name = response["payload"]["frame"]["func"]
        func_args = response["payload"]["frame"]["args"]

        args = []
        for arg in func_args:
            if "name" in arg and "value" in arg:
                arg_name = arg["name"]
                arg_val = arg["value"]
                if (
                    arg_name
                    and arg_val
                    and "0x" not in arg_val
                    and arg_name != "argc"
                    and arg_name != "argv"
                ):
                    args.append(arg_val)

        # Cut args that are sometimes contained in the function name
        # if func_name and "(" in func_name:
        #    func_name = func_name.split("(")[0]

        # Make the function name safe for mimid
        func_name = (
            func_name.replace("<", "_")
            .replace(">", "_")
            .replace(":", "_")
            .replace(" ", "_")
            .replace(",", "_")
            .replace("#", "_")
            .replace(".", "_")
        )

        # Request a stack trace from target
        # Will be added on arrival
        instance.request_stacktrace()
        entry = GDBTracer.TraceEntry(address, func_name, args, [], [])
        execution_trace.append(entry)

    @staticmethod
    def open_sut_instance(config: Config, input_file: Path | str = "") -> SUTInstance:
        match GDBInstance(config["GDB"]["instance"]):
            case GDBInstance.VALGRIND:
                return ValgrindInstance(config, input_file)
            case GDBInstance.STM32:
                return STM32Instance(config, input_file)
            case GDBInstance.ESP32C3:
                return ESP32C3Instance(config, input_file)
            case GDBInstance.MSP430:
                return MSP430Instance(config, input_file)

    @staticmethod
    def merge_traces(list1: list[TraceEntry], list2: list[TraceEntry]) -> list[TraceEntry]:
        if not list1 or not list2 or len(list1) != len(list2):
            raise ValueError(f"Incomplete watchpoint windows: {len(list1)} != {len(list2)}")

        result: list[GDBTracer.TraceEntry] = []
        for index, (elem1, elem2) in enumerate(zip(list1, list2, strict=True)):
            if (elem1.address, elem1.function_name, elem1.stack) != (
                elem2.address,
                elem2.function_name,
                elem2.stack,
            ):
                raise ValueError(
                    f"Watchpoint windows diverge at instruction {index}: {elem1} != {elem2}"
                )
            new_entry = GDBTracer.TraceEntry(
                elem1.address,
                elem1.function_name,
                elem1.function_args,
                elem1.stack,
                [*elem1.watchpoint_hits, *elem2.watchpoint_hits],
            )
            result.append(new_entry)
        return result

    def trace_input(self, filename: Path | str) -> list[TraceEntry]:
        input_len = Path(filename).stat().st_size

        logging.info(f"Seed length: {input_len}")

        watchpoint_window_offset = 0

        merged_trace: list[GDBTracer.TraceEntry] | None = None

        # Sliding window according to watchpoint count
        while watchpoint_window_offset < input_len:
            with GDBTracer.open_sut_instance(self.config, filename) as instance:
                trace = self.trace_input_slice(instance, input_len, watchpoint_window_offset)

            if not trace or any(not entry.stack for entry in trace):
                raise ValueError(f"Incomplete trace window at offset {watchpoint_window_offset}")
            merged_trace = trace if merged_trace is None else self.merge_traces(merged_trace, trace)
            # TODO: Investigate backend support for unlimited watchpoints (-1) and window advancement.
            watchpoint_window_offset += self.watchpoint_count

        if merged_trace is None:
            raise ValueError("Cannot trace an empty seed")
        return merged_trace

    def trace_input_slice(
        self, instance: SUTInstance, input_len: int, watchpoint_window_offset: int = 0
    ) -> list[TraceEntry]:
        instruction_trace_list: list[GDBTracer.TraceEntry] = []
        watchpoint_offset = {}

        # Set the first breakpoint at entrypoint address
        entry_breakpoint = instance.set_temporary_breakpoint(self.entrypoint)
        if entry_breakpoint is None:
            instance.wait_for_any_gdb_response()
        instance.continue_execution()
        time.sleep(1)  # Give GDB some time to continue the execution
        instance.send_input()

        # The first stop after continuing must be the entry breakpoint: a late stop from the reset
        # or attach would otherwise be taken as the parser entry. Backends that return the
        # breakpoint number (C3) are also checked against it.
        response = instance.wait_for_any_stop_message()
        if response["payload"].get("reason") != "breakpoint-hit":
            raise RuntimeError(f"Unexpected stop before parser entry: {response}")
        if entry_breakpoint is not None and response["payload"].get("bkptno") != entry_breakpoint:
            raise RuntimeError(f"Unexpected entry breakpoint: {response}")

        string_range = range(input_len)
        watchpoint_range = range(self.watchpoint_count)
        # Set watchpoints
        for i, _ in zip(string_range[watchpoint_window_offset:], watchpoint_range):
            if self.input_buffer.startswith("0x"):
                watchpoint_address = hex(int(self.input_buffer, 16) + i)
            else:
                watchpoint_address = "&" + self.input_buffer + f"[{i}]"
            # Set watchpoint
            watchpoint_id = instance.set_watchpoint_and_get_id(
                watchpoint_address, self.watchpoint_type
            )
            watchpoint_offset[watchpoint_id] = i

        # Set breakpoint to exit address
        # TODO make this dependent on initial stack
        exit_breakpoint = None
        if self.exitpoint:
            exit_breakpoint = instance.set_temporary_breakpoint(self.exitpoint)

        # Request the entry stack only after watchpoint/breakpoint setup, so allocators that drain
        # GDB batches cannot consume this response.
        self.trace_instruction(response, instance, instruction_trace_list)

        # Wait for each instruction's stack before stepping, including entry. Otherwise a delayed
        # stack can be attributed to the successor.

        # To keep track of ignored functions and subroutines
        ignore_till_stack_len = -1

        # To remember at which stack level we start tracing

        entry_stack_len = -1
        entry_stack: list[str] = []
        # Raw GDB frame names; trace entries hold names normalised for mimid.
        entry_function = ""
        entry_caller_func = ""
        deadline = time.monotonic() + instance.timeout

        # Valgrind's gdbserver reports a completed `-exec-finish` without a reason, so a reason-less
        # stop is accepted only while a finish is pending.
        finish_pending = False

        run = True
        while run:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Trace stalled at window {watchpoint_window_offset}")
            responses = deque(instance.get_gdb_responses())
            while responses:
                response = responses.popleft()

                if instance.is_stack_message(response):
                    # Stacktrace incoming
                    logging.debug(f"Stacktrace {response['payload']}")

                    stacktrace = self.parse_stacktrace(response)
                    raw_frames = response["payload"].get("stack") or []
                    current_func = (
                        raw_frames[0].get("func", "")
                        if raw_frames and isinstance(raw_frames[0], dict)
                        else ""
                    )

                    deadline = time.monotonic() + instance.timeout
                    if entry_stack_len == -1:  # Init entry stack len
                        entry_stack_len = len(stacktrace)
                        entry_stack = stacktrace
                        entry_function = current_func
                        if len(raw_frames) > 1 and isinstance(raw_frames[1], dict):
                            entry_caller_func = raw_frames[1].get("func", "")
                    elif not self.exitpoint and entry_stack_len > len(stacktrace):
                        # Require the expected caller chain and that we actually left the parser.
                        # `parse_stacktrace` drops the current frame, so a truncated unwind can
                        # otherwise match `entry_stack[1:]`.
                        if stacktrace != entry_stack[1:]:
                            raise RuntimeError(f"Unexpected parser return stack: {stacktrace}")
                        if current_func == entry_function or (
                            entry_caller_func and current_func != entry_caller_func
                        ):
                            raise RuntimeError(
                                f"Parser return stop still in unexpected frame: {current_func!r}"
                            )
                        if instruction_trace_list[-1].watchpoint_hits:
                            raise RuntimeError("Read observations attached outside parser")

                        # Remove last trace element
                        instruction_trace_list.pop()

                        # Delete watchpoints and stop tracing
                        run = False
                        for wp_id in watchpoint_offset:
                            instance.delete_breakpoint(wp_id)
                        instance.continue_execution()

                        # Skip rest of loop
                        break

                    if ignore_till_stack_len < 0:
                        # Just add stacktrace to latest trace entry
                        if not instruction_trace_list[-1].stack:
                            instruction_trace_list[-1].stack = stacktrace
                            instance.step_instruction()
                        else:
                            logging.debug("Ignore duplicate stacktrace response")

                    elif len(stacktrace) > ignore_till_stack_len:
                        # We currently ignore messages
                        # Best we can do is to step out of func and check again
                        instance.step_out_of_function()
                        finish_pending = True
                    else:
                        # We reached the desired stack len,
                        # so go back to track every instruction
                        ignore_till_stack_len = -1
                        # instruction_trace_list[-1].stack = stacktrace
                        instance.step_instruction()

                # Check if execution is interrupted
                elif instance.is_stop_message(response):
                    logging.debug(f"Execution stopped {response['payload']}")
                    deadline = time.monotonic() + instance.timeout
                    after_finish, finish_pending = finish_pending, False

                    # Here we hit a breakpoint, which should only be on the exit point
                    if (
                        "reason" in response["payload"]
                        and response["payload"]["reason"] == "breakpoint-hit"
                    ):
                        if not self.exitpoint or (
                            exit_breakpoint is not None
                            and response["payload"].get("bkptno") != exit_breakpoint
                        ):
                            raise RuntimeError(f"Unexpected exit breakpoint: {response}")
                        # Delete watchpoints and stop tracing
                        run = False
                        for wp_id in watchpoint_offset:
                            instance.delete_breakpoint(wp_id)
                        instance.continue_execution()

                    # In this case we got a memory response and need to evaluate it
                    elif (
                        "reason" in response["payload"]
                        and "read-watchpoint-trigger" in response["payload"]["reason"]
                    ):
                        if "hw-rwpt" in response["payload"]:
                            # Sometimes 'hw-rwpt' comes as list and sometimes as single object. We take the first one, as they seems to be duplicates mostly
                            wp = (
                                response["payload"]["hw-rwpt"][0]
                                if isinstance(response["payload"]["hw-rwpt"], list)
                                and len(response["payload"]["hw-rwpt"]) > 0
                                else response["payload"]["hw-rwpt"]
                            )
                            watchpoint_id = wp["number"]
                            logging.info(f"Watchpoint triggered: {watchpoint_id}")
                            instruction_trace_list[-1].watchpoint_hits.append(
                                watchpoint_offset[watchpoint_id]
                            )
                            instance.step_instruction()

                        elif "offset" in response["payload"]:
                            offset = watchpoint_window_offset + response["payload"]["offset"]
                            logging.info(f"Watchpoint triggered: {offset} ")
                            instruction_trace_list[-1].watchpoint_hits.append(offset)

                    # This case will be executed after a step instruction.
                    # We need to check, if we need to do again a step instruction
                    # or a simple continue
                    # 'reason' in response['payload'] and \
                    #     (response['payload']['reason'] == 'end-stepping-range' or \
                    #     response['payload']['reason'] == 'function-finished'):
                    else:
                        reason = response["payload"].get("reason")
                        if reason not in {"end-stepping-range", "function-finished"} and not (
                            after_finish and reason is None
                        ):
                            raise RuntimeError(f"Unexpected trace stop: {response}")
                        func_name = response["payload"]["frame"]["func"]

                        # Check if we currently ignore interruptions
                        if ignore_till_stack_len > 0:
                            # Request stack trace to check if we reached our desired stack len
                            instance.request_stacktrace()

                        elif self.ignore_functions_regex and re.search(
                            self.ignore_functions_regex, func_name
                        ):
                            # Ignore all interruption until stack is back to previous function
                            ignore_till_stack_len = len(instruction_trace_list[-1].stack)
                            instance.step_out_of_function()
                            finish_pending = True
                        else:
                            if not instruction_trace_list[-1].stack:
                                raise RuntimeError("Successor arrived before instruction stack")
                            self.trace_instruction(response, instance, instruction_trace_list)
                elif response.get("type") == "result" and response.get("message") == "error":
                    raise RuntimeError(f"GDB command failed: {response}")
                else:
                    logging.debug(f"Unprocessed GDB message {response}")

        return instruction_trace_list

    def parse_stacktrace(self, response) -> list[str]:
        if not response["payload"].get("stack"):
            raise RuntimeError("Missing stack frames; cannot establish parser completion")
        stacktrace = []
        # Skip first address on stack trace, because it can be unreliable
        for frame in response["payload"]["stack"][1:]:
            stacktrace.append(frame["addr"])
        stacktrace.append("0x0")  # Put a dummy element on stack
        return stacktrace
