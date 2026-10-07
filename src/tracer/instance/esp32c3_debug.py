"""ESP32-C3 RV32 debug values.

See `example_firmware/ESP32-C3 DevKitM-1-N4X.md#debug-register-values`.

Register source, pinned to the documented OpenOCD release:
https://github.com/espressif/openocd-esp32/blob/v0.12.0-esp32-20260831/src/target/riscv/debug_defines.h
"""

from enum import IntEnum, IntFlag, auto, unique


@unique
class DCSRCause(IntEnum):
    """`CSR_DCSR_CAUSE_*` encodings, in the source header's numeric order.

    `dcsr.cause` records why the hart entered debug mode.
    """

    EBREAK = 1
    """An `ebreak` instruction ran (a software breakpoint)."""
    TRIGGER = auto()
    """A trigger with `MControlFlag.ACTION_DEBUG_MODE` matched: a read trigger or a hardware
    breakpoint."""
    HALTREQ = auto()
    STEP = auto()
    """A single step completed."""
    RESETHALTREQ = auto()
    GROUP = auto()
    OTHER = auto()


DCSR_CAUSE_OFFSET = 6
"""Bit offset of `dcsr.cause` (`CSR_DCSR_CAUSE_OFFSET`)."""


@unique
class DCSRMask(IntFlag):
    """`CSR_DCSR_CAUSE` and `CSR_DCSR_STEPIE` register masks."""

    CAUSE = 0x7 << DCSR_CAUSE_OFFSET
    """`dcsr.cause`; shift right by `DCSR_CAUSE_OFFSET` to get a `DCSRCause`."""
    STEPIE = 1 << 11
    """Interrupts enabled during single steps.

    Must be 0: otherwise an interrupt handler could run inside a step, and its instructions and
    loads would enter the trace.
    """


@unique
class MControlFlag(IntFlag):
    """`CSR_MCONTROL_*` RV32 bits used to own, disable and validate read triggers.

    They are bits of `tdata1` for an `mcontrol` trigger (RISC-V debug specification, type 2).
    """

    LOAD = auto()
    """Match loads."""
    STORE = auto()
    """Match stores."""
    EXECUTE = auto()
    """Match instruction fetches, as a hardware breakpoint does."""
    M = 1 << 6
    """Match in machine mode, where the firmware runs."""
    ACTION_DEBUG_MODE = 1 << 12
    """On a match, halt the hart into debug mode instead of raising a breakpoint exception that
    the firmware would handle."""
    HIT = 1 << 20
    """Set by the hardware when the trigger matches."""
    DMODE = 1 << 27
    """Only debug mode (OpenOCD) may write the trigger, so the firmware cannot reprogram or clear
    it while it runs."""
    TYPE_MCONTROL = 2 << 28
    """`type` field value 2: an address and data match trigger."""


MCONTROL_ACCESS_MASK = MControlFlag.LOAD | MControlFlag.STORE | MControlFlag.EXECUTE
"""Access bits of `tdata1`; a slot with any of them set is active."""
MCONTROL_CONTROL_MASK = 0xF81FFFFF
"""`tdata1` bits compared on readback: all except the read-only `CSR_MCONTROL_MASKMAX(32)`, bits
26:21."""

HARDWARE_TRIGGER_COUNT = 8
"""Trigger slots on the ESP32-C3, shared by hardware breakpoints and watchpoints.

https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/jtag-debugging/tips-and-quirks.html#breakpoints-and-watchpoints-available
"""
