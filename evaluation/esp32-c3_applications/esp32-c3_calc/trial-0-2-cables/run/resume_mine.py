"""Resume mine.py after method generalization: loop, token and grammar steps only.

Reads method_trees.json (the saved result of the finished methods phase) and then runs the same
code as the tail of src/miner/mine.py main(). Kept outside src/ on purpose; no repo file is changed.
The methods phase used 154,455 requests (mine.out, 2026-10-22 22:10:02); that count is restored so
[no_tested_inputs] in parsing_g.json stays the sum over all three phases.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.setrecursionlimit(99000)

import cmimid.grammartools as G
from cmimid import parsinggrammar
from miner.loop_generalizer import LoopGeneralizer
from miner.method_generalizer import MethodGeneralizer
from miner.mine import (
    check_empty_rules,
    collapse_rules,
    convert_spaces_in_keys,
    convert_to_grammar,
    eliminate_non_terminating_vars,
)
from miner.token_generalizer import TokenGeneralizer
from util import (
    add_override_arguments,
    apply_overrides,
    find_output_directory,
    load_config,
    setup_logging,
)

METHOD_REQUESTS = 154455


def main() -> None:
    start_time = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    add_override_arguments(parser)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_directory = find_output_directory(Path(config["BASIC"]["output_directory"]))
    setup_logging(output_directory, config["LOGS"]["log_level"])
    apply_overrides(config, args)
    logging.info("RESUME: loading method_trees.json; methods phase used %d requests", METHOD_REQUESTS)

    with (output_directory / "method_trees.json").open(encoding="utf-8") as f:
        trees = json.load(f)

    method_generalizer = MethodGeneralizer(config)
    method_generalizer.number_of_tested_inputs = METHOD_REQUESTS

    loop_generalizer = LoopGeneralizer(config)
    trees = loop_generalizer.generalize_loop_trees(trees)
    with (output_directory / "loop_trees.json").open("w", encoding="utf-8") as f:
        json.dump(trees, f)

    ret, g = convert_to_grammar(trees)
    cmds = {src for starts, src, arg in ret}
    starts = {starts for starts, src, arg in ret}
    assert len(cmds) == 1
    cmd = next(iter(cmds))
    assert len(starts) == 1
    start_symbol = next(iter(starts))
    g = G.grammar_gc(g, start_symbol)
    g = check_empty_rules(g)
    g = eliminate_non_terminating_vars(g)
    g = G.grammar_gc(g, start_symbol)
    g = collapse_rules(g)
    g = G.grammar_gc(g, start_symbol)
    g = convert_spaces_in_keys(g)
    g = G.grammar_gc(g, start_symbol)

    grammar_map = {"[start]": start_symbol, "[grammar]": g, "[command]": cmd}
    with (output_directory / "mined_g.json").open("w", encoding="utf-8") as f:
        json.dump(grammar_map, f, indent=4)

    token_generalizer = TokenGeneralizer(config)
    g = token_generalizer.generalize_tokens_in_grammar(g, start_symbol)
    compact_g = G.compact_grammar(g, start_symbol)
    final_grammar = parsinggrammar.enhance_grammar(compact_g)

    number_of_tested_inputs = (
        method_generalizer.number_of_tested_inputs
        + loop_generalizer.number_of_tested_inputs
        + token_generalizer.number_of_tested_inputs
    )
    with (output_directory / "parsing_g.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "[start]": start_symbol,
                "[grammar]": final_grammar,
                "[command]": cmd,
                "[no_tested_inputs]": number_of_tested_inputs,
            },
            f,
        )
    logging.info(f"Resumed mining time (loops, tokens, grammar only): {time.time() - start_time} seconds")


if __name__ == "__main__":
    main()
