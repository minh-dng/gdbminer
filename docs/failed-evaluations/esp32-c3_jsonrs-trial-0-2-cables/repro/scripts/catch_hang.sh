#!/bin/bash
# Wait for the 5th read, then for the log to stall; snapshot GDB/OpenOCD state during the hang.
log=$1; out=$2
until grep -q "Watchpoint triggered: 4" "$log" 2>/dev/null || grep -q "^exit=" "$log" 2>/dev/null; do sleep 1; done
echo "hit4 or exit seen"
prev=-1
while ! grep -q "^exit=" "$log"; do
  size=$(stat -f %z "$log")
  if [ "$size" = "$prev" ]; then n=$((n+1)); else n=0; fi; prev=$size
  if [ "${n:-0}" -ge 6 ]; then break; fi
  sleep 1
done
{
  date; echo "--- processes"; ps -axo pid,ppid,stat,etime,%cpu,command | grep -E "riscv32-esp-elf-gdb|esp32c3-builtin" | grep -v grep
  gdbpid=$(pgrep -f riscv32-esp-elf-gdb | head -1)
  ocdpid=$(pgrep -f esp32c3-builtin | head -1)
  echo "--- lsof gdb $gdbpid"; lsof -p "$gdbpid" -a -i 2>/dev/null
  echo "--- sample gdb"; sample "$gdbpid" 3 -mayDie 2>&1 | sed -n '1,80p'
  echo "--- sample openocd $ocdpid"; sample "$ocdpid" 2 -mayDie 2>&1 | grep -E "Call graph|^ +[0-9]+ " | head -40
} > "$out" 2>&1
echo "snapshot written"
