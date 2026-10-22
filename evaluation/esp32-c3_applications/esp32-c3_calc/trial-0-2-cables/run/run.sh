#!/usr/bin/env bash
# Mine and evaluate ESP32-C3 calc (2 cables) from the reused trial-0 traces.
set -uo pipefail
cd /Users/minh/.t3/worktrees/gdbminer/t3-8fb1f618
C=output/c3-calc-2cable-run/configuration.toml
B=(--adapter-serial A0:F2:62:01:70:28 --port /dev/cu.usbserial-11130 --gdb-port 3345)
export PYTHONPATH=src
date +%FT%T > output/c3-calc-2cable-run/mine.start
.venv/bin/python src/miner/mine.py --config "$C" "${B[@]}" > output/c3-calc-2cable-run/mine.out 2>&1
echo "mine exit $?" >> output/c3-calc-2cable-run/status.txt; date +%FT%T > output/c3-calc-2cable-run/mine.end
.venv/bin/python src/eval/precision_recall.py --config "$C" "${B[@]}" --out output/c3-calc-2cable-run/evaluation.json > output/c3-calc-2cable-run/eval.out 2>&1
echo "eval exit $?" >> output/c3-calc-2cable-run/status.txt; date +%FT%T > output/c3-calc-2cable-run/eval.end
