"""Bounded live checks of the Arduino_JSON port and its serial/buffer contract.

Requires exclusive UART access and the matching firmware already flashed.
"""

import argparse
import hashlib
import json
import struct
import time
from configparser import ConfigParser
from pathlib import Path

import serial


def read_one_of(port, values: set[int], timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        byte = port.read(1)
        if byte and byte[0] in values:
            return byte[0]
    raise TimeoutError(f"No byte from {sorted(values)} before deadline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    config = ConfigParser()
    config.read(args.config)
    connection = config["Connection"]
    cases = [
        ("object", b"{}", True),
        ("array", b'[1,true,"x"]', True),
        ("invalid escape", b'"\\q"', False),
        ("invalid token", b"?", False),
        ("empty", b"", False),
        # cJSON_Parse uses C-string/prefix semantics, as in the STM32 wrapper.
        ("trailing bytes", b"{}junk", True),
        ("embedded NUL", b"{}\x00?", True),
        ("2048-byte valid input", b'"' + b"a" * 2046 + b'"', True),
        ("2049-byte wrapper rejection", b'"' + b"a" * 2047 + b'"', False),
        ("next packet after oversized rejection", b"{}", True),
    ]
    result = {
        "status": "incomplete",
        "elf_sha256": hashlib.sha256(Path(config["BASIC"]["binary_file"]).read_bytes()).hexdigest(),
        "baud_rate": connection.getint("baud_rate"),
        "ready_byte": ord("A"),
        "cases": [],
    }
    port = serial.Serial()
    port.port = connection["port"]
    port.baudrate = connection.getint("baud_rate")
    port.timeout = 0.2
    port.dtr = connection.getboolean("dtr", fallback=False)
    port.rts = connection.getboolean("rts", fallback=True)
    port.open()
    try:
        if connection.getboolean("reset_pulse", fallback=True):
            time.sleep(0.05)
            port.rts = False
            time.sleep(connection.getfloat("boot_delay", fallback=3))
        for name, candidate, expected in cases:
            read_one_of(port, {result["ready_byte"]}, 10)
            port.write(struct.pack("<I", len(candidate)) + candidate)
            port.flush()
            response = read_one_of(port, {0, 255}, 10)
            row = {
                "name": name,
                "input_hex": candidate.hex(),
                "size": len(candidate),
                "expected_accept": expected,
                "response": response,
            }
            result["cases"].append(row)
            if (response == 0) != expected:
                raise AssertionError(f"Wrong oracle decision: {name}: {response:#x}")
            print(f"PASS {name}: {len(candidate)} bytes -> {response:#04x}", flush=True)
        result["status"] = "passed"
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        port.close()
        (args.out / "result.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
