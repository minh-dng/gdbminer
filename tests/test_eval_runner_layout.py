"""Destination naming of the evaluation runner: uv run pytest tests/test_eval_runner_layout.py."""

from pathlib import Path

import pytest

from scripts.eval_runner import layout

C3_JSON = Path("example_firmware/esp32-c3_json/configuration/configuration.2-cables.toml")
S3_XML = Path("example_firmware/esp32-s3_xml/configuration/configuration.1-watchpoint.toml")


def test_setup_suffix():
    assert layout.setup_suffix(C3_JSON) == "2-cables"
    assert layout.setup_suffix(S3_XML) == "1-watchpoint"
    for name in ("configuration.toml", "configuration.1-cable.txt"):
        with pytest.raises(ValueError):
            layout.setup_suffix(Path(name))


def test_target_name():
    assert layout.target_name("esp32-c3_json") == "esp32-c3_arduinojson"
    assert layout.target_name("esp32-s3_xml") == "esp32-s3_libyxml"
    assert layout.target_name("esp32-c3_cgidecode") == "esp32-c3_cgidecode"


def test_next_trial_counts_per_setup(tmp_path: Path):
    assert layout.next_trial(tmp_path / "missing", "1-cable") == 0
    for name in ("trial-0-1-cable", "trial-3-1-cable", "trial-7-2-cables", "trial-9-x1-cable"):
        (tmp_path / name).mkdir()
    assert layout.next_trial(tmp_path, "1-cable") == 4
    assert layout.next_trial(tmp_path, "2-cables") == 8
    assert layout.next_trial(tmp_path, "1-watchpoint") == 0


def test_destination_and_preview(tmp_path: Path):
    (tmp_path / "esp32-c3_arduinojson/trial-1-2-cables").mkdir(parents=True)
    expected = tmp_path / "esp32-c3_arduinojson/trial-2-2-cables"
    assert layout.destination(tmp_path, C3_JSON) == expected
    assert layout.preview([C3_JSON, S3_XML], tmp_path).splitlines() == [
        f"{C3_JSON} -> {expected}/",
        f"{S3_XML} -> {tmp_path}/esp32-s3_libyxml/trial-0-1-watchpoint/",
        "(run/ in each destination holds the logs and provenance)",
    ]


def test_scratch_dir():
    assert layout.scratch_dir(C3_JSON) == Path("output/eval-runner/esp32-c3_json-2-cables")
