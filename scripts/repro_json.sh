#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-/tmp/gdbminer-repro-venv}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/output/repro-json}"
PYTHON="$VENV/bin/python"
CC="${CC:-gcc}"

cd "$REPO_ROOT"

if [[ -x "$PYTHON" ]] && [[ "$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.12" ]]; then
	rm -rf "$VENV"
fi
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --frozen --python 3.12.11 --no-dev

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/bin" "$OUT_DIR/work/seeds" "$OUT_DIR/work/eval" "$OUT_DIR/work/out"

cp example_programs/json/seeds/input.{1,2,3} "$OUT_DIR/work/seeds/"
cp example_programs/json/eval/input.{1,2,3,4,5,6,7,8,9,10} "$OUT_DIR/work/eval/"

"$CC" -g -O0 -no-pie -o "$OUT_DIR/bin/json" example_programs/json/json.c

# JSON string escaping also produces valid TOML strings for arbitrary paths.
"$PYTHON" - "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
paths = {
    "seed_directory": out / "work/seeds",
    "output_directory": out / "work/out",
    "binary_file": out / "bin/json",
    "eval_directory": out / "work/eval",
}
config = "[BASIC]\n" + "\n".join(
    f"{key} = {json.dumps(str(value))}" for key, value in paths.items()
)
config += '''

[Connection]
input_channel = "file"

[GDB]
gdb_path = "/usr/bin/gdb"
instance = "valgrind"
ignore_functions_regex = '@plt|_vgr*'
watchpoint_type = "(char*)"
watchpoint_count = 10000
timeout = 30
entrypoint = "json_parse"
exitpoint = ""
input_buffer = "my_string"

[LOGS]
log_level = "INFO"
'''
(out / "configuration.toml").write_text(config, encoding="utf-8")
PY

PYTHONPATH=src "$PYTHON" src/tracer/trace.py --config "$OUT_DIR/configuration.toml"
PYTHONPATH=src "$PYTHON" src/miner/mine.py --config "$OUT_DIR/configuration.toml"

echo "Wrote mined grammar to $OUT_DIR/work/out/trial-0/parsing_g.json"
