"""Probe raw C3 trigger capability/priority on the already-flashed parser.

Exclusive UART/JTAG ownership required. No firmware writes or software breaks.
Example: PYTHONPATH=src .venv/bin/python <script> --config CONFIG --out NEW_DIR --alias
"""

import argparse
import hashlib
import json
import logging
from configparser import ConfigParser
from pathlib import Path

from tracer.instance.esp32c3_instance import ESP32C3Instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--alias", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.count <= 8:
        raise ValueError("Test between one and eight slots")
    args.out.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=args.out / "mi.log", level=logging.DEBUG)
    config = ConfigParser()
    config.read(args.config)
    seed = args.out / "seed"
    seed.write_bytes(b'["abcdefghi"]')
    evidence = {
        "status": "incomplete",
        "alias": args.alias,
        "slots": [],
        "stops": [],
        "elf_sha256": hashlib.sha256(Path(config["BASIC"]["binary_file"]).read_bytes()).hexdigest(),
    }
    try:
        with ESP32C3Instance(config, seed) as instance:
            breakpoint = instance.set_temporary_breakpoint(config["GDB"]["entrypoint"])
            instance.continue_execution()
            instance.send_input()
            entry = instance.wait_for_any_stop_message()
            if entry["payload"].get("bkptno") != breakpoint:
                raise RuntimeError(f"Unexpected entry: {entry}")
            result, _ = instance._command('-data-evaluate-expression "(unsigned int)&buf[0]"')
            base = int(result["payload"]["value"], 0)
            saved = {}
            try:
                # Read every slot before mutating any of them. Never seize active slots.
                for slot in range(args.count):
                    instance.trigger_slot = slot
                    control, address, dcsr = instance._registers()
                    if control & 7:
                        raise RuntimeError(f"Slot {slot} has another owner: {control:#x}")
                    if dcsr & (1 << 11):
                        raise RuntimeError("Interrupts enabled during stepping")
                    saved[slot] = (control, address)
                for slot in saved:
                    address = base if args.alias else base + slot
                    instance._monitor(
                        f"reg tselect {slot}; reg tdata1 0; reg tdata2 {address:#x}; "
                        f"reg tdata1 {instance.MCONTROL:#x}"
                    )
                for slot in saved:
                    instance.trigger_slot = slot
                    control, address, _ = instance._registers()
                    expected_address = base if args.alias else base + slot
                    if (
                        control & instance.CONTROL_MASK != instance.MCONTROL
                        or address != expected_address
                    ):
                        raise RuntimeError(
                            f"Slot {slot} does not support required mode: {control:#x}/{address:#x}"
                        )
                    evidence["slots"].append(
                        {"slot": slot, "control": hex(control), "address": hex(address)}
                    )
                print(f"Validated {len(saved)} simultaneous load triggers", flush=True)
                disabled = set()
                first_pc = None
                for step in range(200):
                    before = instance._pc
                    stop = instance._step_stop()
                    states = {}
                    for slot in saved:
                        instance.trigger_slot = slot
                        states[slot] = instance._registers()
                    causes = {(s[2] >> 6) & 7 for s in states.values()}
                    hits = [
                        slot for slot, (control, _, _) in states.items() if control & instance.HIT
                    ]
                    if causes == {4} and not hits:
                        if first_pc is not None:
                            evidence["retired_pc"] = instance._pc
                            break
                        continue
                    if causes != {2} or not hits or instance._pc != before or set(hits) & disabled:
                        raise RuntimeError(f"Unexpected trigger stop: {stop}; {states}")
                    if first_pc is None:
                        first_pc = before
                    if before != first_pc:
                        raise RuntimeError("Recovery advanced past the matching instruction")
                    evidence["stops"].append({"pc": before, "hits": hits, "states": states})
                    print(f"Before-load match pc={before}, slots={hits}", flush=True)
                    for slot in hits:
                        instance._monitor(f"reg tselect {slot}; reg tdata1 0")
                        disabled.add(slot)
                else:
                    raise RuntimeError("No matching load and verified retirement within 200 steps")
                expected = set(saved) if args.alias else {0}
                if disabled != expected:
                    raise RuntimeError(
                        f"Missing or unexpected hardware matches: {disabled} != {expected}"
                    )
                evidence["status"] = "passed"
            finally:
                for slot, (control, address) in saved.items():
                    instance._monitor(
                        f"reg tselect {slot}; reg tdata1 0; reg tdata2 {address:#x}; reg tdata1 {control:#x}"
                    )
                    instance.trigger_slot = slot
                    restored, restored_address, _ = instance._registers()
                    if restored & 7 or restored_address != address:
                        raise RuntimeError(f"Failed to restore slot {slot}")
                evidence["cleanup"] = "verified-inactive"
            instance.continue_execution()
    finally:
        (args.out / "result.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    main()
