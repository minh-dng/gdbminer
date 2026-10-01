"""Live acceptance check of a C3 port against its golden-grammar corpora.

Seeds and evaluation inputs are generated from the golden grammar, so the port
must accept every one. Known-invalid inputs, the 2,048-byte capacity and packet
alignment after an oversized rejection check the wrapper contract.
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

CAPACITY = 2048


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
    parser.add_argument("--reject", action="append", default=[], help="input that must be rejected")
    parser.add_argument(
        "--fill", required=True, help="byte string repeated to build capacity inputs"
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    config = ConfigParser()
    config.read(args.config)
    basic, connection = config["BASIC"], config["Connection"]

    cases = [
        (f"seed {p.name}", p.read_bytes(), True)
        for p in sorted(Path(basic["seed_directory"]).iterdir())
    ]
    cases += [
        (f"eval {p.name}", p.read_bytes(), True)
        for p in sorted(Path(basic["eval_directory"]).iterdir())
    ]
    cases += [(f"invalid {r!r}", r.encode(), False) for r in args.reject]
    fill = args.fill.encode()
    at_capacity = (fill * CAPACITY)[:CAPACITY]
    cases += [
        ("2048-byte input", at_capacity, True),
        ("2049-byte wrapper rejection", at_capacity + fill[:1], False),
        ("next packet after oversized rejection", cases[0][1], True),
    ]

    result = {
        "status": "incomplete",
        "elf_sha256": hashlib.sha256(Path(basic["binary_file"]).read_bytes()).hexdigest(),
        "cases": 0,
        "mismatches": [],
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
        ready = ord("A")
        for name, candidate, expected in cases:
            read_one_of(port, {ready}, 10)
            port.write(struct.pack("<I", len(candidate)) + candidate)
            port.flush()
            accepted = read_one_of(port, {0, 255}, 10) == 0
            result["cases"] += 1
            if accepted != expected:
                result["mismatches"].append({"name": name, "input_hex": candidate.hex()})
                print(f"MISMATCH {name}: accepted={accepted}", flush=True)
        result["status"] = "passed" if not result["mismatches"] else "failed"
        print(
            f"{result['status']}: {result['cases']} cases, {len(result['mismatches'])} mismatches"
        )
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        port.close()
        (args.out / "result.json").write_text(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
