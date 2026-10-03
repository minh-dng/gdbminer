# Handoff: ESP32-C3 GDBMiner work (2026-09-24)

> **Superseded (2026-10-01).** Historical record, kept for the thesis. The current method, configurations and
> results are in the [paper replica record](../esp32c3-paper-replica-2026-09-30/README.md). This historical record describes the firmware input-access bitmap and custom parsers, which were rejected as off-method; the tracer no longer supports the bitmap. Do not run
> the commands below against the current checkout.

**For review agents.** Read this first. Do not assume ESP32 tracing/mining is done.

Worktree: `impl/gdbminer.codex-rp2350-setup`  
Branch: `codex/fix-native-usb-transport`  
Related notes: `docs/thesis/esp32c3-onboard-2026-09-24/`, Obsidian `Uni/Thesis/Replication/ESP32-C3*` and `Paper GDBMiner replication cgi_decode json yxml 2026-09-24.md`

---

## 1. Status in one sentence

**ESP32-C3 firmware adapters and serial oracles are done and verified on hardware. GDBMiner `trace.py` / `mine.py` / `precision_recall.py` are NOT done on the C3 — blocked on a JTAG path.** A separate Docker Valgrind run completed the paper pipeline for desktop `cgi_decode` / `json` / `yxml` (that is not the C3).

| Layer | cgi_decode | json | xml/LibYxml |
| --- | --- | --- | --- |
| Firmware builds + flashes (ESP32-C3-DevKitM-1-N4X) | yes | yes | yes |
| Serial accept/reject oracle (not paper Table 8) | 1020/1020 | 1020/1020 | 1014/1020 |
| `trace.py` (GDB single-step + input events) | **blocked** | **blocked** | **blocked** |
| `mine.py` | blocked | blocked | blocked |
| `precision_recall.py` | blocked | blocked | blocked |

---

## 2. Hardware and host facts (verified)

| Item | Value |
| --- | --- |
| Board | ESP32-C3-DevKitM-1-N4X |
| Chip | ESP32-C3 AZ QFN32 rev v1.1, 4 MB XMC flash (esptool) |
| MAC | a0:f2:62:01:70:28 |
| Serial today | CP2102N USB-UART → `/dev/cu.usbserial-11130` |
| That port is | UART0 flash + SUT protocol **only** |
| That port is **not** | JTAG |
| Native USB Serial/JTAG | GPIO18 D−, GPIO19 D+ — **not wired to the Micro-USB connector** |
| OpenOCD `board/esp32c3-builtin.cfg` | `esp_usb_jtag: could not find or open device` |
| OpenOCD `board/esp32c3-ftdi.cfg` | `unable to open ftdi device` |
| J-Link | **Do not install** for this board path |

Correct debug chain (when JTAG exists):

```text
GDBMiner → gdb (riscv:rv32) → Espressif OpenOCD (esp32c3-builtin.cfg) → C3 USB-JTAG → core
```

Espressif OpenOCD already installed: `~/.espressif/openocd-esp32` (v0.12.0-esp32-20260831).  
Homebrew `gdb` 17.2 supports `riscv:rv32`.  
**Unblock:** USB breakout Mac D−/D+ → GPIO18/19 (or ESP-Prog / CMSIS-DAP). Then `openocd -f board/esp32c3-builtin.cfg` should see `esp_usb_jtag`.

---

## 3. Why not hardware watchpoints (design constraint)

Audited Espressif OpenOCD disables RISC-V triggers around `riscv_openocd_step`. A post-step `hit` bit cannot recover a read that happened while triggers were off. This is **source-level** evidence (already in thesis notes), not a board measurement.

Therefore the C3 adapters use the **same strategy as `rp2350_riscv`**: firmware `input_accessed[]` bitmap + `input_access_bitmap` in config. `STM32Instance.read_input_access_bitmap` already converts set bits into `read-watchpoint-trigger` events. No ARM `DWT_FUNCTIONn` polling.

`tracked_read` must see **every** input byte. Parsers are instrumented accordingly (`extern "C"` so GDB symbols stay `cgi_decode` / `parse_json` / `parse_xml` / `tracked_read` / `buf` / `input_accessed`).

---

## 4. What was added (adapters; originals left alone)

