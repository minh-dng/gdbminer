#!/usr/bin/env bash
set -euo pipefail

# Regression check for the LLVM 14 taints port (mimid-llvm14.patch): taint
# propagation must handle the FNEG instruction, which clang >= 8 emits for
# unary float negation and which the LLVM 4 trace format never contained.
#
# Run inside the experiment image, where /mimid/taints is built:
#   scripts/repro_fneg.sh

TAINTS="/mimid/taints"

if [[ ! -x "$TAINTS/install/bin/trace-instr" ]]; then
	echo "error: $TAINTS is not built; run this script inside the experiment image" >&2
	exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

cp "$(dirname "${BASH_SOURCE[0]}")/fneg_reproducer.c" "$WORK_DIR/fneg.c"
cd "$WORK_DIR"

"$TAINTS/install/bin/trace-instr" fneg.c "$TAINTS/samples/excluded_functions"
printf 'A' | ./fneg.c.instrumented >/dev/null
gzip -c output >output.gz
"$TAINTS/install/bin/trace-taint" -me metadata -po pygmalion.json -t output.gz

echo "FNEG reproducer passed: trace-taint handled unary float negation"
