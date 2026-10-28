"""Inline debug frames may change depth by more than one instruction to instruction."""

import unittest

from miner.graph_utils import all_natural_loops, build_control_flow_graphs_from_traces


def test_return_pops_observed_scopes_by_depth_not_number_of_debug_frames():
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
    assert functions == {
        "root": "parser",
        "child": "inlined_child",
        "grandchild": "inlined_grandchild",
    }
    assert scopes == {
        "root": {"root", "root-return"},
        "child": {"child", "child-return"},
        "grandchild": {"grandchild"},
    }


class GraphStackTest(unittest.TestCase):
    def test_single_instruction_callee_remains_in_graph_without_changing_edges(self):
        trace = [
            {"address": address, "stack": stack, "function_name": name}
            for address, stack, name in [
                ("caller-entry", ["outer-return"], "parser"),
                ("call-site", ["outer-return"], "parser"),
                ("callee-entry", ["call-return", "outer-return"], "helper"),
                ("caller-resumed", ["outer-return"], "parser"),
            ]
        ]
        cfg, functions, scopes = build_control_flow_graphs_from_traces([trace])

        self.assertEqual(
            set(cfg.edges),
            {
                ("0", "outer-return"),
                ("caller-entry", "call-site"),
                ("call-site", "call-return"),
            },
        )
        self.assertTrue(set().union(*scopes.values()).issubset(cfg.nodes))
        self.assertTrue(set(functions).issubset(cfg.nodes))
        self.assertEqual(cfg.degree("callee-entry"), 0)
        self.assertEqual(all_natural_loops(cfg, "callee-entry"), {})