### Firmware (`example_firmware/`)

| Path | SUT | Notes |
| --- | --- | --- |
| `esp32-c3_cgidecode/` | `cgi_decode` | Classic body + `tracked_read` |
| `esp32-c3_json/` | `parse_json` | Full JSON value; leading zeros rejected (RFC 8259) |
| `esp32-c3_xml/` | `parse_xml` | LibYxml / `yxml_parse` stream; no `yxml_eof` (matches `stm32_libyxml`) |

Shared pattern: `buf[128]`, `input_accessed[128]`, serial protocol `A` + `uint32` LE length + payload + `0x00`/`0xFF`, PlatformIO `esp32-c3-devkitm-1` + Arduino, `-O0 -g3`.

Do **not** edit `stm32_*` or `rp2350_*` unless a reviewer finds a shared bug.

### Tracer adapters (`src/`)

| File | Role |
| --- | --- |
| `tracer/instance/esp32c3_instance.py` | Thin `STM32Instance` subclass (bitmap path; OpenOCD `monitor reset halt`) |
| `tracer/connection/esp32_serial_connection.py` | Open UART with DTR released + EN pulse (default `SerialConnection` can leave C3 in reset/download) |
| `tracer/connection/sut_connection.py` | One new arm: `input_channel = esp32-serial` |
| `tracer/gdb_tracer.py` | One factory case: `instance = esp32c3` |

Pre-existing and reused without redesign: `input_access_bitmap` / `input_access_bitmap_size` in `stm32_instance.py` and `gdb_tracer.py` (from the RP2350 work on this branch).

### Configs

`example_firmware/esp32_{cgidecode,json,xml}/configuration/configuration.ini`

- `instance = esp32c3`
- `input_channel = esp32-serial`
- `input_access_bitmap = input_accessed`, `input_access_bitmap_size = 128`
- `dwt_watchpoint_workaround = false`
- `ignore_functions_regex = ^tracked_read$`
- `gdb_path = /opt/homebrew/bin/gdb`
- `gdb_server_path = ~/.espressif/openocd-esp32/bin/openocd … -f board/esp32c3-builtin.cfg`
- entrypoints: `cgi_decode` / `parse_json` / `parse_xml`

### Tools

`example_firmware/*/tools/serial_smoke.py` — host oracle vs device accept/reject.

---

## 5. Toolchain notes (macOS arm64)

1. PlatformIO `toolchain-riscv32-esp@8.4.0` is **x86_64 only**. Rosetta was unavailable.
2. Replaced with Espressif crosstool-NG `riscv32-esp-elf-16.1.0_20260609-aarch64-apple-darwin`, pinned via `platform_packages = toolchain-riscv32-esp@file://…` and version metadata `8.4.0+2021r2-patch5` so PIO does not reinstall x86.
3. Flags: `-march=rv32imc_zicsr_zifencei -mabi=ilp32` (newer gas requires explicit `zicsr`).
4. `src/toolchain_stubs.c`: `_cleanup_r`, `_Unwind_SetEnableExceptionFdeSorting` for newlib skew vs prebuilt Arduino core.
5. Espressif OpenOCD arm64 tarball (not Homebrew OpenOCD — that lacks `esp32c3-*.cfg`).

---

## 6. Serial results (what actually ran on the C3)

Protocol matches `serial_connection.py`. Oracles: cgi (hex decode rules), json (`json.loads`), xml (Python expat stream, no eof).

| Target | Seeds | Eval (1000) | Notes |
| --- | --- | --- | --- |
| cgi_decode | 20/20 | 1000/1000 | |
| parse_json | 20/20 | 1000/1000 | After leading-zero fix |
| parse_xml | 20/20 | 994/1000 | 6 eval cases: **duplicate attribute names** (yxml accepts redefinition; expat rejects). Same class of disagreement as paper §5.3 SVG++. |

**These are not Table 8 precision/recall.** No grammar was mined from the C3.

---

## 7. What was **not** done on the C3 (reviewers: do not overclaim)

