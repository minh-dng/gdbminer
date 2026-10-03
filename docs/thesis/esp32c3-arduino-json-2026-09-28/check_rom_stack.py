"""Hardware regression: ROM calls must retain the parser's caller chain.

Uses the already-flashed Arduino_JSON firmware; does not flash or alter it.
The ROM address must match the connected chip and the failing call under test.
"""

import argparse
import json
import time
from configparser import ConfigParser
from pathlib import Path

from tracer.instance.esp32c3_instance import ESP32C3Instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--rom-address", required=True)
    parser.add_argument(
        "--check-return", action="store_true", help="Verify this stop's return against live RA"
    )
    parser.add_argument(
        "--walk-memset", action="store_true", help="Step the first memset call through its return"
    )
    args = parser.parse_args()
    config = ConfigParser()
    config.read(args.config)
    with ESP32C3Instance(config, args.input) as instance:
        entrypoint = config["GDB"]["entrypoint"]
        instance.set_temporary_breakpoint(entrypoint)
        instance.continue_execution()
        time.sleep(1)  # Match the tracer's post-continue serial startup delay.
        instance.send_input()
        instance.wait_for_any_stop_message()
        entry, _ = instance._command("-stack-list-frames")
        callers = [frame["addr"] for frame in entry["payload"]["stack"][1:]]
        instance.set_temporary_breakpoint(args.rom_address)
        instance.continue_execution()
        instance.wait_for_any_stop_message()
        result, _ = instance._command("-stack-list-frames")
        stack = result["payload"]["stack"]
        print(json.dumps(stack, indent=2), flush=True)
        assert int(stack[0]["addr"], 16) == int(args.rom_address, 16), stack
        assert any(frame.get("func") == entrypoint for frame in stack), stack
        assert callers and [frame["addr"] for frame in stack[-len(callers) :]] == callers, stack
        print("PASS: ROM stack retains the parser and its entry caller chain.")
        if args.check_return:
            read_regs = "-data-list-register-values x 1 2 5 8 32"
            before, _ = instance._command(read_regs)
            instance._command("-stack-list-frames")
            after, _ = instance._command(read_regs)
            assert before["payload"] == after["payload"], "Unwinding changed target registers"
            ra = int(before["payload"]["register-values"][0]["value"], 16)
            instance._step_stop()
            returned, _ = instance._command("-stack-list-frames")
            actual = returned["payload"]["stack"]
            assert int(actual[0]["addr"], 16) == ra, actual
            assert [f["addr"] for f in actual] == [f["addr"] for f in stack[1:]], actual
            print(
                "PASS: return reaches live RA and the exact unwound caller chain; no registers modified."
            )
        if args.walk_memset:
            start = int(config["GDB"]["rom_memset_address"], 0)
            assert int(args.rom_address, 16) == start, "Walk must begin at memset entry"
            read_regs = "-data-list-register-values x 1 2 5 8 32"  # ra, sp, t0, s0, pc
            registers, _ = instance._command(read_regs)
            outer_ra = int(registers["payload"]["register-values"][0]["value"], 16)
            paths = set()
            for step in range(256):
                before, _ = instance._command(read_regs)
                result, _ = instance._command("-stack-list-frames")
                after, _ = instance._command(read_regs)
                assert before["payload"] == after["payload"], "Unwinding changed target registers"
                stack = result["payload"]["stack"]
                assert any(frame.get("func") == entrypoint for frame in stack), stack
                assert [frame["addr"] for frame in stack[-len(callers) :]] == callers, stack
                pc = int(stack[0]["addr"], 16)
                if not start <= pc < start + 0xA8:
                    assert pc == outer_ra, (hex(pc), hex(outer_ra))
                    break
                ra = int(before["payload"]["register-values"][0]["value"], 16)
                if ra != start + 0x9A:
                    paths.add("ordinary")
                elif pc - start in range(0x3A, 0x77, 4):
                    paths.add("internal")
                instance._step_stop()
            else:
                raise AssertionError("memset failed to return within the diagnostic step budget")
            assert paths == {"internal", "ordinary"}, paths
            print(f"PASS: {step} steps, both memset paths, unchanged registers, correct return.")


if __name__ == "__main__":
    main()
