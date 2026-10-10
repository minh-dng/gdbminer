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
        raise TypeError(f"Config key {key!r} must be {names}, got {type(value).__name__}")
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
    for key in ("exitpoint", "ignore_functions_regex"):
        if key in gdb:
            _require(gdb, key, str)
    if _require(gdb, "watchpoint_count", int) <= 0:
        raise ValueError("GDB.watchpoint_count must be positive")
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

        if channel not in esp32_channels:
            raise ValueError(
                "ESP32-C3 Connection.input_channel must be one of "
                + ", ".join(f"'{value}'" for value in esp32_channels)
            )
        for key in ("boot_delay", "max_input_size"):
            if key in connection:
                raise ValueError(f"Remove obsolete ESP32 serial setting {key!r} from [Connection]")
        if connection.get("rts", True) and not connection.get("reset_pulse", True):
            raise ValueError("ESP32-C3 Connection.reset_pulse = false requires rts = false")
        if "esp32c3" in config:
            raise ValueError("Move the [esp32c3] table to [GDB.esp32c3]")
        c3 = _require(gdb, "esp32c3", dict)
        c3_keys = (
            "rom_elf",
            "hardware_trigger_slot",
            "reset_on_connect",
            "breakpoint_always_inserted",
            "startup_retry_interval",
        )
        for key in c3_keys:
            if key in gdb:
                raise ValueError(f"Move {key!r} from [GDB] to [GDB.esp32c3]")
        if "stm32" in gdb or any(
            key in table
            for table in (gdb, c3)
            for key in ("dwt_function_reg", "dwt_watchpoint_workaround")
        ):
            raise ValueError("ESP32-C3 uses RISC-V triggers; remove ARM DWT settings")
        if unknown := c3.keys() - set(c3_keys):
            raise ValueError(f"Unknown [GDB.esp32c3] keys: {', '.join(sorted(unknown))}")
        if "rom_elf" in c3:
            _require(c3, "rom_elf", str)
        for key in ("reset_on_connect", "breakpoint_always_inserted"):
            if key in c3:
                _require(c3, key, bool)
        if "startup_retry_interval" in c3:
            interval = _require(c3, "startup_retry_interval", (int, float))
            if not math.isfinite(interval) or interval <= 0:
                raise ValueError("GDB.esp32c3.startup_retry_interval must be positive and finite")
        slot = _require(c3, "hardware_trigger_slot", int)
        if slot < 0 or slot + gdb["watchpoint_count"] > HARDWARE_TRIGGER_COUNT:
            raise ValueError(
                "ESP32-C3 hardware_trigger_slot + watchpoint_count must fit slots "
                f"0..{HARDWARE_TRIGGER_COUNT - 1}"
            )
        if gdb["watchpoint_count"] == HARDWARE_TRIGGER_COUNT and gdb.get("exitpoint", ""):
            raise ValueError("ESP32-C3 exitpoint requires a free hardware trigger slot")
        if gdb["watchpoint_type"] != "(char*)":
            raise ValueError("ESP32-C3 watchpoint_type must be '(char*)'")


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

    Call it after the logging setup: it logs each value it uses. `Connection.port` and
    `GDB.gdb_port` are replaced by `--port` and `--gdb-port`, then validated with the
    configuration's rules. `{gdb_port}` and `{adapter_serial}` in `gdb_server_path` are replaced by
    the GDB port and `--adapter-serial`. `{telnet_port}` and `{tcl_port}` take their flags' port
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
        _log_override("Connection.port", connection["port"], port, "--port")
        connection["port"] = port
    if gdb_port is not None:
        _log_override("GDB.gdb_port", gdb.get("gdb_port"), gdb_port, "--gdb-port")
        gdb["gdb_port"] = gdb_port
    _validate_config(config)
    if "gdb_port" not in gdb:
        raise ValueError("Set GDB.gdb_port in the configuration or pass --gdb-port")
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
