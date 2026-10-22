#!/usr/bin/env bash
# Resume the C3 2-cable mining from method_trees.json, then evaluate. Up to 3 attempts for the
# loop phase, because OpenOCD start-up failed once (O10) at the start of that phase.
set -uo pipefail
cd /Users/minh/.t3/worktrees/gdbminer/t3-8fb1f618
D=output/c3-calc-2cable-run
C=$D/configuration.toml
B=(--adapter-serial A0:F2:62:01:70:28 --port /dev/cu.usbserial-11130 --gdb-port 3345)
export PYTHONPATH=src
date +%FT%T > $D/resume.start
for attempt in 1 2 3; do
  .venv/bin/python $D/resume_mine.py --config "$C" "${B[@]}" > $D/resume-mine-$attempt.out 2>&1
  rc=$?
  echo "resume mine attempt $attempt exit $rc $(date +%T)" >> $D/status.txt
  [ $rc -eq 0 ] && break
  sleep 60
done
date +%FT%T > $D/resume.end
if [ -s output/esp32-c3_calc-2-cables-reused-trial0/trial-0/parsing_g.json ]; then
  .venv/bin/python src/eval/precision_recall.py --config "$C" "${B[@]}" --out $D/evaluation.json > $D/eval.out 2>&1
  echo "eval exit $? $(date +%T)" >> $D/status.txt
  date +%FT%T > $D/eval.end
fi
