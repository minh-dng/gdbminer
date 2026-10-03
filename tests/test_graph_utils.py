"""Inline debug frames may change depth by more than one instruction to instruction."""

import unittest

from miner.graph_utils import build_control_flow_graphs_from_traces


class GraphStackTest(unittest.TestCase):
    def test_return_pops_observed_scopes_by_depth_not_number_of_debug_frames(self):
        def entry(address, depth, name):
            return {"address": address, "stack": ["return"] * depth, "function_name": name}

        trace = [
            entry("root", 1, "parser"),
            entry("child", 4, "inlined_child"),
            entry("grandchild", 6, "inlined_grandchild"),
            entry("child-return", 4, "inlined_child"),
            entry("root-return", 1, "parser"),
        ]
        _, functions, scopes = build_control_flow_graphs_from_traces([trace, trace])
        self.assertEqual(
            functions,
            {"root": "parser", "child": "inlined_child", "grandchild": "inlined_grandchild"},
        )
        self.assertEqual(
            scopes,
            {
                "root": {"root", "root-return"},
                "child": {"child", "child-return"},
                "grandchild": {"grandchild"},
            },
        )


if __name__ == "__main__":
    unittest.main()
