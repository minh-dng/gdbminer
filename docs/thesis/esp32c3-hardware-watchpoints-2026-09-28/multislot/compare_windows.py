"""Compare full hardware traces across watchpoint budgets without flashing.

Writes diagnostic JSON, not mining-ready .trace files. A successful comparison
requires identical instruction/stack sequences AND per-instruction read offsets.
"""

import argparse
import dataclasses
import hashlib
import json
import logging
import time
from collections import Counter
from configparser import ConfigParser
from pathlib import Path

from tracer.gdb_tracer import GDBTracer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--counts", nargs="+", type=int, default=[8, 1])
    parser.add_argument(
        "--expected-reads", nargs="+", type=int, help="Known fixture read count for each input byte"
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=args.out / "adapter.log", level=logging.INFO)
    config = ConfigParser()
    config.read(args.config)
    seed = args.input.read_bytes()
    if not seed or any(not 1 <= n <= 8 for n in args.counts):
        raise ValueError("Use a nonempty seed and budgets in 1..8")
    if len(args.counts) < 2 and args.expected_reads is None:
        raise ValueError("Use two budgets or a fixture's known per-byte read counts")
    if args.expected_reads is not None and len(args.expected_reads) != len(seed):
        raise ValueError("Supply one expected read count per input byte")
    manifest = {
        "status": "incomplete",
        "elf_sha256": hashlib.sha256(Path(config["BASIC"]["binary_file"]).read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(
            Path("src/tracer/instance/esp32c3_instance.py").read_bytes()
        ).hexdigest(),
        "seed_hex": seed.hex(),
        "runs": [],
    }
    baseline = None
    try:
        for count in args.counts:
            config["GDB"]["watchpoint_count"] = str(count)
            tracer = GDBTracer(config)
            merged = None
            run = {"count": count, "windows": [], "status": "incomplete"}
            manifest["runs"].append(run)
            start = time.monotonic()
            for offset in range(0, len(seed), count):
                with tracer.open_sut_instance(config, args.input) as instance:
                    trace = tracer.trace_input_slice(instance, len(seed), offset)
                if not trace or any(not entry.stack for entry in trace):
                    raise RuntimeError(f"Incomplete window at offset {offset}")
                (args.out / f"count-{count}-window-{offset}.json").write_text(
                    json.dumps(trace, default=dataclasses.asdict)
                )
                merged = trace if merged is None else tracer.merge_traces(merged, trace)
                run["windows"].append(
                    {
                        "offset": offset,
                        "instructions": len(trace),
                        "hits": sum(len(entry.watchpoint_hits) for entry in trace),
                    }
                )
                print(
                    f"count={count} offset={offset} instructions={len(trace)} "
                    f"hits={run['windows'][-1]['hits']}",
                    flush=True,
                )
                (args.out / "result.json").write_text(json.dumps(manifest, indent=2))
            observed = Counter(offset for entry in merged for offset in entry.watchpoint_hits)
            run["reads_per_byte"] = [observed[i] for i in range(len(seed))]
            if args.expected_reads is not None and run["reads_per_byte"] != args.expected_reads:
                raise RuntimeError(
                    f"Hardware read counts {run['reads_per_byte']} != expected {args.expected_reads}"
                )
            stable = [
                (e.address, e.function_name, e.stack, sorted(e.watchpoint_hits)) for e in merged
            ]
            if baseline is not None and stable != baseline:
                mismatch = next(
                    (i for i, pair in enumerate(zip(baseline, stable)) if pair[0] != pair[1]),
                    min(len(baseline), len(stable)),
                )
                raise RuntimeError(
                    f"Budgets diverge at instruction {mismatch}; lengths {len(baseline)}/{len(stable)}"
                )
            baseline = stable
            run.update(
                status="complete",
                seconds=time.monotonic() - start,
                instructions=len(stable),
                hits=sum(len(row[3]) for row in stable),
            )
            print(f"count={count} complete: {run['seconds']:.2f}s", flush=True)
        manifest["status"] = "passed"
    except BaseException as error:
        manifest["error"] = repr(error)
        raise
    finally:
        (args.out / "result.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
