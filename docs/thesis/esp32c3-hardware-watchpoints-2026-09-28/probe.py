"""Run an existing XML firmware load under continue or stepi, without flashing."""

import argparse
import hashlib
import re
import subprocess
import threading
import time
from pathlib import Path

import serial

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["continue", "stepi", "raw-step"])
parser.add_argument("--trial", default="1")
args = parser.parse_args()
elf = ROOT / "example_firmware/esp32-c3_xml/.pio/build/esp32-c3-devkitm-1/firmware.elf"
assert (
    hashlib.sha256(elf.read_bytes()).hexdigest()
    == "fce044feb1e09ef205c33e59e4d414506313969d61c1b2b44ee53979f6075c16"
), "Probe addresses require the recorded XML ELF"
prefix = f"{args.mode}-{args.trial}"
flag = BASE / "send-input"
flag.unlink(missing_ok=True)
log = (BASE / f"{prefix}-openocd.log").open("w")

s = serial.Serial()
s.port = "/dev/cu.usbserial-11110"
s.baudrate = 115200
s.timeout = 0.2
s.dtr = False
s.rts = False
s.open()
time.sleep(0.5)
server = subprocess.Popen(
    [
        "/Users/dan173/.espressif/openocd-esp32/bin/openocd",
        "-s",
        "/Users/dan173/.espressif/openocd-esp32/share/openocd/scripts",
        "-c",
        "set ESP_RTOS none",
        "-f",
        "board/esp32c3-builtin.cfg",
        "-c",
        "adapter speed 1000",
        "-c",
        "gdb port 3334",
        "-c",
        "tcl port 6667",
        "-c",
        "telnet port 4445",
    ],
    stdout=log,
    stderr=subprocess.STDOUT,
)
stop = threading.Event()


def feed():
    while not stop.is_set() and not flag.exists():
        time.sleep(0.05)
    s.reset_input_buffer()
    while not stop.is_set():
        if s.read(1) == b"\xa5":
            s.write(b"\x04\x00\x00\x00<a/>")
            print("Sent <a/>", flush=True)
            return


thread = threading.Thread(target=feed)
thread.start()
script = BASE / f"{prefix}.gdb"
gdb_text = (
    """set pagination off
set confirm off
set remotetimeout 10
target extended-remote :3334
monitor reset halt
thbreak parse_xml
python open("""
    + repr(str(flag))
    + """, 'w').close()
continue
printf "PARSER_ENTRY pc=%p\\n", $pc
thbreak *0x42000064
continue
printf "BEFORE_LOAD pc=%p address=%p value=%u\\n", $pc, $a5, *(unsigned char*)$a5
x/i $pc
python assert int(gdb.parse_and_eval("*(unsigned int*)$pc")) == 0x0007c783, "Expected lbu a5,0(a5)"
rwatch -location *(unsigned char*)$a5
python
hits=[]
def stopped(event):
    if isinstance(event, gdb.BreakpointEvent):
        hits.extend(b.type for b in event.breakpoints if b.type == gdb.BP_READ_WATCHPOINT)
gdb.events.stop.connect(stopped)
end
"""
    + ("thbreak *0x42000068\ncontinue\n" if args.mode == "continue" else "stepi\n")
    + """printf "AFTER_LOAD pc=%p value=%u\\n", $pc, $a5
python print("HARDWARE_READ_WATCHPOINT_HITS=" + str(len(hits)))
delete breakpoints
monitor reset run
detach
quit
"""
)
if args.mode == "raw-step":
    gdb_text = gdb_text.replace(
        "rwatch -location *(unsigned char*)$a5",
        """monitor reg tselect 0
monitor reg tdata1 0
monitor reg tdata2 0x3fc8d680
monitor reg tdata1 0x28001041
monitor reg tdata1
monitor reg tdata2""",
    )
    gdb_text = gdb_text.replace(
        "delete breakpoints",
        """monitor reg dcsr
monitor reg tdata1
monitor reg tdata1 0
stepi
printf "RECOVERY pc=%p value=%u\\n", $pc, $a5
delete breakpoints""",
    )
else:
    gdb_text = gdb_text.replace(
        "rwatch -location *(unsigned char*)$a5",
        "monitor debug_level 3\nrwatch -location *(unsigned char*)$a5",
    )
script.write_text(gdb_text)
try:
    time.sleep(1)
    result = subprocess.run(
        ["/opt/homebrew/bin/gdb", "-q", "-nx", "-batch", str(elf), "-x", str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=35,
    )
    output = result.stdout + result.stderr
    (BASE / f"{prefix}-gdb.log").write_text(output)
    print(output)
    assert result.returncode == 0, result.returncode
    assert "BEFORE_LOAD pc=0x42000064" in output and "value=60" in output, (
        "Load precondition failed"
    )
    if args.mode == "raw-step":
        dcsr = int(re.search(r"dcsr \(/32\): (0x[0-9a-f]+)", output)[1], 16)
        values = [int(v, 16) for v in re.findall(r"tdata1 \(/32\): (0x[0-9a-f]+)", output)]
        assert (dcsr >> 6) & 7 == 2, "Expected hardware trigger halt cause"
        assert any(v & (1 << 20) for v in values), "Expected trigger hit bit"
        assert "AFTER_LOAD pc=0x42000064" in output, "Expected before-load halt"
        assert "RECOVERY pc=0x42000068 value=60" in output, (
            "Load did not complete after disabling trigger"
        )
    else:
        assert "HARDWARE_READ_WATCHPOINT_HITS=1" in output, "Hardware read watchpoint did not fire"
finally:
    stop.set()
    thread.join(timeout=1)
    s.close()
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
    log.close()
    flag.unlink(missing_ok=True)
