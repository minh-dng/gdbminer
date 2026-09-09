#!/usr/bin/env bash
set -euo pipefail

# Regression check for issue #18: the LLVM 14 taints port instrumented C
# functions on N = hardware_concurrency * 30 threads and raced on the shared
# LLVM Module. The race intermittently SIGSEGV'd `opt` (exit 139) on linux/amd64
# while linux/arm64 often slipped by. The port now instruments serially.
#
# Run inside the experiment image, where /mimid/taints is built:
#   scripts/repro_instrumentation_race.sh
#
# The script instruments json.c repeatedly. Any non-zero exit fails the check.

TAINTS="/mimid/taints"
CMIMID="/mimid/Cmimid"
RUNS="${RUNS:-8}"

if [[ ! -x "$TAINTS/install/bin/trace-instr" ]]; then
	echo "error: $TAINTS is not built; run this script inside the experiment image" >&2
	exit 1
fi

if [[ ! -f /example_programs/json/json.c ]]; then
	echo "error: /example_programs/json/json.c is missing; run inside the experiment image" >&2
	exit 1
fi

cp /example_programs/json/json.c "$CMIMID/examples/"
make -C "$CMIMID" build/json.c >/tmp/repro-race-prepare.log

mkdir -p "$TAINTS/build"
rm -rf "${TAINTS:?}/build/"*
cp "$CMIMID"/examples/*.h "$CMIMID/build/"
cp -r "$CMIMID/build/"* "$TAINTS/build/"

for i in $(seq 1 "$RUNS"); do
	"$TAINTS/install/bin/trace-instr" \
		"$TAINTS/build/json.c" \
		"$TAINTS/samples/excluded_functions" \
		>"/tmp/repro-race-$i.log" 2>&1
	if [[ ! -x "$TAINTS/build/json.c.instrumented" ]]; then
		echo "error: run $i produced no instrumented binary" >&2
		exit 1
	fi
	rm -f "$TAINTS/build/json.c.instrumented"
	echo "run $i ok"
done

echo "Instrumentation race reproducer passed: $RUNS serial json.c runs"
