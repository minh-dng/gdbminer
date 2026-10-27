"""Load TOML and validate shared settings plus the selected backend's settings."""

import argparse
import logging
import math
import tomllib
from pathlib import Path
from typing import Any

type Config = dict[str, Any]

GDB_PORT_PLACEHOLDER = "{gdb_port}"
ADAPTER_SERIAL_PLACEHOLDER = "{adapter_serial}"
TELNET_PORT_PLACEHOLDER = "{telnet_port}"
TCL_PORT_PLACEHOLDER = "{tcl_port}"


def _require(table: Config, key: str, expected: type | tuple[type, ...]) -> Any:
    """Require a config key to have a specific type, raising a TypeError if it does not."""

    value = table[key]
    types = expected if isinstance(expected, tuple) else (expected,)
    # Exact types exclude booleans from numeric settings.
    if type(value) not in types:
        names = " or ".join(t.__name__ for t in types)
        raise TypeError(f"Config {key=!r} must be {names}, got {type(value).__name__}")
    return value


def _validate_config(config: Config) -> None:
    for name, keys in {
        "BASIC": ("seed_directory", "output_directory", "binary_file", "eval_directory"),
        "GDB": ("gdb_path", "instance", "entrypoint", "input_buffer", "watchpoint_type"),
        "LOGS": ("log_level",),
    }.items():
        table = _require(config, name, dict)
        for key in keys:
            _require(table, key, str)

    # Keep logging's native error without configuring application loggers.
    logging.NullHandler(level=config["LOGS"]["log_level"])

    gdb = config["GDB"]
    for key in ("exitpoint", "ignore_functions_regex", "frame_arguments"):
        if key in gdb:
            _require(gdb, key, str)
    if _require(gdb, "watchpoint_count", int) <= 0:
        raise ValueError("GDB.watchpoint_count must be positive")
    if "watchpoint_min_distance" in gdb:
        raise ValueError("Move 'watchpoint_min_distance' from [GDB] to [GDB.esp32s3] (S3 only)")
    timeout = _require(gdb, "timeout", (int, float))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("GDB.timeout must be positive and finite")

    # Imported here: the tracer modules import Config from this module.
    from tracer.connection import InputChannel
    from tracer.instance import GDBInstance

    instance = gdb["instance"]
    if instance not in GDBInstance:
        raise ValueError(f"Unknown GDB instance type: {instance}")
    if instance == GDBInstance.VALGRIND:
        return

    _require(gdb, "gdb_server_path", str)
    if "gdb_server_address" in gdb:
        raise ValueError("Replace GDB.gdb_server_address with GDB.gdb_port, such as 3333")
    # Optional: `--gdb-port` can supply it, and `apply_overrides` then requires one.
    if "gdb_port" in gdb and not 0 < _require(gdb, "gdb_port", int) < 65536:
        raise ValueError("GDB.gdb_port must be between 1 and 65535")
    connection = _require(config, "Connection", dict)
    channel = _require(connection, "input_channel", str)
    if channel not in InputChannel:
        raise ValueError(f"Unsupported Connection.input_channel: {channel!r}")
    if "port" in connection:
        _require(connection, "port", str)
    if channel == InputChannel.ESP32_USB_SERIAL_JTAG:
        if "baud_rate" in connection:
            raise ValueError(f"Remove Connection.baud_rate: the '{channel}' port has no baud rate")
    elif _require(connection, "baud_rate", int) <= 0:
        raise ValueError("Connection.baud_rate must be positive")
    if "write_gap_sec" in connection and channel != InputChannel.ESP32_USB_SERIAL_JTAG:
        raise ValueError(
            f"Connection.write_gap_sec applies only to '{InputChannel.ESP32_USB_SERIAL_JTAG}'"
        )
    esp32_channels = (InputChannel.ESP32_UART, InputChannel.ESP32_USB_SERIAL_JTAG)
    if channel in esp32_channels:
        for key in ("dtr", "rts", "reset_pulse"):
            if key in connection:
                _require(connection, key, bool)
        for key in ("quiet_sec", "grace_sec", "reset_pulse_sec", "write_gap_sec"):
            if key in connection:
                seconds = _require(connection, key, (int, float))
                if not math.isfinite(seconds) or seconds <= 0:
                    raise ValueError(f"Connection.{key} must be positive and finite")

    if instance == GDBInstance.STM32:
        for key in ("dwt_function_reg", "dwt_watchpoint_workaround"):
            if key in gdb:
                raise ValueError(f"Move {key!r} from [GDB] to [GDB.stm32]")
        if "stm32" in config:
            raise ValueError("Move the [stm32] table to [GDB.stm32]")
        stm32 = _require(gdb, "stm32", dict)
        if "dwt_watchpoint_workaround" in stm32:
            _require(stm32, "dwt_watchpoint_workaround", bool)
        if stm32.get("dwt_watchpoint_workaround", True) or "dwt_function_reg" in stm32:
            _require(stm32, "dwt_function_reg", str)
    elif instance == GDBInstance.ESP32C3:
        from tracer.instance import HARDWARE_TRIGGER_COUNT

        c3 = _validate_esp32(
            config,
            "ESP32-C3",
            "esp32c3",
            ("hardware_trigger_slot", "breakpoint_always_inserted"),
            "RISC-V triggers",
        )
        if "breakpoint_always_inserted" in c3:
            _require(c3, "breakpoint_always_inserted", bool)
        slot = _require(c3, "hardware_trigger_slot", int)
        if slot < 0 or slot + gdb["watchpoint_count"] > HARDWARE_TRIGGER_COUNT:
            raise ValueError(
                "ESP32-C3 hardware_trigger_slot + watchpoint_count must fit slots "
                f"0..{HARDWARE_TRIGGER_COUNT - 1}"
            )
        if gdb["watchpoint_count"] == HARDWARE_TRIGGER_COUNT and gdb.get("exitpoint", ""):
            raise ValueError("ESP32-C3 exitpoint requires a free hardware trigger slot")
    elif instance == GDBInstance.ESP32S3:
        from tracer.instance.esp32s3_debug import DATA_BREAKPOINT_COUNT, WATCH_MIN_DISTANCE

        s3 = _validate_esp32(
            config,
            "ESP32-S3",
            "esp32s3",
            ("startup_delay", "usb_reset_command", "watchpoint_min_distance"),
            "Xtensa data breakpoints",
        )
        if "startup_delay" in s3:
            delay = _require(s3, "startup_delay", (int, float))
            if not math.isfinite(delay) or delay < 0:
                raise ValueError("GDB.esp32s3.startup_delay must be non-negative and finite")
        if "usb_reset_command" in s3:
            _require(s3, "usb_reset_command", str)
        if s3.get("reset_on_connect", False):
            raise ValueError(
                "ESP32-S3 reset_on_connect must be false: after OpenOCD's reset, the "
                "USB-Serial/JTAG device re-enumerates and the serial port fails"
            )
        if gdb["watchpoint_count"] > DATA_BREAKPOINT_COUNT:
            raise ValueError(
                f"ESP32-S3 watchpoint_count must be at most {DATA_BREAKPOINT_COUNT} (DBREAK pairs)"
            )
        if "watchpoint_min_distance" in s3 and _require(s3, "watchpoint_min_distance", int) <= 0:
            raise ValueError("GDB.esp32s3.watchpoint_min_distance must be positive")
        if (
            gdb["watchpoint_count"] > 1
            and s3.get("watchpoint_min_distance", 1) < WATCH_MIN_DISTANCE
        ):
            raise ValueError(
                f"GDB.esp32s3.watchpoint_min_distance must be at least {WATCH_MIN_DISTANCE}: "
                "one halt names one data breakpoint"
            )


