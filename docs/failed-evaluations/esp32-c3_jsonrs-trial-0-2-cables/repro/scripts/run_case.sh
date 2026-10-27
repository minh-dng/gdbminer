#!/bin/bash
# One isolated run: serial reset, fresh OpenOCD, GDB script $1; output to $2.
cd /tmp/c3pm; rm -f ready go
PY=/Users/minh/.t3/worktrees/gdbminer/feat-esp32-c3-jsonrs-c3/.venv/bin/python
GDB=~/Library/Arduino15/packages/esp32/tools/riscv32-esp-elf-gdb/17.1_20260402/bin/riscv32-esp-elf-gdb
ELF=/Users/minh/.t3/worktrees/gdbminer/feat-esp32-c3-jsonrs-c3/example_firmware/esp32-c3_jsonrs/build-2/esp32-c3_jsonrs.ino.elf
$PY -I scripts/send_on_go.py /dev/cu.usbserial-11130 seeds/seed.11.in ready go > "$2.serial" 2>&1 &
SEND=$!
until [ -f ready ]; do sleep 0.2; done; sleep 1
~/.espressif/openocd-esp32/bin/openocd -c "set ESP_RTOS none" -c "set ESP_FLASH_SIZE 0" -f board/esp32c3-builtin.cfg -c "gdb port 3333" -c "telnet port disabled" -c "tcl port disabled" -c "adapter serial A0:F2:62:01:70:28" -c "adapter speed 40000" > "$2.openocd" 2>&1 &
OCD=$!
until grep -q "Listening on port 3333" "$2.openocd" || ! kill -0 $OCD 2>/dev/null; do sleep 0.2; done
timeout 90 $GDB -nx -q -batch -x "$1" $ELF > "$2" 2>&1; echo "gdb exit=$?" >> "$2"
sleep 2; kill $SEND 2>/dev/null; kill $OCD; wait $OCD 2>/dev/null
