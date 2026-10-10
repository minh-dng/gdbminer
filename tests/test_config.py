"""Hardware-free regression check: PYTHONPATH=src python tests/test_config.py."""

from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tracer import GDBTracer, trace
from tracer.instance import ESP32C3Instance, HardwareInstance, MSP430Instance, STM32Instance
from util import add_override_arguments, apply_overrides, load_config
from util.config import _validate_config

ROOT = Path(__file__).resolve().parents[1]
JSON_CONFIG = ROOT / "example_programs/json/configuration/configuration.toml"
STM32_CONFIG = ROOT / "example_firmware/stm32_libyxml/configuration/configuration.toml"
C3_CONFIG = ROOT / "example_firmware/esp32-c3_json/configuration/configuration.2-cables.toml"


def test_config():
    for path in ROOT.glob("example_*/**/configuration*.toml"):
        load_config(path)

    desktop = load_config(JSON_CONFIG)
    stm32 = load_config(STM32_CONFIG)
    c3 = load_config(C3_CONFIG)

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
        (c3, "GDB", "watchpoint_count", (9,)),
        (c3, "GDB", "watchpoint_type", ("(uint16_t*)",)),
        (c3, "esp32c3", "hardware_trigger_slot", (True, "2", 2.0, -1, 3)),
        (c3, "esp32c3", "rom_elf", (123, False)),
        (c3, "esp32c3", "reset_on_connect", ("false", 0, 1)),
        (c3, "esp32c3", "reset_on_conect", (False,)),
        (c3, "esp32c3", "breakpoint_always_inserted", ("true", 0, 1)),
        (c3, "esp32c3", "startup_retry_interval", (True, "0.2", 0, -1, float("inf"), float("nan"))),
        (c3, "Connection", "dtr", ("false", 0, 1)),
        (c3, "Connection", "rts", ("true", 0, 1)),
        (c3, "Connection", "reset_pulse", ("false", False, 0, 1)),
        (c3, "Connection", "input_channel", ("serial",)),
        *[
            (c3, "Connection", key, (True, "1", 0, -1, float("inf"), float("nan")))
            for key in ("quiet_sec", "grace_sec", "reset_pulse_sec")
        ],
        (c3, "Connection", "boot_delay", (3,)),
        (c3, "Connection", "max_input_size", (2048,)),
    ):
        for value in invalids:
            config = deepcopy(base)
            target = config["GDB"][table] if table in ("stm32", "esp32c3") else config[table]
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
            _validate_config(config)
        except ValueError as exc:
            assert "[GDB.stm32]" in str(exc)
        else:
            raise AssertionError(f"Accepted misplaced {key}")

    config = deepcopy(stm32)
    config["stm32"] = config["GDB"].pop("stm32")
    try:
        _validate_config(config)
    except ValueError as exc:
        assert "[GDB.stm32]" in str(exc)
    else:
        raise AssertionError("Accepted obsolete top-level STM32 table")

    desktop["GDB"].pop("exitpoint")
    desktop["GDB"]["timeout"] = 0.5
    _validate_config(desktop)
    assert GDBTracer(desktop).exitpoint == ""
    assert GDBTracer.open_sut_instance(desktop).timeout == 0.5

    assert STM32Instance(stm32, "").dwt_watchpoint_workaround is True
    stm32["GDB"]["stm32"] = {"dwt_watchpoint_workaround": False}
    _validate_config(stm32)
    assert STM32Instance(stm32, "").dwt_watchpoint_workaround is False

    instance = GDBTracer.open_sut_instance(c3)
    assert isinstance(instance, ESP32C3Instance)
    assert ESP32C3Instance.__bases__ == (HardwareInstance,)
    assert STM32Instance.__bases__ == (HardwareInstance,)
    assert not hasattr(instance, "dwt_watchpoint_workaround")
    assert not instance.reset_on_connect
    assert (instance.trigger_slot, instance.watchpoint_count) == (2, 6)
    assert instance.gdb_server_path_with_args[-2:] == ["-c", "adapter speed 40000"]

    full_window = deepcopy(c3)
    full_window["GDB"]["watchpoint_count"] = 8
    full_window["GDB"]["esp32c3"]["hardware_trigger_slot"] = 0
    _validate_config(full_window)
    full_window["GDB"]["exitpoint"] = "parser_exit"
    with (
        patch("sys.argv", ["trace", "--config", str(C3_CONFIG)]),
        patch("util.config.tomllib.load", return_value=full_window),
        patch("tracer.trace.create_output_dir") as create_output,
        patch("tracer.trace.generate_trace") as generate_trace,
    ):
        try:
            trace.main()
        except ValueError as exc:
            assert "exitpoint" in str(exc)
        else:
            raise AssertionError("Accepted eight read triggers plus an exit breakpoint")
        create_output.assert_not_called()
        generate_trace.assert_not_called()

    no_reset = deepcopy(c3)
    no_reset["Connection"].update(rts=False, reset_pulse=False)
    _validate_config(no_reset)

    for key in (
        "rom_elf",
        "hardware_trigger_slot",
        "reset_on_connect",
        "breakpoint_always_inserted",
    ):
        config = deepcopy(c3)
        config["GDB"][key] = config["GDB"]["esp32c3"].pop(key, False)
        try:
            _validate_config(config)
        except ValueError as exc:
            assert "[GDB.esp32c3]" in str(exc)
        else:
            raise AssertionError(f"Accepted misplaced {key}")

    for table in ("GDB", "esp32c3"):
        config = deepcopy(c3)
        target = config["GDB"] if table == "GDB" else config["GDB"][table]
        target["dwt_watchpoint_workaround"] = False
        try:
            _validate_config(config)
        except ValueError as exc:
            assert "DWT" in str(exc)
        else:
            raise AssertionError("Accepted ARM DWT settings on ESP32-C3")

    # MSP430 uses the shared server settings and requires no DWT table.
    stm32["GDB"].pop("stm32")
    stm32["GDB"].update(
        instance="msp430",
        gdb_path="'/opt/tool chain/gdb' --quiet",
        gdb_server_path="'/opt/tool chain/mspdebug' gdb",
    )
    _validate_config(stm32)
    instance = GDBTracer.open_sut_instance(stm32)
    assert isinstance(instance, MSP430Instance)
    assert instance.gdb_with_args == ["/opt/tool chain/gdb", "--quiet"]
    assert instance.gdb_server_path_with_args == ["/opt/tool chain/mspdebug", "gdb"]


