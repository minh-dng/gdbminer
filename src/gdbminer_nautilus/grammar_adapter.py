# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

"""Convert GDBMiner grammar JSON into NAUTILUS grammar JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

GDBMINER_GRAMMAR_KEY = "[grammar]"
GDBMINER_START_KEY = "[start]"
NAUTILUS_ROOT_SYMBOL = "START"

_GDBMINER_NONTERMINAL_RE = re.compile(r"^<(.+)>$")
_NAUTILUS_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9_-]*$")
_UNSAFE_NAUTILUS_NAME_CHARS_RE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class NautilusRule:
    """A single NAUTILUS JSON rule."""

    nonterminal: str
    rhs: str

    def to_json(self) -> list[str]:
        return [self.nonterminal, self.rhs]


@dataclass(frozen=True)
class NautilusGrammar:
    """Converted grammar plus conversion metadata."""

    source_start: str
    start_nonterminal: str
    rules: tuple[NautilusRule, ...]
    symbol_map: Mapping[str, str]

    def to_json(self) -> list[list[str]]:
        return [rule.to_json() for rule in self.rules]

    def summary(self) -> dict[str, Any]:
        return {
            "source_start": self.source_start,
            "nautilus_root": NAUTILUS_ROOT_SYMBOL,
            "start_nonterminal": self.start_nonterminal,
            "nonterminals": len(self.symbol_map),
            "rules": len(self.rules),
        }


def load_gdbminer_grammar(path: Union[str, Path]) -> Mapping[str, Any]:
    """Load and minimally validate a GDBMiner grammar JSON document."""

    grammar_path = Path(path)
    with grammar_path.open(encoding="utf-8") as grammar_file:
        document = json.load(grammar_file)

    if not isinstance(document, Mapping):
        raise ValueError(f"{grammar_path} must contain a JSON object")
    if GDBMINER_START_KEY not in document:
        raise ValueError(f"{grammar_path} is missing {GDBMINER_START_KEY!r}")
    if GDBMINER_GRAMMAR_KEY not in document:
        raise ValueError(f"{grammar_path} is missing {GDBMINER_GRAMMAR_KEY!r}")

    return document


def convert_gdbminer_to_nautilus(document: Mapping[str, Any]) -> NautilusGrammar:
    """Convert a GDBMiner grammar JSON object into NAUTILUS JSON rules."""

    source_start = _expect_string(document[GDBMINER_START_KEY], GDBMINER_START_KEY)
    grammar = _expect_grammar(document[GDBMINER_GRAMMAR_KEY])

    if source_start not in grammar:
        raise ValueError(f"start symbol {source_start!r} is not defined in grammar")

    referenced = _collect_referenced_nonterminals(grammar)
    undefined = sorted(referenced.difference(grammar))
    if undefined:
        raise ValueError(f"grammar references undefined nonterminals: {undefined}")

    ordered_symbols = _ordered_unique([source_start, *grammar.keys(), *referenced])
    symbol_map = _build_symbol_map(ordered_symbols)
    ordered_lhs = _ordered_unique([source_start, *grammar.keys()])

    rules: list[NautilusRule] = []
    for source_nonterminal in ordered_lhs:
        nautilus_nonterminal = symbol_map[source_nonterminal]
        for alternative in grammar[source_nonterminal]:
            rhs = "".join(_convert_token(token, symbol_map) for token in alternative)
            rules.append(NautilusRule(nautilus_nonterminal, rhs))

    return NautilusGrammar(
        source_start=source_start,
        start_nonterminal=symbol_map[source_start],
        rules=tuple(rules),
        symbol_map=symbol_map,
    )


def write_nautilus_json(grammar: NautilusGrammar, path: Union[str, Path]) -> None:
    """Write converted NAUTILUS rules as pretty JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(grammar.to_json(), output_file, indent=2)
        output_file.write("\n")


def convert_file(
    input_path: Union[str, Path], output_path: Union[str, Path]
) -> NautilusGrammar:
    """Load a GDBMiner grammar and write a converted NAUTILUS JSON grammar."""

    converted = convert_gdbminer_to_nautilus(load_gdbminer_grammar(input_path))
    write_nautilus_json(converted, output_path)
    return converted


