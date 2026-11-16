"""Find a board's USB serial devices by USB serial number, and wait while one is unplugged.

A replug can move `/dev/cu.usbmodem*`, so a device is named by its USB serial number and its path
is looked up with pyserial before every stage. An unplugged device stops the run until the user
types C, because only a person can plug it back in; that wait is not a failed attempt.
"""

from dataclasses import dataclass

from serial.tools import list_ports

ADAPTER = "debug adapter"
UART = "UART bridge"


@dataclass(frozen=True)
class Device:
    path: str
    serial: str
    description: str


def list_devices() -> list[Device]:
    """The USB serial devices that report a serial number, sorted by path."""
    devices = [
        Device(port.device, serial, port.description)
        for port in list_ports.comports()
        if (serial := port.serial_number)
    ]
    return sorted(devices, key=lambda device: device.path)


def present() -> dict[str, str]:
    """USB serial number to path of every device present now."""
    return {device.serial: device.path for device in list_devices()}


@dataclass(frozen=True)
class Board:
    """The USB serial numbers of one board's devices by role (`ADAPTER`, `UART`)."""

    serials: dict[str, str]

    def unplugged(self) -> list[str]:
        """The roles whose device is not present now."""
        return self._missing(present())

    def paths(self) -> dict[str, str]:
        """Each role's current path. While a device is unplugged, wait for the user to type C."""
        while missing := self._missing(now := present()):
            for role in missing:
                print(f"The {role} (USB serial {self.serials[role]}) is unplugged.")
            while input("Plug it in, then type C to continue: ").strip().upper() != "C":
                pass
        # The paths come from the same lookup that found every device present.
        return {role: now[serial] for role, serial in self.serials.items()}

    def _missing(self, now: dict[str, str]) -> list[str]:
        return [role for role, serial in self.serials.items() if serial not in now]
