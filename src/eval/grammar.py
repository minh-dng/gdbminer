"""Small grammar utilities used by the evaluation scripts."""

import random
import string
from typing import Dict, List, Set, Tuple

Grammar = Dict[str, List[List[str]]]
State = Tuple[str, Tuple[str, ...], int, int]

ASCII_MAP = {
    "[__ASCII_PRINTABLE__]": string.printable,
    "[__ASCII_ALPHANUM_PUNCT__]": string.ascii_letters + string.digits + string.punctuation.replace('"', '').replace('\\', ''),
    "[__ASCII_PUNCT__]": string.punctuation,
    "[__WHITESPACE__]": string.whitespace,
    "[__ASCII_ALPHANUM__]": string.ascii_letters + string.digits,
    "[__ASCII_LETTER__]": string.ascii_letters,
    "[__ASCII_LOWER__]": string.ascii_lowercase,
    "[__ASCII_UPPER__]": string.ascii_uppercase,
    "[__ASCII_HEXDIGIT__]": string.hexdigits,
    "[__DIGIT__]": string.digits,
}


def trim_grammar(grammar: Grammar, start_symbol: str) -> Grammar:
    """Return the part of ``grammar`` reachable from ``start_symbol``."""
    reachable: Set[str] = set()
    pending = [start_symbol]
    while pending:
        symbol = pending.pop()
        if symbol in reachable or symbol not in grammar:
            continue
        reachable.add(symbol)
        pending.extend(
            token
            for rule in grammar[symbol]
            for token in rule
            if token in grammar and token not in reachable
        )
    return {symbol: [list(rule) for rule in grammar[symbol]] for symbol in reachable}


class CoverageFuzzer:
    """Depth-limited grammar fuzzer that prefers uncovered productions."""

    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.cost = self._compute_costs()
        self.uncovered = {
            symbol: set(range(len(expansions)))
            for symbol, expansions in grammar.items()
        }

    def _compute_costs(self) -> Dict[str, List[float]]:
        symbol_cost = {symbol: float("inf") for symbol in self.grammar}
        for _ in self.grammar:
            changed = False
            for symbol, expansions in self.grammar.items():
                costs = [
                    max(
                        (symbol_cost[token] for token in rule if token in self.grammar),
                        default=0,
                    ) + 1
                    for rule in expansions
                ]
                minimum = min(costs, default=0)
                if minimum < symbol_cost[symbol]:
                    symbol_cost[symbol] = minimum
                    changed = True
            if not changed:
                break

        return {
            symbol: [
                max(
                    (symbol_cost[token] for token in rule if token in self.grammar),
                    default=0,
                ) + 1
                for rule in expansions
            ]
            for symbol, expansions in self.grammar.items()
        }

    def _choose_rule(self, symbol: str, depth: int, max_depth: int) -> List[str]:
        expansions = self.grammar[symbol]
        candidates = list(range(len(expansions)))
        if depth >= max_depth:
            minimum = min(self.cost[symbol])
            candidates = [
                index
                for index, cost in enumerate(self.cost[symbol])
                if cost == minimum
            ]

        uncovered = list(self.uncovered[symbol].intersection(candidates))
        index = random.choice(uncovered or candidates)
        self.uncovered[symbol].discard(index)
        return expansions[index]

    def fuzz(self, key: str, max_depth: int = 10) -> str:
        def token_node(token: str):
            if token in ASCII_MAP:
                return [random.choice(ASCII_MAP[token]), []]
            if token.endswith("+") and token[:-1] in ASCII_MAP:
                length = random.randrange(10) + 1
                chars = [random.choice(ASCII_MAP[token[:-1]]) for _ in range(length)]
                return ["".join(chars), []]
            if token in self.grammar:
                return [token, None]
            return [token, []]

        root = [key, None]
        queue = [(0, root)]
        while queue:
            (depth, node), *queue = queue
            if node[1] is not None:
                continue
            rule = self._choose_rule(node[0], depth, max_depth)
            node[1] = [token_node(token) for token in rule]
            queue.extend((depth + 1, child) for child in node[1])

        output = []
        queue = [root]
        while queue:
            node, *queue = queue
            symbol, children = node
            if symbol in self.grammar:
                queue = children + queue
            else:
                output.append(symbol)
        return "".join(output)


def accepts(grammar: Grammar, value: str, start_symbol: str) -> bool:
    """Return whether ``value`` belongs to ``grammar`` using Earley recognition."""
    if start_symbol not in grammar:
        return False

    charts: List[List[State]] = [[] for _ in range(len(value) + 1)]
    seen: List[Set[State]] = [set() for _ in charts]

    def add(position: int, state: State) -> None:
        if state not in seen[position]:
            seen[position].add(state)
            charts[position].append(state)

    goal: State = ("<>", (start_symbol,), 0, 0)
    add(0, goal)

    for position, chart in enumerate(charts):
        cursor = 0
        while cursor < len(chart):
            lhs, rule, dot, origin = chart[cursor]
            cursor += 1

            if dot == len(rule):
                for previous in list(charts[origin]):
                    prev_lhs, prev_rule, prev_dot, prev_origin = previous
                    if prev_dot < len(prev_rule) and prev_rule[prev_dot] == lhs:
                        add(position, (prev_lhs, prev_rule, prev_dot + 1, prev_origin))
                continue

            symbol = rule[dot]
            if symbol in grammar:
                for expansion in grammar[symbol]:
                    add(position, (symbol, tuple(expansion), 0, position))
                for completed in list(chart):
                    comp_lhs, comp_rule, comp_dot, comp_origin = completed
                    if comp_lhs == symbol and comp_dot == len(comp_rule) and comp_origin == position:
                        add(position, (lhs, rule, dot + 1, origin))
            elif value.startswith(symbol, position):
                add(position + len(symbol), (lhs, rule, dot + 1, origin))

    return ("<>", (start_symbol,), 1, 0) in seen[len(value)]


class MutationFuzzer:
    """Seed-first mutation fuzzer compatible with the evaluation runner."""

    def __init__(self, seed: List[str], min_mutations: int = 2, max_mutations: int = 10):
        if not seed:
            raise ValueError("at least one seed is required")
        self.seed = seed
        self.min_mutations = min_mutations
        self.max_mutations = max_mutations
        self.seed_index = 0

    @staticmethod
    def _mutate(value: str) -> str:
        mutation = random.randrange(3)
        if mutation == 0 and value:
            position = random.randrange(len(value))
            return value[:position] + value[position + 1:]
        if mutation == 1 or not value:
            position = random.randrange(len(value) + 1)
            return value[:position] + chr(random.randrange(32, 127)) + value[position:]
        position = random.randrange(len(value))
        replacement = chr(ord(value[position]) ^ (1 << random.randrange(7)))
        return value[:position] + replacement + value[position + 1:]

    def fuzz(self) -> str:
        if self.seed_index < len(self.seed):
            value = self.seed[self.seed_index]
            self.seed_index += 1
            return value

        value = random.choice(self.seed)
        for _ in range(random.randint(self.min_mutations, self.max_mutations)):
            value = self._mutate(value)
        return value
