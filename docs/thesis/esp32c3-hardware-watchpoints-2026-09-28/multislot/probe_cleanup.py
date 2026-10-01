"""Deliberately abort armed/recovery states and verify eight-slot cleanup live."""

import argparse
import json
import logging
from configparser import ConfigParser
from pathlib import Path

from tracer.instance.esp32c3_instance import ESP32C3Instance


class ProbeInterrupted(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=args.out / "mi.log", level=logging.DEBUG)
    config = ConfigParser()
    config.read(args.config)
    config["GDB"]["watchpoint_count"] = "8"
    results = []
    for mode in ["armed", "partially-disabled-recovery"]:
        instance = ESP32C3Instance(config, args.input)
        try:
            with instance:
                breakpoint = instance.set_temporary_breakpoint(config["GDB"]["entrypoint"])
                instance.continue_execution()
                instance.send_input()
                stop = instance.wait_for_any_stop_message()
                if stop["payload"].get("bkptno") != breakpoint:
                    raise RuntimeError(f"Wrong parser entry: {stop}")
                for offset in range(8):
                    instance.set_watchpoint_and_get_id(f"&buf[{offset}]", "(char*)")
                if mode == "partially-disabled-recovery":
                    triggers = list(instance._triggers.values())
                    instance._set_triggers([triggers[2], triggers[5]], False)
                raise ProbeInterrupted(mode)
        except ProbeInterrupted:
            if instance._triggers:
                raise RuntimeError(f"Stale owned triggers after {mode}")
            results.append({"mode": mode, "cleanup": "passed"})
    with ESP32C3Instance(config, args.input) as instance:
        states, _ = instance._read_registers(list(range(8)))
        if any(control & 7 for control, _ in states.values()):
            raise RuntimeError(f"Active trigger after reconnect: {states}")
        instance.continue_execution()
    (args.out / "result.json").write_text(
        json.dumps(
            {"status": "passed", "interruptions": results, "reconnect": "all-eight-inactive"},
            indent=2,
        )
    )
    print("Armed abort, recovery abort, and reconnect cleanup passed")


if __name__ == "__main__":
    main()
