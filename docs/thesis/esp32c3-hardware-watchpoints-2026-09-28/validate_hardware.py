"""Live C3 window/replay check; writes partial evidence, never an accepted .trace.

Run with PYTHONPATH=src .venv/bin/python <this-file> --config CONFIG
--input SEED --out NEW_DIRECTORY [--windows 0 1] [--repeat 2].
Exclusive access to the UART/JTAG board is required. Firmware must already match
CONFIG's ELF; this script does not build or flash it.
"""

import argparse
import dataclasses
import hashlib
import json
import logging
import time
from configparser import ConfigParser
from pathlib import Path

from tracer.gdb_tracer import GDBTracer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--windows", nargs="+", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=args.out / "adapter.log", level=logging.DEBUG)
    config = ConfigParser()
    config.read(args.config)
    seed = args.input.read_bytes()
    windows = args.windows if args.windows is not None else list(range(len(seed)))
    if not seed or not windows or any(w < 0 or w >= len(seed) for w in windows):
        raise ValueError("Select nonempty, in-range byte windows")
    if args.repeat < 1 or config.getint("GDB", "watchpoint_count") != 1:
        raise ValueError("Positive repeats and single-slot configuration required")
    manifest = {
        "status": "incomplete", "config": str(args.config),
        "elf_sha256": hashlib.sha256(Path(config["BASIC"]["binary_file"]).read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "seed_hex": seed.hex(), "windows": [],
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    tracer = GDBTracer(config)
    merged = None
    start = time.monotonic()
    for repeat in range(args.repeat):
        for offset in windows:
            with tracer.open_sut_instance(config, args.input) as instance:
                trace = tracer.trace_input_slice(instance, len(seed), offset)
            window_file = args.out / f"repeat-{repeat}-window-{offset}.json"
            window_file.write_text(json.dumps(trace, default=dataclasses.asdict))
            # Compare every repeat to the same stable instruction/stack context.
            merged = trace if merged is None else tracer.merge_traces(merged, trace)
            hits = [(entry.address, entry.function_name, entry.watchpoint_hits)
                    for entry in trace if entry.watchpoint_hits]
            manifest["windows"].append({"offset": offset, "repeat": repeat,
                                        "instructions": len(trace), "hits": hits,
                                        "completion": "verified-return"})
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"repeat={repeat} offset={offset} instructions={len(trace)} hits={hits}", flush=True)
    manifest["status"] = "selected-windows-complete"
    manifest["seconds"] = time.monotonic() - start
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Validated {len(windows) * args.repeat} windows in {manifest['seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
