#!/usr/bin/env python3
"""Compare the ESP32 jsonrs oracle with the desktop jsonrs, and probe the parser's stack depth.

The desktop verdict is the file oracle's: the input is accepted when `json.rs`, built for the
host, exits with status 0. The ESP32 verdict comes from one of two targets:

- `--model`: the host model of the firmware (`example_firmware/esp32-c3_jsonrs/host/model.c`
  linked with `rust/lib.rs`), which prints the result byte;
- `--config`: the board, without a debugger, through the tracer's own serial exchange
  (`ESP32UARTConnection` or `ESP32USBSerialJTAGConnection`, chosen by `Connection.input_channel`).

    uv run scripts/esp32_jsonrs_oracle.py corpus --desktop DESKTOP --model MODEL \\
        example_programs/json/seeds example_programs/json/eval
    uv run scripts/esp32_jsonrs_oracle.py corpus --desktop DESKTOP \\
        --config example_firmware/esp32-c3_jsonrs/configuration/configuration.2-cables.toml \\
        --port /dev/cu.usbserial-XXXX example_programs/json/seeds example_programs/json/eval
    uv run scripts/esp32_jsonrs_oracle.py depth --kind array \\
        --config example_firmware/esp32-c3_jsonrs/configuration/configuration.2-cables.toml \\
        --port /dev/cu.usbserial-XXXX

`depth` sends valid inputs of growing nesting depth to the board until the firmware restarts
twice on one input, which the serial exchange reports as an error. The deepest answered input
is the deepest nesting that fits the loop-task stack.
"""

# SPDX-License-Identifier: AGPL-3.0

import argparse
import logging
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from util.config import load_config

Verdict = Callable[[bytes], bool]


def desktop_verdict(binary: Path) -> Verdict:
    def accepted(data: bytes) -> bool:
        with tempfile.NamedTemporaryFile() as f:
            f.write(data)
            f.flush()
            status = subprocess.run(
                [binary, f.name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode
        return status == 0

    return accepted


def model_verdict(binary: Path) -> Verdict:
    def accepted(data: bytes) -> bool:
        with tempfile.NamedTemporaryFile() as f:
            f.write(data)
            f.flush()
            out = subprocess.run([binary, f.name], capture_output=True, text=True, check=True)
        return int(out.stdout) == 0

    return accepted


def board_verdict(args: argparse.Namespace) -> Verdict:
    import multiprocessing as mp

    from tracer.connection.esp32_serial_connection import (
        ESP32SerialConnection,
        ESP32UARTConnection,
        ESP32USBSerialJTAGConnection,
    )
    from tracer.connection.sut_connection import InputChannel

    config = load_config(args.config)
    # Only the serial port: no GDB server is started, so its settings stay unfilled.
    config["Connection"]["port"] = args.port
    classes: dict[InputChannel, type[ESP32SerialConnection]] = {
        InputChannel.ESP32_UART: ESP32UARTConnection,
        InputChannel.ESP32_USB_SERIAL_JTAG: ESP32USBSerialJTAGConnection,
    }
    channel = InputChannel(config["Connection"]["input_channel"])
    if channel not in classes:
        raise SystemExit(f"Not an ESP32 input channel: {channel}")
    # The tracer runs the exchange in a separate process fed by these queues; this script calls it
    # directly, so they stay empty.
    connection = classes[channel](config, mp.Queue(), mp.Queue(), mp.Queue())
    connection.connect(config)

    def accepted(data: bytes) -> bool:
        connection.wait_for_input_request()
        return connection.send_input(data)

    return accepted


def esp32_verdict(args: argparse.Namespace) -> Verdict:
    if (args.model is None) == (args.config is None):
        raise SystemExit("Give exactly one of --model and --config")
    if args.config is not None and not args.port:
        raise SystemExit("--config needs --port")
    return model_verdict(args.model) if args.model else board_verdict(args)


def corpus(args: argparse.Namespace) -> int:
    desktop = desktop_verdict(args.desktop)
    esp32 = esp32_verdict(args)
    differ = 0
    for directory in args.directories:
        files = sorted(p for p in directory.iterdir() if p.is_file())
        accepted = [0, 0]
        for path in files:
            data = path.read_bytes()
            verdicts = desktop(data), esp32(data)
            accepted[0] += verdicts[0]
            accepted[1] += verdicts[1]
            if verdicts[0] != verdicts[1]:
                differ += 1
                print(f"  differs: {path} desktop={verdicts[0]} esp32={verdicts[1]}")
        print(
            f"{directory}: {len(files)} inputs, desktop accepts {accepted[0]}, "
            f"ESP32 accepts {accepted[1]}"
        )
    print(f"{differ} inputs differ")
    return 1 if differ else 0


def nested(kind: str, depth: int) -> bytes:
    if kind == "array":
        return b"[" * depth + b"0" + b"]" * depth
    return b'{"":' * depth + b"0" + b"}" * depth


def depth(args: argparse.Namespace) -> int:
    if args.config is None or not args.port:
        raise SystemExit("depth needs the board: --config and --port")
    esp32 = board_verdict(args)
    deepest = None
    for d in range(args.start, args.stop + 1):
        data = nested(args.kind, d)
        try:
            accepted = esp32(data)
        except (RuntimeError, OSError) as exc:  # OSError: the port vanished in a USB reset
            print(f"{args.kind} depth {d}: no answer ({exc})")
            print(f"deepest {args.kind} nesting answered: {deepest}")
            return 0
        print(f"{args.kind} depth {d}: {'accepted' if accepted else 'rejected'}")
        deepest = d
    print(f"no restart up to {args.kind} depth {args.stop}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the ESP32 jsonrs oracle with the desktop jsonrs."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def target_arguments(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", type=Path, help="Host model binary (host/model.c)")
        p.add_argument("--config", type=Path, help="Target configuration, for the board")
        p.add_argument("--port", help="Serial device of the board, Connection.port")

    p = sub.add_parser("corpus", help="Compare verdicts on every file of the directories")
    p.add_argument("--desktop", type=Path, required=True, help="Desktop jsonrs binary")
    target_arguments(p)
    p.add_argument("directories", type=Path, nargs="+")
    p.set_defaults(run=corpus)

    p = sub.add_parser("depth", help="Find the deepest nesting the board answers")
    target_arguments(p)
    p.add_argument("--kind", choices=("array", "object"), default="array")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--stop", type=int, default=60)
    p.set_defaults(run=depth)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