def _validate_esp32(
    config: Config, chip: str, table: str, chip_keys: tuple[str, ...], observation: str
) -> Config:
    """Check the settings shared by the ESP32 backends and return the chip's `[GDB.<table>]`.

    `chip_keys` are the chip's own keys besides the shared ones; their types are the caller's to
    check. `observation` names the debug hardware in the error for ARM DWT settings.
    """
    from tracer.connection.sut_connection import InputChannel

    gdb = config["GDB"]
    connection = config["Connection"]
    channels = (InputChannel.ESP32_UART, InputChannel.ESP32_USB_SERIAL_JTAG)
    if connection["input_channel"] not in channels:
        raise ValueError(
            f"{chip} Connection.input_channel must be one of "
            + ", ".join(f"'{value}'" for value in channels)
        )
    for key in ("boot_delay", "max_input_size"):
        if key in connection:
            raise ValueError(f"Remove obsolete ESP32 serial setting {key!r} from [Connection]")
    if connection.get("rts", True) and not connection.get("reset_pulse", True):
        raise ValueError(f"{chip} Connection.reset_pulse = false requires rts = false")
    if table in config:
        raise ValueError(f"Move the [{table}] table to [GDB.{table}]")
    settings = _require(gdb, table, dict)
    startup_keys = ("startup_retry_interval", "startup_attempt_timeout")
    keys = ("rom_elf", "reset_on_connect", *startup_keys, *chip_keys)
    for key in keys:
        if key in gdb:
            raise ValueError(f"Move {key!r} from [GDB] to [GDB.{table}]")
    if "stm32" in gdb or any(
        key in source
        for source in (gdb, settings)
        for key in ("dwt_function_reg", "dwt_watchpoint_workaround")
    ):
        raise ValueError(f"{chip} uses {observation}; remove ARM DWT settings")
    if unknown := settings.keys() - set(keys):
        raise ValueError(f"Unknown [GDB.{table}] keys: {', '.join(sorted(unknown))}")
    if "rom_elf" in settings:
        _require(settings, "rom_elf", str)
    if "reset_on_connect" in settings:
        _require(settings, "reset_on_connect", bool)
    for key in startup_keys:
        if key in settings:
            seconds = _require(settings, key, (int, float))
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError(f"GDB.{table}.{key} must be positive and finite")
    return settings


