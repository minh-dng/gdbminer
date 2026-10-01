#!/bin/sh
# ESP32-C3 paper replica, trials 1 and 2 (see README.md in this folder).
#
# Per target: flash the firmware built beforehand, check the corpus once, then
# for each trial run the authors' pipeline with the target INI:
#   trace.py -> mine.py -> precision_recall.py
# trace.py creates output/esp32-c3_<target>/trial-<n>/; mining and evaluation
# select the newest trial folder, so each trial must finish before the next.
# Every stage records its exit status and wall time in the trial's times.txt
# and has a deadline (exit 143 = deadline reached). If tracing stops (for
# example a USB-JTAG drop), the failure is kept, the missing seeds are traced
# into resume-<k>/ once the links are back, and their traces are added to the
# trial, as for trial-0 xml.
#
# Usage: run-trials.sh            (TARGETS="json cgidecode xml" TRIALS="1 2")
set -u
R=$(cd "$(dirname "$0")/../../.." && pwd)
CLI=${ARDUINO_CLI:-$HOME/.local/opt/arduino-cli/1.5.1/arduino-cli}
FQBN=esp32:esp32:esp32c3:CDCOnBoot=default,FlashMode=dio
TARGETS=${TARGETS:-json cgidecode xml}
TRIALS=${TRIALS:-1 2}
MAX_RESUMES=2
PY=.venv/bin/python
cd "$R" || exit 1
export PYTHONPATH=src
STAGES=$R/output/esp32-c3-trials.stages.log

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$STAGES"; }

ini() { sed -n "s/^$2 = //p" "$1" | head -n 1; }

# Run a command; after <seconds>, send it SIGTERM (exit 143). The alarm stays in
# this perl parent, so it cannot interact with precision_recall.py's SIGALRM.
WATCHDOG='my $l = shift; my $p = fork // die "fork: $!"; if (!$p) { exec @ARGV or die "exec: $!" }
$SIG{ALRM} = sub { kill "TERM", $p }; alarm $l;
my $r; do { $r = waitpid($p, 0) } while ($r == -1 && $!{EINTR});
exit(($? & 127) ? 128 + ($? & 127) : $? >> 8)'

# stage <times-file> <label> <seconds> <log-file> <command...>
stage() {
  times=$1 label=$2 limit=$3 out=$4
  shift 4
  start=$(date +%s)
  perl -e "$WATCHDOG" "$limit" "$@" > "$out" 2>&1
  rc=$?
  printf '%s exit=%s seconds=%s\n' "$label" "$rc" "$(($(date +%s) - start))" >> "$times"
  [ $rc -eq 0 ] || cleanup
  return $rc
}

# A killed stage leaves its serial worker, GDB and OpenOCD running.
cleanup() {
  holders=$(lsof -t "$port" 2> /dev/null | tr '\n' ' ')
  [ -n "$holders" ] && log "cleanup: UART holders $holders" && kill $holders 2> /dev/null
  pkill -f 'openocd.*esp32c3-builtin' && log "cleanup: OpenOCD"
  pkill -f 'riscv32-esp-elf-gdb.*interpreter' && log "cleanup: GDB"
  sleep 5
}

# Both USB links present for 30 s, and no leftover process holding the UART.
links_ready() {
  waited=0 stable=0
  while [ $stable -lt 3 ]; do
    if [ -e "$port" ] && ls /dev/cu.usbmodem* > /dev/null 2>&1; then
      stable=$((stable + 1))
    else
      stable=0
    fi
    [ $waited -ge 1800 ] && return 1
    sleep 10
    waited=$((waited + 10))
  done
  if lsof "$port" > /dev/null 2>&1; then
    log "UART $port is held by another process: $(lsof -t "$port" | tr '\n' ' ')"
    return 1
  fi
  if pgrep -f 'openocd.*esp32c3-builtin' > /dev/null; then
    log "an OpenOCD instance for the C3 is still running"
    return 1
  fi
}

src_hash() { find src -name '*.py' -not -path '*/__pycache__/*' | sort | xargs shasum -a 256 | shasum -a 256 | cut -d' ' -f1; }