1. **`trace.py` on ESP32-C3** — never completed. `open_sut_instance` starts OpenOCD; no JTAG device.
2. **`mine.py` / `precision_recall.py` on ESP32-C3** — never run (need traces).
3. **Paper Table 8 comparison for C3** — impossible until (1)–(2).
4. **Hardware watchpoint / DWT path on C3** — intentionally unused (see §3).
5. **SEGGER J-Link** — not installed; not required if native USB-JTAG is used.

A mid-session attempt to `GDBTracer.open_sut_instance` failed in the serial process (stdin spawn + no board handshake in one try) **and** would have failed at OpenOCD anyway. Do not treat that as a tracer bug until JTAG is up.

---

## 8. Related but different: paper pipeline on Docker Valgrind

For contrast only. Same three logical targets (`cgi_decode`, `json`, `yxml`/LibYxml) on **host**, image `gdbminer:arm64`, aarch64 rebuilds of `example_programs/*.c`:

| Target | P | R | F1 | Trace | Mine |
| --- | --- | --- | --- | --- | --- |
| cgi_decode | 1.000 | 1.000 | 1.000 | ~120 s | ~71 s |
| json | 1.000 | 0.668 | 0.801 | ~131 s | ~16 s |
| yxml | 0.983 | 0.767 | 0.862 | ~605 s | ~890 s |

Paper Table 8 (STM32 embedded) for comparison is in `GDBMiner benchmark limitations` / the replication note. **Do not mix these with C3 serial percentages.**

---

## 9. Suggested review checklist

1. Confirm §1 status claim is accurate (C3 trace/mine blocked).
2. Review adapter surface area: only factory + `esp32-serial` channel should touch core.
3. Review `tracked_read` coverage in `esp32-c3_json` / `esp32-c3_xml` (missed input byte ⇒ wrong grammar later).
4. Review `esp32_serial_connection.py` DTR/RTS reset sequence vs DevKitM-1 auto-reset circuit.
5. Confirm xml oracle mismatches (duplicate attrs) are documented as SUT/oracle skew, not tracer bugs.
6. Check configs: `input_access_bitmap_size = 128` matches `FUZZ_INPUT_SIZE` (eval max is 96 bytes).
7. After JTAG: run one seed only first (`trace.py`), confirm watchpoint/bitmaps events in the trace, then 20 seeds, then `mine.py` + `precision_recall.py`.

---

## 10. Exact commands once JTAG is wired

```bash
# sanity
~/.espressif/openocd-esp32/bin/openocd \
  -s ~/.espressif/openocd-esp32/share/openocd/scripts \
  -f board/esp32c3-builtin.cfg
# expect: esp_usb_jtag found, halt at startup, GDB :3333

cd impl/gdbminer.codex-rp2350-setup
# one seed first
# edit configuration seed_directory to a dir with only input.1

PYTHONPATH=src .venv/bin/python src/tracer/trace.py \
  --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini

PYTHONPATH=src .venv/bin/python src/miner/mine.py \
  --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini

PRECISION_SET_SIZE=1000 PYTHONPATH=src .venv/bin/python src/eval/precision_recall.py \
  --config example_firmware/esp32-c3_cgidecode/configuration/configuration.ini \
  --out output/esp32-c3_cgidecode.20.gdbminer.result
```

Repeat for `esp32-c3_json` and `esp32-c3_xml`. Record trace/mine wall times (expect C3 tracing to be **slow**, closer to Table 8 than to Valgrind).

---

## 11. File index (new / relevant)

```text
example_firmware/esp32-c3_cgidecode/**     # firmware + config + tools + seeds/eval
example_firmware/esp32-c3_json/**
example_firmware/esp32-c3_xml/**
src/tracer/instance/esp32c3_instance.py
src/tracer/connection/esp32_serial_connection.py
src/tracer/connection/sut_connection.py  # esp32-serial arm
src/tracer/gdb_tracer.py                 # case "esp32c3"
docs/thesis/esp32c3-onboard-2026-09-24/
  RESULTS.md
  PAPER-PIPELINE-STATUS.md
  HANDOFF-ESP32-C3.md                    # this file
output/paper-replication-2026-09-24/     # desktop Valgrind batch
output/paper-seq-2026-09-24/             # sequential json then yxml
```

Obsidian: `Replication/ESP32-C3*.md`, `Paper GDBMiner replication cgi_decode json yxml 2026-09-24.md`.
