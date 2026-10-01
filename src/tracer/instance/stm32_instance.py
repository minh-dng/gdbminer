# This code contains code to connect to STM32 controllers
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import logging
import shlex
import subprocess
import time
from pathlib import Path
from typing import override

from tracer.connection.sut_connection import SUTConnection
from tracer.instance.sut_instance import SUTInstance
from util.config import Config


class STM32Instance(SUTInstance):
    def __init__(self, config: Config, input_file: Path | str) -> None:
        super().__init__(config)

        stm32 = config["stm32"]
        self.gdb_server_path_with_args = shlex.split(stm32["gdb_server_path"])
        self.gdb_server_address = stm32["gdb_server_address"]
        self.watchpoint_count = config["GDB"]["watchpoint_count"]
        self.dwt_function_reg = stm32["dwt_function_reg"]
        self.dwt_watchpoint_workaround = stm32.get("dwt_watchpoint_workaround", True)
        self.input_file = Path(input_file)

    @override
    def __enter__(self):
        # Native USB CDC devices must be opened while their firmware still runs.
        self.connection = self.init_sut_connection()

        # Start gdb server in subprocess
        self.gdb_server = subprocess.Popen(self.gdb_server_path_with_args)

        time.sleep(1)
        logging.info("GDB Server started")

        # init gdb controller
        self.init_gdb_controller()

        # Connect to GDB Server
        logging.info(f"Trying to connect to GDB Server at {self.gdb_server_address}")
        self.gdb_controller.write(
            f"-target-select extended-remote {self.gdb_server_address}",
            read_response=False,
            timeout_sec=0,
            raise_error_on_timeout=False,
        )
        logging.info(f"Connected to GDB Server at {self.gdb_server_address}")

        self.wait_for_any_stop_message()

        self.reset()

        return self

    # Subclasses may override init_SUT_connection
    def init_sut_connection(self):
        return SUTConnection(self.config, self.reset)

    @override
    def step_instruction(self):
        if self.dwt_watchpoint_workaround:
            # ARMv7 DWT watchpoints do not interrupt single-stepping.
            self.read_dwt_function_register()
        super().step_instruction()

    def read_dwt_function_register(self):
        # Watchpoints are not triggered in single step mode on STM32
        # We can read the DWT function register to see if a watchpoint was triggered.
        logging.debug("Read Watchpoints manually")
        self.send_gdb_command(
            f"-data-read-memory {self.dwt_function_reg} t 4 {self.watchpoint_count} 4"
        )

    @override
    def get_gdb_responses(self) -> list[dict]:
        responses = super().get_gdb_responses()

        # For Watchpoint workaround
        for response in responses:
            if (
                response["message"] == "done"
                and response["type"] == "result"
                and "payload" in response
                and response["payload"]
                and "memory" in response["payload"]
            ):
                for i in range(len(response["payload"]["memory"])):
                    if response["payload"]["memory"][i]["data"][0][7] == "1":
                        # Here we have a watchpoint hit.
                        # Translate to 'real' watchpoint message
                        response["payload"].update({"reason": "read-watchpoint-trigger"})
                        response["payload"].update({"offset": i})
                        response["message"] = "stopped"
                        response["type"] = "notify"

        return responses

    def reset(self):
        # Reset target
        self.interrupt()
        self.wait_for_any_gdb_response()
        self.send_gdb_command("monitor reset halt")
        self.wait_for_any_gdb_response()
        self.send_gdb_command("flushregs")

        # wait till something happened
        self.wait_for_any_gdb_response()
        time.sleep(1)
        # Do not let reset's asynchronous stop notification masquerade as the
        # entrypoint breakpoint of the next trace.
        self.get_gdb_responses()

    @override
    def send_input(self) -> None:
        with self.input_file.open("rb") as f:
            input = f.read()
        self.connection.send_input(input)

    @override
    def input_accepted(self, input: bytes) -> bool:
        self.number_of_tested_inputs += 1
        accepted = self.connection.input_accepted(input)
        logging.debug(f"Test {input} : {accepted=}")
        return accepted

    @override
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connection.disconnect()

        super().__exit__(exc_type, exc_val, exc_tb)

        # Need a short time to wait between GDB and GDB Server shutdown, else we get errors like the following:
        # [!] send_recv send request failed: LIBUSB_ERROR_BUSY
        # [!] send_recv STLINK_DEBUG_RUNCORE
        # [!] send_recv send request failed: LIBUSB_ERROR_BUSY
        # [!] send_recv STLINK_JTAG_WRITEDEBUG_32BIT

        time.sleep(1)
        # Exit gdb server
        self.gdb_server.terminate()
        try:
            self.gdb_server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.gdb_server.kill()
            self.gdb_server.communicate()
        logging.info("GDB Server terminated")