def load_config(path: Path) -> Config:
    with path.expanduser().open("rb") as config_file:
        config = tomllib.load(config_file)
    _validate_config(config)
    return config


def _log_override(key: str, old: object, new: object, flag: str) -> None:
    if old is None:
        logging.info(f"{key} = {new!r} from {flag} (not set in the configuration)")
    elif old != new:
        logging.warning(f"{key}: {old!r} overridden by {flag} = {new!r}")
    else:
        logging.info(f"{key} = {new!r} from {flag} (same as the configuration)")


def add_override_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the flags for the machine-specific settings that `apply_overrides` fills in."""
    parser.add_argument("--port", type=str, help="Override Connection.port, the serial device.")
    parser.add_argument(
        "--adapter-serial",
        type=str,
        help="Fill {adapter_serial} in GDB.gdb_server_path, the debug adapter's serial number.",
    )
    parser.add_argument(
        "--gdb-port",
        type=int,
        help="Override GDB.gdb_port, the port of the GDB server and of the GDB connection to it.",
    )
    for console in ("telnet", "tcl"):
        parser.add_argument(
            f"--{console}-port",
            type=int,
            help=f"Fill {{{console}_port}} in GDB.gdb_server_path; disabled when omitted.",
        )


def apply_overrides(config: Config, args: argparse.Namespace) -> None:
    """Fill the machine-specific settings from `add_override_arguments` flags, in place.

    Configure or buffer logging first: it logs each value it uses. `Connection.port` and
    `GDB.gdb_port` are replaced by `--port` and `--gdb-port`, then validated with the
    configuration's rules. `{gdb_port}` and `{adapter_serial}` in `gdb_server_path` are replaced by
    the GDB port and `--adapter-serial`, which also fills `{adapter_serial}` in
    `GDB.esp32s3.usb_reset_command`. `{telnet_port}` and `{tcl_port}` take their flags' port
    numbers, or `disabled` when omitted so parallel OpenOCD instances do not share console ports.
    A flag overriding a different configured value is logged as a warning.

    Raises if no GDB port is set, a flag has no placeholder in `gdb_server_path` to reach the
    server, or `{adapter_serial}` stays unfilled: a silent fallback would start the server on the
    wrong board or port.
    """
    port, adapter_serial, gdb_port = args.port, args.adapter_serial, args.gdb_port
    telnet_port, tcl_port = args.telnet_port, args.tcl_port
    gdb = config["GDB"]
    if "gdb_server_path" not in gdb:
        if any(
            value is not None for value in (port, adapter_serial, gdb_port, telnet_port, tcl_port)
        ):
            raise ValueError(
                "--port, --adapter-serial, --gdb-port, --telnet-port and --tcl-port "
                "apply to hardware targets"
            )
        return

    if port is not None:
        connection = config["Connection"]
        _log_override("Connection.port", connection.get("port"), port, "--port")
        connection["port"] = port
    if gdb_port is not None:
        _log_override("GDB.gdb_port", gdb.get("gdb_port"), gdb_port, "--gdb-port")
        gdb["gdb_port"] = gdb_port
    _validate_config(config)
    if "gdb_port" not in gdb:
        raise ValueError("Set GDB.gdb_port in the configuration or pass --gdb-port")
    if not config["Connection"].get("port"):
        raise ValueError("Set Connection.port in the configuration or pass --port")
    for flag, value in (("--telnet-port", telnet_port), ("--tcl-port", tcl_port)):
        if value is not None and not 0 < value < 65536:
            raise ValueError(f"{flag} must be between 1 and 65535")
    ports = [value for value in (gdb["gdb_port"], telnet_port, tcl_port) if value is not None]
    if len(ports) != len(set(ports)):
        raise ValueError("GDB, Telnet and Tcl ports must be distinct")
    path = gdb["gdb_server_path"]
    for placeholder, flag, value in (
        (GDB_PORT_PLACEHOLDER, "--gdb-port", gdb_port),
        (ADAPTER_SERIAL_PLACEHOLDER, "--adapter-serial", adapter_serial),
        (TELNET_PORT_PLACEHOLDER, "--telnet-port", telnet_port),
        (TCL_PORT_PLACEHOLDER, "--tcl-port", tcl_port),
    ):
        if value is not None and placeholder not in path:
            raise ValueError(f"{flag} needs {placeholder} in GDB.gdb_server_path")
    for placeholder, value in (
        (GDB_PORT_PLACEHOLDER, gdb["gdb_port"]),
        (ADAPTER_SERIAL_PLACEHOLDER, adapter_serial),
        (TELNET_PORT_PLACEHOLDER, telnet_port if telnet_port is not None else "disabled"),
        (TCL_PORT_PLACEHOLDER, tcl_port if tcl_port is not None else "disabled"),
    ):
        if placeholder in path:
            if value is None:
                raise ValueError(f"GDB.gdb_server_path needs a value for {placeholder}")
            logging.info(f"GDB.gdb_server_path: {placeholder} -> {value}")
            path = path.replace(placeholder, str(value))
    gdb["gdb_server_path"] = path
    logging.info(f"GDB server command: {path}")
    # The S3 resets a wedged USB device between attach attempts and must name the same board.
    chip = gdb.get("esp32s3", {})
    reset = chip.get("usb_reset_command", "")
    if ADAPTER_SERIAL_PLACEHOLDER in reset:
        if adapter_serial is None:
            raise ValueError(
                f"GDB.esp32s3.usb_reset_command needs a value for {ADAPTER_SERIAL_PLACEHOLDER}"
            )
        chip["usb_reset_command"] = reset.replace(ADAPTER_SERIAL_PLACEHOLDER, adapter_serial)
        logging.info(
            f"GDB.esp32s3.usb_reset_command: {ADAPTER_SERIAL_PLACEHOLDER} -> {adapter_serial}"
        )
