import json
import random
import unittest
from pathlib import Path

from eval.grammar import CoverageFuzzer, accepts, trim_grammar


class EvaluationGrammarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        grammar_file = Path(__file__).parents[1] / "example_programs/calc/calc.grammar"
        cls.grammar_file = json.loads(grammar_file.read_text())

    def test_earley_recognizer_handles_left_recursion(self):
        grammar = self.grammar_file["[grammar]"]
        start = self.grammar_file["[start]"]

        for value in ("1", "1+2*3", "(1+2)/3"):
            self.assertTrue(accepts(grammar, value, start))
        for value in ("", "1+", "(1+2"):
            self.assertFalse(accepts(grammar, value, start))

    def test_fuzzer_only_generates_members(self):
        random.seed(1)
        grammar = trim_grammar(
            self.grammar_file["[grammar]"], self.grammar_file["[start]"]
        )
        fuzzer = CoverageFuzzer(grammar)

        for _ in range(50):
            value = fuzzer.fuzz(self.grammar_file["[start]"])
            self.assertTrue(accepts(grammar, value, self.grammar_file["[start]"]))


if __name__ == "__main__":
    unittest.main()
