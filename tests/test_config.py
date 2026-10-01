"""Hardware-free check: PYTHONPATH=src python tests/test_config.py."""

import logging
import tempfile
import tomllib
from pathlib import Path

from tracer.gdb_tracer import GDBTracer
from tracer.instance.msp430_instance import MSP430Instance
from tracer.instance.stm32_instance import STM32Instance
from tracer.instance.valgrind_instance import ValgrindInstance
from util.config import load_config


def test_config():
    root = Path(__file__).resolve().parents[1]
    paths = sorted(root.glob("example_*/**/configuration*.toml"))
    assert len(paths) == 27
    for path in paths:
        config = load_config(path)
        assert isinstance(config["GDB"]["watchpoint_count"], int)
        assert isinstance(config["GDB"]["timeout"], int)
        assert isinstance(config["GDB"]["exitpoint"], str)
        assert "gdb_server_path" not in config["GDB"]
        assert "dwt_function_reg" not in config["GDB"]
        GDBTracer(config)
        instance = GDBTracer.open_sut_instance(config)
        assert isinstance(instance, (STM32Instance, ValgrindInstance))
        if isinstance(instance, STM32Instance):
            assert instance.dwt_function_reg == "0xe0001028"
            assert instance.dwt_watchpoint_workaround is True
        else:
            assert "stm32" not in config

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "configuration.toml"
        path.write_text(
            "[BASIC]\nbinary_file = 'target'\n"
            "[GDB]\ngdb_path = 'gdb'\ninstance = 'stm32'\n"
            "timeout = 0.5\nwatchpoint_count = 4\n"
            "[stm32]\ngdb_server_path = 'st-util'\ngdb_server_address = ':4242'\n"
            "dwt_function_reg = '0xe0001028'\ndwt_watchpoint_workaround = false\n"
            "[LOGS]\nlog_level = 'INVALID'\n"
            "[unused_mcu]\npattern = '100%\\w+'\n",
            encoding="utf-8",
        )
        config = load_config(path)
        assert config["unused_mcu"]["pattern"] == r"100%\w+"
        instance = GDBTracer.open_sut_instance(config)
        assert isinstance(instance, STM32Instance)
        assert instance.dwt_watchpoint_workaround is False
        assert instance.timeout == 0.5
        for invalid in ("false", "true", 0, 1):
            config["stm32"]["dwt_watchpoint_workaround"] = invalid
            try:
                STM32Instance(config, "")
            except TypeError:
                pass
            else:
                raise AssertionError(f"Invalid workaround flag accepted: {invalid!r}")
        config["stm32"].pop("dwt_watchpoint_workaround")
        assert STM32Instance(config, "").dwt_watchpoint_workaround is True
        config["GDB"].update(
            entrypoint="parse", exitpoint="", watchpoint_type="(char*)", input_buffer="buf"
        )
        for invalid in (False, True, 0, -1, "4", 4.0):
            config["GDB"]["watchpoint_count"] = invalid
            try:
                GDBTracer(config)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Invalid watchpoint count accepted: {invalid!r}")
        config["GDB"]["watchpoint_count"] = 4
        assert GDBTracer(config).watchpoint_count == 4
        # An MSP430 target needs its own settings, not STM32's DWT settings.
        config["GDB"]["instance"] = "msp430"
        config["msp430"] = {
            "gdb_server_path": "mspdebug gdb",
            "gdb_server_address": ":2000",
        }
        del config["stm32"]
        assert isinstance(GDBTracer.open_sut_instance(config), MSP430Instance)
        try:
            logging.getLogger().setLevel(config["LOGS"]["log_level"])
        except ValueError as exc:
            assert "Unknown level" in str(exc)
        else:
            raise AssertionError("Invalid logging level accepted")
        path.write_text("[BASIC]\nbinary_file = unquoted\n", encoding="utf-8")
        try:
            load_config(path)
        except tomllib.TOMLDecodeError:
            pass
        else:
            raise AssertionError("Invalid TOML accepted")
        path.unlink()
        try:
            load_config(path)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Missing config accepted")


if __name__ == "__main__":
    test_config()
    print("TOML configuration checks passed (27 examples and backend isolation)")
