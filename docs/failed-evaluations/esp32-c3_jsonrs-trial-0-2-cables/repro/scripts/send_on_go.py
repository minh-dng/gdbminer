"""Open the UART (this resets the chip), wait for 'A', touch READY, wait for GO, send one seed."""
import os, struct, sys, time
import serial
port, path, ready, go = sys.argv[1:5]
s = serial.Serial(timeout=0.5); s.port, s.baudrate, s.dtr, s.rts = port, 9600, False, True
s.open(); time.sleep(0.05); s.rts = False
seen = b""; t0 = time.monotonic()
while time.monotonic() - t0 < 10:
    c = s.read(64); seen += c
    if seen.endswith(b"A") and not c: break
open(ready, "w").close(); print("ready after", len(seen), "boot bytes", flush=True)
while not os.path.exists(go): time.sleep(0.1)
time.sleep(1.0)  # let GDB resume the core
data = open(path, "rb").read(); s.write(struct.pack("<I", len(data)) + data); s.flush()
print("sent", len(data), "bytes", flush=True)
s.timeout = 60; print("result", s.read(1), flush=True); s.close()
