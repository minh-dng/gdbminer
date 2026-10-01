import json
import random
from pathlib import Path

import pytest

from eval.grammar import CoverageFuzzer, accepts, trim_grammar


@pytest.fixture(scope="module")
def grammar_file():
    path = Path(__file__).parents[1] / "example_programs/calc/calc.grammar"
    return json.loads(path.read_text(encoding="utf-8"))


def test_earley_recognizer_handles_left_recursion(grammar_file):
    grammar = grammar_file["[grammar]"]
    start = grammar_file["[start]"]

    for value in ("1", "1+2*3", "(1+2)/3"):
        assert accepts(grammar, value, start)
    for value in ("", "1+", "(1+2"):
        assert not accepts(grammar, value, start)


def test_fuzzer_only_generates_members(grammar_file):
    random.seed(1)
    grammar = trim_grammar(grammar_file["[grammar]"], grammar_file["[start]"])
    fuzzer = CoverageFuzzer(grammar)

    for _ in range(50):
        value = fuzzer.fuzz(grammar_file["[start]"])
        assert accepts(grammar, value, grammar_file["[start]"])
