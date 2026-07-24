# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

import unittest

from gdbminer_nautilus.grammar_adapter import convert_gdbminer_to_nautilus


class NautilusAdapterTests(unittest.TestCase):
    def test_converts_fuzzingbook_grammar_to_nautilus_rules(self) -> None:
        converted = convert_gdbminer_to_nautilus(
            {
                "[start]": "<START>",
                "[grammar]": {
                    "<START>": [["<percent.decode>", "{", "}", "\\"]],
                    "<percent.decode>": [[], ["a"]],
                },
            }
        )

        self.assertEqual(converted.start_nonterminal, "G_START")
        self.assertEqual(
            converted.to_json()[0],
            ["G_START", "".join(["{G_percent_decode}", r"\{", r"\}", "\\"])],
        )
        self.assertEqual(converted.to_json()[1], ["G_percent_decode", ""])
        self.assertEqual(converted.to_json()[2], ["G_percent_decode", "a"])

    def test_rejects_undefined_nonterminal_references(self) -> None:
        with self.assertRaisesRegex(ValueError, "undefined nonterminals"):
            convert_gdbminer_to_nautilus(
                {
                    "[start]": "<start>",
                    "[grammar]": {
                        "<start>": [["<missing>"]],
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
