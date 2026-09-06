#!/usr/bin/env bash
set -euo pipefail

# Regression check for the LLVM 14 taints port (mimid-llvm14.patch): taint
# propagation must handle the CALLBR instruction, which clang >= 9 emits for
# asm goto and which the LLVM 4 trace format never contained.
#
# Run inside the experiment image, where /mimid/taints is built:
#   scripts/repro_callbr.sh

TAINTS="/mimid/taints"

if [[ ! -x "$TAINTS/install/bin/trace-instr" ]]; then
	echo "error: $TAINTS is not built; run this script inside the experiment image" >&2
	exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

cp "$(dirname "${BASH_SOURCE[0]}")/callbr_reproducer.c" "$WORK_DIR/callbr.c"
cd "$WORK_DIR"

"$TAINTS/install/bin/trace-instr" callbr.c "$TAINTS/samples/excluded_functions"
printf 'A' | ./callbr.c.instrumented >/dev/null
gzip -c output >output.gz
"$TAINTS/install/bin/trace-taint" -me metadata -po pygmalion.json -t output.gz

echo "CALLBR reproducer passed: trace-taint handled asm goto (CALLBR)"
