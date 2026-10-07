# This code is an abstract class for modeling connections
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import logging as log
import multiprocessing as mp
from abc import abstractmethod
from typing import override

from util import Config


class ConnectionBaseClass(mp.Process):
    """Exchange queued inputs with the target in a separate process.

    Check target readiness only after an input is available: a reset while
    waiting for the queue could invalidate an earlier readiness marker.
    Adapters define how readiness, packets, and results are exchanged.

    Connection process                     Target
            │                                  │
            │ Wait for queued input...         │ May become ready or reset
            │ Input arrives                    │
            │ wait_for_input_request()         │
            │ ◀──────── readiness ─────────────│
            │ send_input(input)                │
            │ ───────── packet ───────────────▶│ Receive and parse
            │ ◀──────── result ────────────────│
            │ Queue acceptance result          │
    """

    def __init__(
        self,
        config: Config,
        inputs: mp.Queue,
        response: mp.Queue,
        ready: mp.Queue,
    ):
        super().__init__()
        self.inputs = inputs
        self.response = response
        self.ready = ready
        self.config = config
        self.running = True

    @override
    def run(self):
        try:
            self.connect(self.config)
        except Exception:
            log.exception("Failed to connect to SUT")
            self.ready.put(False)
            return

        self.ready.put(True)
        while self.running:
            fuzz_input = self.inputs.get(block=True)
            self.wait_for_input_request()
            self.response.put(self.send_input(fuzz_input))

    def connect(self, config: Config): ...

    def connect_async(self): ...

    @abstractmethod
    def send_input(self, input: bytes) -> bool:
        """Sends 'input' to SUT

        Returns True if input was accepted
        """

    @abstractmethod
    def wait_for_input_request(self):
        """Blocks until SUT can receive input"""

    def disconnect(self):
        """[Optional], free connection resources
        Example: Close TCP socket.
        """

    @override
    def terminate(self):
        self.running = False
        super().terminate()
