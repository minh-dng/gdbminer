"""Removing empty rules keeps the nonempty strings of the marked grammar (issue #58)."""

import itertools
import random
import string

import pytest

from eval.grammar import accepts
from miner.mine import check_empty_rules

# The deletion checks mark a symbol as optional with "-": at the end of a method name, or as the
# can_empty field of a loop or condition. An unmarked symbol stays nonempty: at least one
# deletion in its observed pattern group was rejected.
GRAMMAR = {
    "<START>": [["<value.0>", "<space-.0>"]],
    "<value.0>": [["<sign-.0>", "<digits.0>", "<exponent-.0>"], ["n"]],
    "<digits.0>": [["<digit:while_1,0 -#[]>"]],
    "<digit:while_1,0 -#[]>": [["1"], ["2"]],
    "<sign-.0>": [["+"]],
    "<exponent-.0>": [["e"]],
    "<space-.0>": [[" "]],
}
OPTIONAL = {"<digit:while_1,0 -#[]>", "<sign-.0>", "<exponent-.0>", "<space-.0>"}


def language(grammar, symbol, optional=frozenset()):
    """All strings derived from `symbol` in a grammar without recursion.

    Symbols in `optional` also derive the empty string; the others never do.
    """
    if symbol not in grammar:
        return {symbol}
    strings = {
        "".join(parts)
        for rule in grammar[symbol]
        for parts in itertools.product(*(language(grammar, s, optional) for s in rule))
    }
    return strings | {""} if symbol in optional else strings - {""}


def copy(grammar):
    return {key: [list(rule) for rule in rules] for key, rules in grammar.items()}


def test_keeps_every_optional_combination_in_input_order():
    grammar = {"<START>": [["<a-.0>", "x", "<b-.0>"]], "<a-.0>": [["a"]], "<b-.0>": [["b"]]}

    result = check_empty_rules(grammar)

    # The input rule stays first: later stages name symbols in rule order.
    assert result["<START>"] == [
        ["<a-.0>", "x", "<b-.0>"],
        ["<a-.0>", "x"],
        ["x", "<b-.0>"],
        ["x"],
    ]


def test_keeps_each_partial_omission_of_optional_symbols():
    grammar = {"<START>": [["<a-.0>", "<b-.0>"]], "<a-.0>": [["a"]], "<b-.0>": [["b"]]}

    result = check_empty_rules(grammar)

    assert sorted(result["<START>"]) == [["<a-.0>"], ["<a-.0>", "<b-.0>"], ["<b-.0>"]]


def test_unmarked_symbol_of_optional_symbols_is_not_omitted():
    grammar = {"<START>": [["<a.0>", "c"]], "<a.0>": [["<b-.0>"]], "<b-.0>": [["b"]]}

    result = check_empty_rules(grammar)

    assert result["<START>"] == [["<a.0>", "c"]]


def test_keeps_every_nonempty_string_of_the_marked_grammar():
    expected = language(GRAMMAR, "<START>", OPTIONAL)
    # Spelled out as an independent check of `language`.
    values = {"n", "1", "2", "+1", "+2", "1e", "2e", "+1e", "+2e"}
    assert expected == values | {value + " " for value in values}

    result = check_empty_rules(copy(GRAMMAR))

    assert language(result, "<START>") == expected


@pytest.mark.parametrize("mandatory_first", [False, True])
def test_rule_with_many_optional_symbols_keeps_its_language_without_blow_up(mandatory_first):
    letters = string.ascii_letters + string.digits + "+/"
    symbols = [f"<x{i}-.0>" for i in range(len(letters))]
    rule = ["<end.0>", *symbols] if mandatory_first else [*symbols, "<end.0>"]
    grammar = {
        "<START>": [rule],
        "<end.0>": [["."]],
        **{s: [[c]] for s, c in zip(symbols, letters, strict=True)},
    }

    def word(kept):
        return "." + kept if mandatory_first else kept + "."

    result = check_empty_rules(grammar)

    # Every subset of the 64 optional symbols would be 2**64 rules for START.
    assert sum(map(len, result.values())) < 10_000
    random.seed(0)
    for _ in range(50):
        kept = "".join(c for c in letters if random.random() < 0.5)
        assert accepts(result, word(kept), "<START>")
    for kept in (letters, letters[0], letters[-1], ""):
        assert accepts(result, word(kept), "<START>")
    for rejected in ("", letters, word(letters[::-1]), word(letters[0] * 2)):
        assert not accepts(result, rejected, "<START>")