def _expect_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _expect_grammar(value: Any) -> dict[str, list[list[str]]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{GDBMINER_GRAMMAR_KEY} must be an object")

    grammar: dict[str, list[list[str]]] = {}
    for key, alternatives in value.items():
        source_nonterminal = _expect_gdbminer_nonterminal(key)
        if not isinstance(alternatives, Sequence) or isinstance(
            alternatives, (str, bytes)
        ):
            raise ValueError(f"rules for {source_nonterminal!r} must be a list")

        grammar[source_nonterminal] = []
        for alternative in alternatives:
            if not isinstance(alternative, Sequence) or isinstance(
                alternative, (str, bytes)
            ):
                raise ValueError(
                    f"alternative for {source_nonterminal!r} must be a token list"
                )
            tokens = [
                _expect_string(token, f"token in {source_nonterminal!r}")
                for token in alternative
            ]
            grammar[source_nonterminal].append(tokens)

    return grammar


def _expect_gdbminer_nonterminal(symbol: str) -> str:
    if not isinstance(symbol, str) or not _GDBMINER_NONTERMINAL_RE.match(symbol):
        raise ValueError(f"expected GDBMiner nonterminal like '<name>', got {symbol!r}")
    return symbol


def _collect_referenced_nonterminals(
    grammar: Mapping[str, Sequence[Sequence[str]]],
) -> set[str]:
    referenced: set[str] = set()
    for alternatives in grammar.values():
        for alternative in alternatives:
            for token in alternative:
                if _GDBMINER_NONTERMINAL_RE.match(token):
                    referenced.add(token)
    return referenced


def _build_symbol_map(symbols: Sequence[str]) -> dict[str, str]:
    used = {NAUTILUS_ROOT_SYMBOL}
    symbol_map: dict[str, str] = {}
    for symbol in symbols:
        if symbol in symbol_map:
            continue
        candidate = _sanitize_nonterminal_name(symbol)
        unique_candidate = candidate
        suffix = 2
        while unique_candidate in used:
            unique_candidate = f"{candidate}_{suffix}"
            suffix += 1
        used.add(unique_candidate)
        symbol_map[symbol] = unique_candidate
    return symbol_map


def _sanitize_nonterminal_name(symbol: str) -> str:
    match = _GDBMINER_NONTERMINAL_RE.match(symbol)
    if not match:
        raise ValueError(f"expected GDBMiner nonterminal like '<name>', got {symbol!r}")

    name = _UNSAFE_NAUTILUS_NAME_CHARS_RE.sub("_", match.group(1)).strip("_")
    if not name:
        name = "SYMBOL"
    if not name[0].isupper():
        name = f"G_{name}"
    if name == NAUTILUS_ROOT_SYMBOL:
        name = "G_START"
    if not _NAUTILUS_NAME_RE.match(name):
        raise ValueError(f"could not convert {symbol!r} to a NAUTILUS nonterminal")
    return name


def _convert_token(token: str, symbol_map: Mapping[str, str]) -> str:
    if _GDBMINER_NONTERMINAL_RE.match(token):
        return "{" + symbol_map[token] + "}"
    return _escape_nautilus_literal(token)


def _escape_nautilus_literal(token: str) -> str:
    return token.replace("{", r"\{").replace("}", r"\}")


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert GDBMiner grammar JSON into NAUTILUS JSON rules."
    )
    parser.add_argument("input", type=Path, help="Path to GDBMiner parsing_g.json")
    parser.add_argument("output", type=Path, help="Path to write NAUTILUS JSON rules")
    parser.add_argument(
        "--map",
        type=Path,
        help="Optional path to write the GDBMiner-to-NAUTILUS symbol map",
    )
    args = parser.parse_args()

    converted = convert_file(args.input, args.output)
    if args.map:
        args.map.parent.mkdir(parents=True, exist_ok=True)
        with args.map.open("w", encoding="utf-8") as map_file:
            json.dump(dict(converted.symbol_map), map_file, indent=2)
            map_file.write("\n")

    print(json.dumps(converted.summary(), indent=2))


if __name__ == "__main__":
    main()