snapshot() {  # <dir>: code, configuration and inputs the trial runs with, taken before tracing
  mkdir -p "$1"
  {
    echo "date: $(date '+%F %T %Z')"
    echo "git HEAD: $(git rev-parse HEAD) ($(git rev-parse --abbrev-ref HEAD))"
    echo "src tree sha256 (see src.tgz): $(src_hash)"
    echo "ELF sha256: $(shasum -a 256 "$(ini "$cfg" binary_file)" | cut -d' ' -f1)"
    echo "gdb: $("$(ini "$cfg" gdb_path)" --version | head -n 1)"
    echo "openocd: $($(ini "$cfg" gdb_server_path | cut -d' ' -f1) --version 2>&1 | head -n 1)"
    echo "python: $($PY --version)"
    echo "PRECISION_SET_SIZE=${PRECISION_SET_SIZE:-unset} PYTHONHASHSEED=${PYTHONHASHSEED:-unset} (RNG unseeded, as upstream)"
    echo "libraries:"
    "$CLI" lib list 2>&1
  } > "$1/state.txt"
  git status --short > "$1/git-status.txt"
  git diff HEAD > "$1/git-diff.patch"
  tar -czf "$1/src.tgz" --exclude __pycache__ src
  (cd "$(ini "$cfg" seed_directory)" && shasum -a 256 -- *) > "$1/seeds.sha256"
  (cd "$(ini "$cfg" eval_directory)" && shasum -a 256 -- *) > "$1/eval.sha256"
  cp "$cfg" "$1/configuration.ini"
  cp "$(dirname "$(ini "$cfg" binary_file)")/build.options.json" "$1/build.options.json"
  cp "$base/build-2026-10-01.log" "$1/build.log"
  cp "$base/flash-2026-10-01.log" "$1/flash.log"
}

unchanged() {  # <trial-dir> <stage>: the code must not change during a trial
  [ "$(src_hash)" = "$(sed -n 's/^src tree sha256 (see src.tgz): //p' "$1/state.txt")" ] && return 0
  log "$t: src/ changed since the trial started; not running $2"
  return 1
}

