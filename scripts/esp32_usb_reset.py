#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyusb==1.3.1"]
# ///
"""Reset (USB port reset) one Espressif USB-Serial/JTAG device, selected by its serial number.

Recovers a device whose control endpoint stopped answering: OpenOCD then reports
`libusb_get_string_descriptor_ascii() failed`, and esptool `No serial data`. The ESP32-S3 backend
runs this as `GDB.esp32s3.usb_reset_command` between two attach attempts:

    uv run scripts/esp32_usb_reset.py --serial E8:06:90:95:80:6C

Needs libusb (`brew install libusb` on macOS).
"""

# SPDX-License-Identifier: AGPL-3.0

import argparse
import plistlib
import subprocess
import sys
import time
from pathlib import Path

import usb.backend.libusb1
import usb.core

ESPRESSIF_VID, USB_SERIAL_JTAG_PID = 0x303A, 0x1001
HOMEBREW_LIBUSB = Path("/opt/homebrew/lib/libusb-1.0.dylib")
SETTLE_SEC = 3
"""Time the device gets to enumerate again before the next attach."""


def macos_usb_location(serial: str) -> tuple[int, tuple[int, ...], int]:
    """Return the bus, port path and USB address of the device with `serial`.

    A wedged device cannot return its serial-number string, so libusb cannot match it. The I/O
    Registry kept the identity from the device's last enumeration, with its physical location;
    libusb reports the same location without asking the device.
    """
    registry = plistlib.loads(subprocess.check_output(["ioreg", "-a", "-p", "IOUSB", "-l"]))
    matches = []

    def visit(node):
        if isinstance(node, dict):
            if (
                str(node.get("USB Serial Number", "")).upper() == serial.upper()
                and node.get("idVendor") == ESPRESSIF_VID
                and node.get("idProduct") == USB_SERIAL_JTAG_PID
            ):
                matches.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(registry)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one cached USB identity for {serial}, got {len(matches)}")
    # locationID: bus in bits 31:24, then one port number per nibble from bit 23 down.
    location = matches[0]["locationID"]
    bus = location >> 24
    ports = []
    while location & 0xF00000:
        ports.append((location >> 20) & 0xF)
        location <<= 4
    if not ports:
        raise RuntimeError(f"Missing physical USB port for {serial}")
    return bus, tuple(ports), matches[0]["USB Address"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serial", required=True, help="USB serial number (the chip's MAC)")
    args = parser.parse_args()

    backend = usb.backend.libusb1.get_backend(
        find_library=lambda _: str(HOMEBREW_LIBUSB) if HOMEBREW_LIBUSB.exists() else None
    )
    devices = list(
        usb.core.find(
            find_all=True, idVendor=ESPRESSIF_VID, idProduct=USB_SERIAL_JTAG_PID, backend=backend
        )
    )
    if sys.platform == "darwin":
        location = macos_usb_location(args.serial)
        devices = [d for d in devices if (d.bus, d.port_numbers, d.address) == location]
    else:
        devices = [d for d in devices if (d.serial_number or "").upper() == args.serial.upper()]
    if len(devices) != 1:
        raise RuntimeError(f"Expected one USB device with serial {args.serial}, got {len(devices)}")
    devices[0].reset()
    time.sleep(SETTLE_SEC)
    print(f"Reset USB device {args.serial}")


if __name__ == "__main__":
    main()
