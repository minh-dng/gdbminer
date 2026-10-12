"""ESP32-S3 (Xtensa LX7) debug values and the instruction decoding used by the S3 backend.

See `example_firmware/ESP32-S3-Zero.md#debug-register-values`.

Register sources, pinned to the documented OpenOCD release:
https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/xtensa/xtensa_debug_module.h
https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/xtensa/xtensa.c
https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/tcl/target/xtensa-core-esp32s3.cfg

Chip values: ESP-IDF `components/soc/esp32s3/include/soc/soc.h`. Instruction encodings: Cadence,
Xtensa Instruction Set Architecture (ISA) Reference Manual, chapter 7 (instruction formats and
opcode maps).
"""

from enum import IntFlag, auto, unique


@unique
class DebugCause(IntFlag):
    """`DEBUGCAUSE_*` bits: why the core entered debug mode."""

    IC = auto()
    """ICOUNT: a single step completed."""
    IB = auto()
    """IBREAK: a hardware instruction breakpoint matched."""
    DB = auto()
    """DBREAK: a data breakpoint matched; `DEBUGCAUSE_DBNUM` names the one slot."""
    BI = auto()
    """A `BREAK` instruction ran (a software breakpoint)."""
    BN = auto()
    """A `BREAK.N` instruction ran (a software breakpoint)."""
    DI = auto()
    """Debug interrupt: OpenOCD asked the core to halt."""


DEBUGCAUSE_DBNUM_SHIFT = 8
"""Bit offset of `DEBUGCAUSE.DBNUM`, the data breakpoint that matched."""
DEBUGCAUSE_DBNUM_MASK = 0xF
"""Width mask of `DEBUGCAUSE.DBNUM` after the shift."""


@unique
class DBreakC(IntFlag):
    """`DBREAKC` access bits, as `xtensa_watchpoint_add` writes them."""

    LOAD = 1 << 30
    """Break before a load that reads the watched bytes (GDB `rwatch`)."""
    STORE = 1 << 31
    """Break before a store; the firmware's FreeRTOS stack guard uses this."""


DBREAKC_BYTE_MASK = 0x3F
"""`DBREAKC` bits 5:0 for a one-byte watch: every address bit is compared."""
DBREAKC_READ_BYTE = DBreakC.LOAD | DBREAKC_BYTE_MASK
"""`DBREAKC` of a one-byte read watchpoint, `0x4000003f`."""

DATA_BREAKPOINT_COUNT = 2
"""DBREAK pairs per core (`xtensa-core-esp32s3.cfg`: `dbreaknum 2`). The two instruction
breakpoints (`ibreaknum 2`) are a separate unit."""
WATCH_MIN_DISTANCE = 4
"""Bytes between two bytes watched in one run.

One halt names one data breakpoint, and the widest scalar load reads one aligned 32-bit word, so
two watched bytes at least four apart are never read by the same load.
"""

PRO_CPU_PRID = 0xCDCD
"""`PRID` of core 0, the core OpenOCD debugs with `ESP_ONLYCPU 1` (ESP-IDF `PRO_CPUID`)."""
MASK_ROM = range(0x40000000, 0x40060000)
"""Instruction-bus addresses of the mask ROM (`SOC_IROM_MASK_LOW` to `SOC_IROM_MASK_HIGH`)."""

ENTRY_BYTE0 = 0x36
"""First byte of `ENTRY`, the first instruction of every windowed-ABI function (op0 = 6, n = 3,
m = 0)."""


def load_width(insn: bytes) -> int | None:
    """Bytes read by a scalar load, or None for any other instruction.

    `L32I.N` (op0 = 8) and the LSAI group (op0 = 2), where the r field selects `L8UI`, `L16UI`,
    `L16SI`, `L32I` or `L32AI`.
    """
    op0 = insn[0] & 0xF
    if op0 == 0x8:
        return 4
    if op0 == 0x2:
        return {0: 1, 1: 2, 9: 2, 2: 4, 11: 4}.get(insn[1] >> 4)
    return None


def load_size(insn: bytes) -> int:
    """Instruction size of a load accepted by `load_width`: `L32I.N` is a 2-byte narrow
    instruction, the LSAI loads take 3 bytes."""
    return 2 if insn[0] & 0xF == 0x8 else 3


def l32r_register(insn: bytes) -> int | None:
    """Target register of `L32R` (op0 = 1, RI16 format), else None."""
    return insn[0] >> 4 if insn[0] & 0xF == 0x1 else None


def jx_register(insn: bytes) -> int | None:
    """Register of `JX` (CALLX format, m = 2, n = 2), else None."""
    if insn[0] == 0xA0 and insn[1] >> 4 == 0 and insn[2] == 0:
        return insn[1] & 0xF
    return None


def is_windowed_call(insn: bytes) -> bool:
    """`CALL4/8/12` or `CALLX4/8/12`: the callee must start with `ENTRY`."""
    if insn[0] & 0xF == 0x5:  # CALLn; n = 0 is CALL0, which does not rotate the window
        return insn[0] >> 4 & 0x3 != 0
    return insn[0] in {0xD0, 0xE0, 0xF0} and insn[1] >> 4 == 0 and insn[2] == 0