missing_seeds() {  # <trial-dir>
  for seed in "$(ini "$cfg" seed_directory)"/*; do
    [ -f "$1/$(basename "$seed").trace" ] || echo "$seed"
  done
}

trace_trial() {  # <trial-number>; trace.py must create exactly trial-<n>
  dir=$base/trial-$1 pre=$base/.trial-$1
  latest=$(find "$base" -maxdepth 1 -name 'trial-*' | sed 's/.*trial-//' | sort -n | tail -n 1)
  [ "$latest" = "$(($1 - 1))" ] || { log "$t: expected trial-$(($1 - 1)) as newest, found trial-$latest"; return 1; }
  rm -rf "$pre"
  snapshot "$pre"
  stage "$pre/times.txt" trace "$trace_limit" "$pre/trace.log" $PY src/tracer/trace.py --config "$cfg"
  rc=$?
  [ -d "$dir" ] || { log "$t trial-$1: trace.py did not create $dir (kept $pre)"; return 1; }
  mv "$pre"/* "$dir/" && rmdir "$pre"
  k=0
  while [ -n "$(missing_seeds "$dir")" ]; do
    k=$((k + 1))
    log "$t trial-$1: tracing stopped (exit $rc); missing $(missing_seeds "$dir" | xargs -n 1 basename | tr '\n' ' ')"
    [ $k -le $MAX_RESUMES ] || { log "$t trial-$1: giving up after $MAX_RESUMES resumes"; return 1; }
    links_ready || { log "$t trial-$1: links not ready for resume $k"; return 1; }
    unchanged "$dir" "resume $k" || return 1
    rd=$dir/resume-$k
    mkdir -p "$rd/seeds"
    missing_seeds "$dir" | while read -r seed; do cp "$seed" "$rd/seeds/"; done
    sed -e "s|^seed_directory = .*|seed_directory = $rd/seeds|" \
      -e "s|^output_directory = .*|output_directory = $rd/|" "$cfg" > "$rd/configuration.ini"
    log "$t trial-$1: resume $k"
    stage "$dir/times.txt" "trace-resume-$k" "$trace_limit" "$rd/trace.log" \
      $PY src/tracer/trace.py --config "$rd/configuration.ini"
    rc=$?
    cp "$rd"/trial-0/*.trace "$dir/" 2> /dev/null
  done
}

run_trial() {  # <trial-number>
  n=$1 dir=$base/trial-$1
  links_ready || { log "$t trial-$n: links not ready"; return 1; }
  log "$t trial-$n: tracing"
  trace_trial "$n" || { log "$t trial-$n: failed tracing"; return 1; }
  # mine.py pairs sorted traces with sorted seeds; require exactly one trace per seed.
  seeds=$(for f in "$(ini "$cfg" seed_directory)"/*; do basename "$f"; done | sort)
  traces=$(for f in "$dir"/*.trace; do basename "$f" .trace; done | sort)
  [ "$seeds" = "$traces" ] || { log "$t trial-$n: traces do not match seeds"; return 1; }
  unchanged "$dir" mining || return 1
  log "$t trial-$n: mining"
  stage "$dir/times.txt" mine "$mine_limit" "$dir/mine.log" $PY src/miner/mine.py --config "$cfg" \
    || { log "$t trial-$n: failed mining"; return 1; }
  unchanged "$dir" evaluation || return 1
  log "$t trial-$n: evaluating"
  stage "$dir/times.txt" eval 3600 "$dir/eval.log" $PY src/eval/precision_recall.py --config "$cfg" \
    --out "$dir/evaluation.json" || { log "$t trial-$n: failed evaluating"; return 1; }
  log "$t trial-$n: finished $(cat "$dir/evaluation.json")"
}

run_target() {  # <target> <trace seconds> <mine seconds> <check_corpus arguments...>
  t=$1 trace_limit=$2 mine_limit=$3
  shift 3
  cfg=example_firmware/esp32-c3_$t/configuration/configuration.ini
  base=$(ini "$cfg" output_directory | sed 's|/$||')
  port=$(ini "$cfg" port)
  mkdir -p "$base"
  # Built once beforehand with the README command; its log is build-2026-10-01.log.
  [ -s "$base/build-2026-10-01.log" ] || { log "$t: build log missing"; return 1; }
  links_ready || { log "$t: links not ready for flashing"; return 1; }
  log "$t: flashing $(shasum -a 256 "$(ini "$cfg" binary_file)" | cut -d' ' -f1)"
  "$CLI" upload -b "$FQBN" -p "$port" --input-dir "$R/example_firmware/esp32-c3_$t/build" \
    "example_firmware/esp32-c3_$t" > "$base/flash-2026-10-01.log" 2>&1 \
    || { log "$t: failed flashing"; return 1; }
  log "$t: corpus check"
  rm -rf "$base/corpus-check-2026-10-01"
  $PY docs/thesis/esp32c3-paper-replica-2026-09-30/check_corpus.py --config "$cfg" \
    --out "$base/corpus-check-2026-10-01" "$@" > "$base/corpus-check-2026-10-01.log" 2>&1 \
    || { log "$t: failed corpus check"; return 1; }
  for n in $TRIALS; do
    run_trial "$n" || return 1
  done
}

# Deadlines: about three times the trial-0 durations (json 45 min, cgidecode
# 10 min, xml 7.5 h tracing; xml 82 min mining).
failed=0
for t in $TARGETS; do
  case $t in
    json) run_target json 10800 3600 --reject '?' --reject '"\q"' --reject '' --reject '{' --fill '[]' ;;
    cgidecode) run_target cgidecode 3600 3600 --reject '%FF' --reject '%80' --reject '%zz' --fill 'a' ;;
    xml) run_target xml 72000 18000 --reject 'a' --reject '<>' --fill ' ' ;;
    *) log "unknown target $t" && false ;;
  esac || {
    log "$t: stopped"
    failed=1
  }
done
log "all done (failed=$failed)"
exit $failed
