"""Each watchpoint window is traced separately; windows merge per instruction."""

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
