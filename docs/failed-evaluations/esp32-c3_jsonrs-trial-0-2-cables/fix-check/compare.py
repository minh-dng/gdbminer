"""Compare two GDBMiner traces entry by entry and report which fields differ.

Usage: compare.py <reference.trace> <new.trace>
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def hits(trace: list[dict]) -> int:
    return sum(len(entry["watchpoint_hits"]) for entry in trace)


def main() -> None:
    reference_path, new_path = map(Path, sys.argv[1:3])
    reference, new = load(reference_path), load(new_path)
    for label, path, trace in (("reference", reference_path, reference), ("new", new_path, new)):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{label}: {path.name} sha256={digest} entries={len(trace)} hits={hits(trace)}")
    if reference_path.read_bytes() == new_path.read_bytes():
        print("result: byte-identical")
        return
    if len(reference) != len(new):
        print(f"result: entry counts differ ({len(reference)} vs {len(new)})")
        return
    differing = Counter(
        field
        for old, current in zip(reference, new, strict=True)
        for field in old.keys() | current.keys()
        if old.get(field) != current.get(field)
    )
    if not differing:
        print("result: entries identical, bytes differ (formatting only)")
        return
    for field, count in sorted(differing.items()):
        print(f"field {field}: differs in {count} of {len(reference)} entries")
    other = set(differing) - {"function_args"}
    print("result: " + ("identical apart from function_args" if not other else f"differs in {sorted(other)}"))


if __name__ == "__main__":
    main()
