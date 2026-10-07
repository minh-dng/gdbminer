# This code contains code to connect to MSP430 controllers
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import logging
import subprocess
import time
from typing import override

from tracer.instance.hardware_instance import HardwareInstance


class MSP430Instance(HardwareInstance):
    @override
    def __enter__(self):
        # Start gdb server in subprocess
        self.gdb_server = subprocess.Popen(self.gdb_server_path_with_args)

        time.sleep(3)
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

        self.connection = self.init_sut_connection()
        self.reset()

        return self

    @override
    def reset(self) -> None:
        # Reset target
        self.interrupt()
        self.wait_for_any_gdb_response()
        self.send_gdb_command("monitor reset halt")
        self.wait_for_any_gdb_response()
        self.send_gdb_command("flushregs")

        # wait till something happened
        self.wait_for_any_gdb_response()

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
        self._stop_gdb_server()
