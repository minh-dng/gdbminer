# Ruff configuration recommendation

Checked against the current official Ruff documentation on 20 August 2026.

## Recommendation

For this repository, start with:

```toml
[tool.ruff]
extend-exclude = ["example_programs"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]
```

No `[tool.ruff.format]` table is needed. Ruff already defaults to an 88-character
line length, four-space indentation, double quotes, magic trailing commas, and
automatic line-ending detection. Repeating those values adds noise without
changing behavior. [Ruff configuration defaults][configuration]

Use `extend-exclude`, not `exclude`, for the repository-specific directory.
`exclude` replaces Ruff's built-in list, while `extend-exclude` adds to it. Ruff
also respects Git ignore files by default. [File discovery][discovery]

An explicit `target-version = "py39"` is valid but unnecessary here. Ruff can
infer Python 3.9 from this `pyproject.toml` file's
`requires-python = ">=3.9,<3.10"`. Do not use the proposed `py313`; it disagrees
with the project's declared supported version. [Python version inference][target]

The `I` extension is the one extra category worth enabling at setup because the
formatter does not sort imports. Ruff documents running `ruff check --select I
--fix` before `ruff format`. [Import sorting][imports]

## Rule selection

Ruff recommends starting with a small rule set and adding categories gradually.
Its example of a broader, popular set is `E`, `F`, `UP`, `B`, `SIM`, and `I`.
For an existing research codebase, adopting all of those at once would create a
large migration unrelated to formatting. Freeze the conservative Pyflakes and
pycodestyle baseline plus import sorting explicitly. This avoids rule-set drift
between Ruff releases. [Rule selection][lint]

Do not enable preview mode by default. It opts into unstable rules, fixes,
formatter changes, and interface changes. Enabling preview also does not select
all preview lint rules automatically. [Preview mode][preview]

If the rule set expands later, avoid the lint rules Ruff lists as conflicting
with its formatter, including `W191`, `E111`, `E114`, `E117`, `D203`, `D206`,
`D300`, `Q000` through `Q004`, `COM812`, and `COM819`. Ruff emits a formatter
warning for incompatible configuration. [Formatter conflicts][conflicts]

[configuration]: https://docs.astral.sh/ruff/configuration/
[discovery]: https://docs.astral.sh/ruff/configuration/#python-file-discovery
[target]: https://docs.astral.sh/ruff/configuration/#inferring-the-python-version
[imports]: https://docs.astral.sh/ruff/formatter/#sorting-imports
[lint]: https://docs.astral.sh/ruff/linter/#rule-selection
[preview]: https://docs.astral.sh/ruff/preview/
[conflicts]: https://docs.astral.sh/ruff/formatter/#conflicting-lint-rules