def test_esp32_usb_serial_jtag_settings():
    uart = load_config(C3_CONFIG)
    usb = deepcopy(uart)
    usb["Connection"].pop("baud_rate")
    usb["Connection"].update(input_channel="esp32-usb-serial-jtag", write_gap_sec=0.001)
    _validate_config(usb)

    invalid = [(usb, "baud_rate", 9600), (uart, "write_gap_sec", 0.002)]
    invalid += [
        (usb, "write_gap_sec", value)
        for value in (True, "0.002", 0, -1, float("inf"), float("nan"))
    ]
    for base, key, value in invalid:
        config = deepcopy(base)
        config["Connection"][key] = value
        try:
            _validate_config(config)
        except (TypeError, ValueError) as exc:
            assert key in str(exc), str(exc)
        else:
            raise AssertionError(f"Accepted Connection.{key} = {value!r}")


def test_gdb_port_validation():
    config = load_config(C3_CONFIG)
    del config["GDB"]["gdb_port"]
    # `--gdb-port` can supply the port, so the file may leave it out.
    _validate_config(config)

    for key, value in (
        ("gdb_server_address", ":3333"),
        *[("gdb_port", value) for value in (0, -1, 65536, "3333", True)],
    ):
        config = load_config(C3_CONFIG)
        config["GDB"][key] = value
        try:
            _validate_config(config)
        except (TypeError, ValueError) as exc:
            assert key in str(exc), str(exc)
        else:
            raise AssertionError(f"Accepted GDB.{key} = {value!r}")


def _override(config, *flags: str) -> None:
    parser = ArgumentParser()
    add_override_arguments(parser)
    apply_overrides(config, parser.parse_args(flags))


def _templated(gdb_port: int | None = 3333):
    """C3 configuration whose server command holds both placeholders."""
    config = load_config(C3_CONFIG)
    config["GDB"]["gdb_server_path"] = (
        'openocd -c "gdb port {gdb_port}" -c "adapter serial {adapter_serial}"'
    )
    if gdb_port is None:
        del config["GDB"]["gdb_port"]
    return config


