"""Hardware-free regression check: PYTHONPATH=src python tests/test_config.py."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tracer import trace
from tracer.gdb_tracer import GDBTracer
from tracer.instance.msp430_instance import MSP430Instance
from tracer.instance.stm32_instance import STM32Instance
from util.config import load_config, validate_config

ROOT = Path(__file__).resolve().parents[1]
JSON_CONFIG = ROOT / "example_programs/json/configuration/configuration.toml"
STM32_CONFIG = ROOT / "example_firmware/stm32_libyxml/configuration/configuration.toml"


def test_config():
    for path in ROOT.glob("example_*/**/configuration*.toml"):
        load_config(path)

    desktop = load_config(JSON_CONFIG)
    stm32 = load_config(STM32_CONFIG)

    # Mutate parsed dictionaries instead of maintaining a second TOML fixture.
    for base, table, key, invalids in (
        (desktop, "GDB", "watchpoint_count", (False, True, 0, -1, "4", 4.0)),
        (desktop, "GDB", "timeout", (True, "30", 0, -1, float("inf"), float("nan"))),
        (desktop, "GDB", "entrypoint", (0x8001000,)),
        (desktop, "GDB", "input_buffer", (0x20000000,)),
        (desktop, "GDB", "exitpoint", (0x8002000,)),
        (desktop, "GDB", "instance", ("STM32", "arm")),
        (desktop, "LOGS", "log_level", ("INVALID",)),
        (stm32, "stm32", "dwt_function_reg", (0xE0001028,)),
        (stm32, "stm32", "dwt_watchpoint_workaround", ("false", "true", 0, 1)),
        (stm32, "Connection", "input_channel", ("SERIAL", "usb")),
    ):
        for value in invalids:
            config = deepcopy(base)
            target = config["GDB"][table] if table == "stm32" else config[table]
            target[key] = value
            # Exercise the CLI's loader, before any directory or target is created.
            with (
                patch("sys.argv", ["trace", "--config", str(JSON_CONFIG)]),
                patch("util.config.tomllib.load", return_value=config),
                patch(
                    "tracer.trace.create_output_dir",
                    side_effect=AssertionError("Invalid config reached trial-directory creation"),
                ),
                patch("tracer.trace.generate_trace") as generate_trace,
            ):
                try:
                    trace.main()
                except (TypeError, ValueError) as exc:
                    expected = f"Unknown level: {value!r}" if key == "log_level" else key
                    assert expected in str(exc), str(exc)
                else:
                    raise AssertionError(f"Accepted {key} = {value!r}")
                generate_trace.assert_not_called()

    for key, value in (("dwt_watchpoint_workaround", False), ("dwt_function_reg", "0x1000")):
        config = deepcopy(stm32)
        config["GDB"][key] = value
        try:
            validate_config(config)
        except ValueError as exc:
            assert "[GDB.stm32]" in str(exc)
        else:
            raise AssertionError(f"Accepted misplaced {key}")

    config = deepcopy(stm32)
    config["stm32"] = config["GDB"].pop("stm32")
    try:
        validate_config(config)
    except ValueError as exc:
        assert "[GDB.stm32]" in str(exc)
    else:
        raise AssertionError("Accepted obsolete top-level STM32 table")

    desktop["GDB"].pop("exitpoint")
    desktop["GDB"]["timeout"] = 0.5
    validate_config(desktop)
    assert GDBTracer(desktop).exitpoint == ""
    assert GDBTracer.open_sut_instance(desktop).timeout == 0.5

    assert STM32Instance(stm32, "").dwt_watchpoint_workaround is True
    stm32["GDB"]["stm32"] = {"dwt_watchpoint_workaround": False}
    validate_config(stm32)
    assert STM32Instance(stm32, "").dwt_watchpoint_workaround is False

    # MSP430 uses the shared server settings and requires no DWT table.
    stm32["GDB"].pop("stm32")
    stm32["GDB"].update(
        instance="msp430",
        gdb_path="'/opt/tool chain/gdb' --quiet",
        gdb_server_path="'/opt/tool chain/mspdebug' gdb",
    )
    validate_config(stm32)
    instance = GDBTracer.open_sut_instance(stm32)
    assert isinstance(instance, MSP430Instance)
    assert instance.gdb_with_args == ["/opt/tool chain/gdb", "--quiet"]
    assert instance.gdb_server_path_with_args == ["/opt/tool chain/mspdebug", "gdb"]


if __name__ == "__main__":
    test_config()
    print("Configuration regression checks passed")
