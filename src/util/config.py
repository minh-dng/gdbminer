"""Load TOML and validate shared settings plus the selected backend's settings."""

import logging
import math
import tomllib
from pathlib import Path
from typing import Any

type Config = dict[str, Any]


def require(table: Config, key: str, expected: type | tuple[type, ...]) -> Any:
    """Require a config key to have a specific type, raising a TypeError if it does not."""

    value = table[key]
    types = expected if isinstance(expected, tuple) else (expected,)
    # Exact types exclude booleans from numeric settings.
    if type(value) not in types:
        names = " or ".join(t.__name__ for t in types)
        raise TypeError(f"Config key {key!r} must be {names}, got {type(value).__name__}")
    return value


def validate_config(config: Config) -> None:
    for name, keys in {
        "BASIC": ("seed_directory", "output_directory", "binary_file", "eval_directory"),
        "GDB": ("gdb_path", "instance", "entrypoint", "input_buffer", "watchpoint_type"),
        "LOGS": ("log_level",),
    }.items():
        table = require(config, name, dict)
        for key in keys:
            require(table, key, str)

    # Keep logging's native error without configuring application loggers.
    logging.NullHandler(level=config["LOGS"]["log_level"])

    gdb = config["GDB"]
    for key in ("exitpoint", "ignore_functions_regex"):
        if key in gdb:
            require(gdb, key, str)
    if require(gdb, "watchpoint_count", int) <= 0:
        raise ValueError("GDB.watchpoint_count must be positive")
    timeout = require(gdb, "timeout", (int, float))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("GDB.timeout must be positive and finite")

    # Imported here: the tracer modules import Config from this module.
    from tracer.connection.sut_connection import InputChannel
    from tracer.instance.sut_instance import GDBInstance

    instance = gdb["instance"]
    if instance not in GDBInstance:
        raise ValueError(f"Unknown GDB instance type: {instance}")
    if instance == GDBInstance.VALGRIND:
        return

    for key in ("gdb_server_path", "gdb_server_address"):
        require(gdb, key, str)
    connection = require(config, "Connection", dict)
    if require(connection, "input_channel", str) not in InputChannel:
        raise ValueError(f"Unsupported Connection.input_channel: {connection['input_channel']!r}")
    require(connection, "port", str)
    if require(connection, "baud_rate", int) <= 0:
        raise ValueError("Connection.baud_rate must be positive")
    if connection["input_channel"] == InputChannel.ESP32_UART:
        for key in ("dtr", "rts", "reset_pulse"):
            if key in connection:
                require(connection, key, bool)
        for key in ("quiet_sec", "grace_sec", "reset_pulse_sec"):
            if key in connection:
                seconds = require(connection, key, (int, float))
                if not math.isfinite(seconds) or seconds <= 0:
                    raise ValueError(f"Connection.{key} must be positive and finite")

    if instance == GDBInstance.STM32:
        for key in ("dwt_function_reg", "dwt_watchpoint_workaround"):
            if key in gdb:
                raise ValueError(f"Move {key!r} from [GDB] to [GDB.stm32]")
        if "stm32" in config:
            raise ValueError("Move the [stm32] table to [GDB.stm32]")
        stm32 = require(gdb, "stm32", dict)
        if "dwt_watchpoint_workaround" in stm32:
            require(stm32, "dwt_watchpoint_workaround", bool)
        if stm32.get("dwt_watchpoint_workaround", True) or "dwt_function_reg" in stm32:
            require(stm32, "dwt_function_reg", str)


def load_config(path: Path) -> Config:
    with path.expanduser().open("rb") as config_file:
        config = tomllib.load(config_file)
    validate_config(config)
    return config