def test_apply_overrides():
    config = _templated()
    with patch("util.config.logging") as log:
        _override(config, "--port", "/dev/ttyB", "--adapter-serial", "AA:BB", "--gdb-port", "3334")
    assert config["Connection"]["port"] == "/dev/ttyB"
    assert config["GDB"]["gdb_port"] == 3334
    assert config["GDB"]["gdb_server_path"] == (
        'openocd -c "gdb port 3334" -c "adapter serial AA:BB"'
    )
    # Both flags replace a different configured value, which is worth a warning each.
    assert log.warning.call_count == 2

    # Without --gdb-port the placeholder takes GDB.gdb_port.
    config = _templated()
    port = config["Connection"]["port"]
    _override(config, "--adapter-serial", "AA:BB")
    assert config["Connection"]["port"] == port
    assert 'gdb port 3333"' in config["GDB"]["gdb_server_path"]

    # --gdb-port alone suffices when the configuration leaves gdb_port out.
    config = _templated(gdb_port=None)
    _override(config, "--adapter-serial", "AA:BB", "--gdb-port", "5000")
    assert config["GDB"]["gdb_port"] == 5000

    for port in (None, ""):
        config = _templated()
        if port is None:
            del config["Connection"]["port"]
        else:
            config["Connection"]["port"] = port
        _validate_config(config)
        try:
            _override(config, "--adapter-serial", "AA:BB")
        except ValueError as exc:
            assert "Connection.port" in str(exc), str(exc)
        else:
            raise AssertionError("Accepted a missing serial port")
        _override(config, "--port", "/dev/ttyB", "--adapter-serial", "AA:BB")
        assert config["Connection"]["port"] == "/dev/ttyB"

    # A missing or invalid value, and a flag without its placeholder, must not start a server.
    plain = load_config(STM32_CONFIG)
    plain["GDB"]["gdb_server_path"] = "st-util"
    for base, flags in (
        (_templated(), ()),
        (_templated(gdb_port=None), ("--adapter-serial", "AA:BB")),
        *[
            (_templated(), ("--adapter-serial", "AA:BB", "--gdb-port", p))
            for p in ("0", "-1", "65536")
        ],
        (deepcopy(plain), ("--adapter-serial", "AA:BB")),
        (deepcopy(plain), ("--gdb-port", "4243")),
        (load_config(JSON_CONFIG), ("--port", "/dev/ttyB")),
    ):
        try:
            _override(base, *flags)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted overrides {flags!r}")


def test_example_configs_template_gdb_port():
    # One port setting reaches both the server and GDB only through the placeholder.
    for path in ROOT.glob("example_*/**/configuration*.toml"):
        gdb = load_config(path)["GDB"]
        if "gdb_server_path" in gdb:
            assert "{gdb_port}" in gdb["gdb_server_path"], path


def test_invalid_overrides_do_not_create_trial():
    with TemporaryDirectory() as directory:
        config = load_config(C3_CONFIG)
        output = Path(directory) / "runs"
        config["BASIC"]["output_directory"] = str(output)
        with (
            patch("sys.argv", ["trace", "--config", str(C3_CONFIG)]),
            patch("util.config.tomllib.load", return_value=config),
            patch("tracer.trace.generate_trace") as generate_trace,
        ):
            try:
                trace.main()
            except ValueError as exc:
                assert "{adapter_serial}" in str(exc), str(exc)
            else:
                raise AssertionError("Accepted a missing adapter serial")
            generate_trace.assert_not_called()
        assert not output.exists(), "Invalid overrides left a trial directory behind"


def test_openocd_console_ports():
    for path in ROOT.glob("example_firmware/esp32-c3_*/configuration/configuration*.toml"):
        for flags, telnet, tcl in (
            ((), "disabled", "disabled"),
            (("--telnet-port", "4444"), "4444", "disabled"),
            (("--tcl-port", "6666"), "disabled", "6666"),
            (("--telnet-port", "4445", "--tcl-port", "6667"), "4445", "6667"),
        ):
            config = load_config(path)
            _override(config, "--adapter-serial", "AA:BB", *flags)
            command = ESP32C3Instance(config, "").gdb_server_path_with_args
            assert f"telnet port {telnet}" in command, path
            assert f"tcl port {tcl}" in command, path

    for flag in ("--telnet-port", "--tcl-port"):
        for config in (_templated(), load_config(STM32_CONFIG), load_config(JSON_CONFIG)):
            try:
                _override(config, flag, "4444")
            except ValueError as exc:
                assert flag in str(exc), str(exc)
            else:
                raise AssertionError(f"Accepted {flag} without its server placeholder")

        for port in ("0", "-5", "65536", "99999", "3333"):
            config = load_config(C3_CONFIG)
            try:
                _override(config, "--adapter-serial", "AA:BB", flag, port)
            except ValueError as exc:
                assert flag in str(exc) or "distinct" in str(exc), str(exc)
            else:
                raise AssertionError(f"Accepted {flag} {port}")

    config = load_config(C3_CONFIG)
    try:
        _override(
            config, "--adapter-serial", "AA:BB", "--telnet-port", "4444", "--tcl-port", "4444"
        )
    except ValueError as exc:
        assert "distinct" in str(exc), str(exc)
    else:
        raise AssertionError("Accepted colliding console ports")


if __name__ == "__main__":
    test_config()
    test_gdb_port_validation()
    test_apply_overrides()
    test_example_configs_template_gdb_port()
    test_invalid_overrides_do_not_create_trial()
    test_openocd_console_ports()
    test_esp32_usb_serial_jtag_settings()
    print("Configuration regression checks passed")
