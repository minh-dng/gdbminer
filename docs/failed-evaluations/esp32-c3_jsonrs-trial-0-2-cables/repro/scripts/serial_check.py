"""Send seeds to the C3 jsonrs firmware over UART with no debugger; print each result byte."""
import struct, sys, time
import serial

port, seeds = sys.argv[1], sys.argv[2:]
s = serial.Serial(timeout=0.2)
s.port, s.baudrate, s.dtr, s.rts = port, 9600, False, True
s.open(); time.sleep(0.05); s.rts = False  # EN pulse: reset the chip
boot = b""; t0 = time.monotonic()
while time.monotonic() - t0 < 5:  # boot text, then 'A' followed by silence
    chunk = s.read(256); boot += chunk
    if boot.endswith(b"A") and not chunk:
        break
print("boot bytes:", len(boot), "tail:", boot[-80:])
for path in seeds:
    data = open(path, "rb").read()
    if not boot.endswith(b"A"):
        r = s.read(1)
    s.write(struct.pack("<I", len(data)) + data); s.flush()
    t = time.monotonic(); res = s.read(1); s.timeout = 3
    extra = s.read(200); s.timeout = 0.2
    print(f"{path.split('/')[-1]:12} len={len(data):3} result={res!r} after {time.monotonic()-t:.2f}s next={extra[:60]!r}")
    boot = extra
s.close()
