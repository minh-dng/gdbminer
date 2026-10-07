"""Each watchpoint window is traced separately; windows merge per instruction."""

from itertools import pairwise

import pytest

from tracer import GDBTracer


def entry(address="0x10", function="parser", hits=()):
    return GDBTracer.TraceEntry(address, function, [], ["0x20", "0x0"], list(hits))


@pytest.mark.parametrize("other", [[], [entry(), entry()], [entry(function="different")]])
def test_merge_rejects_partial_and_divergent_windows(other):
    with pytest.raises(ValueError):
        GDBTracer.merge_traces([entry()], other)


def test_merge_does_not_mutate_previous_window():
    first = [entry(hits=[0])]
    merged = GDBTracer.merge_traces(first, [entry(hits=[1])])
    assert merged[0].watchpoint_hits == [0, 1]
    assert first[0].watchpoint_hits == [0]


def tracer(count, distance=None, instance="valgrind"):
    gdb = {
        "entrypoint": "parser",
        "input_buffer": "buf",
        "watchpoint_type": "(char*)",
        "watchpoint_count": count,
        "instance": instance,
    }
    if distance is not None:
        gdb["instance"] = "esp32s3"
        gdb["esp32s3"] = {"watchpoint_min_distance": distance}
    elif instance == "esp32s3":
        gdb["esp32s3"] = {}
    return GDBTracer({"GDB": gdb})


@pytest.mark.parametrize("instance", ["valgrind", "stm32", "msp430", "esp32c3", "esp32s3"])
def test_default_windows_slide_contiguously(instance):
    assert tracer(2, instance=instance).watch_windows(5) == [[0, 1], [2, 3], [4]]


def test_s3_distance_does_not_affect_other_targets():
    gdb_tracer = tracer(2, 4)
    gdb_tracer.config["GDB"]["instance"] = "esp32c3"
    assert GDBTracer(gdb_tracer.config).watch_windows(5) == [[0, 1], [2, 3], [4]]


@pytest.mark.parametrize("count, distance", [(1, 4), (2, 4), (3, 4), (2, 2), (6, 4)])
def test_spread_windows_watch_every_byte_once_and_far_enough_apart(count, distance):
    gdb_tracer = tracer(count, distance)
    for length in range(1, 41):
        windows = gdb_tracer.watch_windows(length)
        assert sorted(offset for window in windows for offset in window) == list(range(length))
        for window in windows:
            assert 1 <= len(window) <= count
            assert all(b - a >= distance for a, b in pairwise(window))
        if length > count * (distance - 1):
            # As many runs as the paper's contiguous window.
            assert len(windows) == len(tracer(count).watch_windows(length))


def test_spread_windows_for_two_s3_data_breakpoints():
    assert tracer(2, 4).watch_windows(10) == [[0, 5], [1, 6], [2, 7], [3, 8], [4, 9]]
    assert tracer(2, 4).watch_windows(3) == [[0], [1], [2]]
