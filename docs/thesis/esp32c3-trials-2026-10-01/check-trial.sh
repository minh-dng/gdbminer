#!/bin/sh
# Host-side alignment check of one finished trial (no board needed).
#
# The upstream tools do not log individual oracle answers, so a one-query serial
# shift can hide behind plausible scores (replica record, Section 8). Two checks
# use the host parser builds of the replica analysis (host_eval.py):
#   1. every generated input the board rejected in evaluation must also be
#      rejected by the host oracle;
#   2. the trial's grammar, scored with the host oracle (5 x 1,000 precision
#      samples, recall on the corpus), should match the board's scores.
# Output: trial-<n>/host-check.txt
#
# Usage: check-trial.sh <json|cgidecode|xml> <trial-number>
set -eu
R=$(cd "$(dirname "$0")/../../.." && pwd)
A=${ANALYSIS:-$HOME/Documents/Uni/thesis/experiments/esp32c3-paper-replica-2026-09-30/analysis}
t=$1 dir=$R/output/esp32-c3_$1/trial-$2
cd "$R"
export PYTHONPATH=src
sed -n 's/.*Generated non accepting input: //p' "$dir/eval.log" > "$dir/board-rejected.txt"
{
  echo "board evaluation: $(cat "$dir/evaluation.json")"
  echo "board-rejected generated inputs: $(wc -l < "$dir/board-rejected.txt" | tr -d ' ')"
  .venv/bin/python "$A/host_eval.py" "$t" oracle-check "$dir/board-rejected.txt"
  .venv/bin/python "$A/host_eval.py" "$t" grammars "$dir/parsing_g.json"
} > "$dir/host-check.txt" 2>&1
cat "$dir/host-check.txt"
