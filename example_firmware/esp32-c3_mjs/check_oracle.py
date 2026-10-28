"""Check the firmware wrapper against the fetched, pinned Cmimid benchmark source."""

import ctypes
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent
ROOT = TARGET.parents[1]
DESKTOP = ROOT / "example_programs/mjs"
COMMIT = "9c96909783ba99035372f78d6c52003f7f42b1ec"
HASHES = {
    "mjs.c": "4b46b1ec869ed479b108e97617a1b91ee978b1d6369498a10d717097389cd3c3",
    "mjs.h": "8beb8137ac2acc38544f4838ce6f3e08619dc920b6ce96199c2fb1d82ac11207",
    "mjs_extra.h": "c8f4cfd04fd058a6498a64f52f6bca85234ae49589af0ba77776ef7e3688fade",
}


def main() -> None:
    if (TARGET / "src/upstream").exists():
        raise ValueError("Move legacy src/upstream/ outside src/ before building the Cmimid target")
    for name, expected in HASHES.items():
        path = DESKTOP / name
        if not path.exists():
            raise FileNotFoundError("Run ./fetch_example_programs.sh --mjs-source-only first")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Desktop {name} does not match pinned Cmimid {COMMIT}")
        link = TARGET / "src" / ("mjs_source.h" if name == "mjs.c" else name)
        if link.resolve() != path.resolve():
            raise ValueError(f"Firmware {link} must link to the fetched desktop source {path}")

    build = TARGET / "build/native"
    build.mkdir(parents=True, exist_ok=True)
    library = build / "libmjs.so"
    command = [
        "cc",
        "-g",
        "-O0",
        "-shared",
        "-fPIC",
        str(TARGET / "src/parser.c"),
        "-lm",
        "-o",
        str(library),
    ]
    subprocess.run(command, check=True)
    parser = ctypes.CDLL(str(library)).parser
    parser.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    parser.restype = ctypes.c_int
    result: dict[str, object] = {
        "commit": COMMIT,
        "sources_sha256": HASHES,
        "parser_sha256": hashlib.sha256((TARGET / "src/parser.c").read_bytes()).hexdigest(),
        "compat_sha256": hashlib.sha256((TARGET / "src/cmimid_compat.h").read_bytes()).hexdigest(),
        "compiler_command": command,
        "compiler_version": subprocess.check_output(["cc", "--version"], text=True).strip(),
        "host": platform.platform(),
        "python_version": sys.version,
        "python_optimization": sys.flags.optimize,
    }
    for label, count in (("seeds", 20), ("eval", 1000)):
        inputs = sorted((DESKTOP / label).glob("*.in"))
        if len(inputs) != count:
            raise ValueError(f"Expected {count} {label} files, found {len(inputs)}")
        rejected = [
            str(p.relative_to(ROOT)) for p in inputs if parser(p.read_bytes(), p.stat().st_size)
        ]
        result[label] = {
            "count": count,
            "rejected": rejected,
            "inputs_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        }
        if rejected:
            raise ValueError(f"Rejected {label} inputs: {rejected}")
    controls = []
    for data, expected in (
        (b"", -1),
        (b"\0", 0),
        (b"let x = 1;\0@", 0),
        (b"let x = 1;", 0),
        (b"while (true) {}", 0),
        (b"unknown();", 0),
        (b"let x = ;", -1),
        (b"var x = 1;", -1),
        (b"let x = (1 + 2;", -1),
        (b"let x = 1; @", -1),
    ):
        actual = parser(data, len(data))
        controls.append({"input": data.decode(), "expected": expected, "actual": actual})
        if actual != expected:
            raise ValueError(f"Control {data!r}: expected {expected}, got {actual}")
    result["controls"] = controls
    (build / "corpus-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cmimid mJS: 20/20 seeds, 1000/1000 evaluation inputs, 10 acceptance checks passed.")


if __name__ == "__main__":
    main()
