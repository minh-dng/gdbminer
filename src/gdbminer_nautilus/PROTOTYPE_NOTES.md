# PROTOTYPE - GDBMiner to NAUTILUS Adapter

Question: can a GDBMiner `parsing_g.json` grammar be converted into a grammar
that NAUTILUS can load and sample?

Current slice:

- `gdbminer_nautilus.grammar_adapter` converts the Fuzzing Book-style
  GDBMiner grammar object into NAUTILUS JSON rules.
- `gdbminer_nautilus.nautilus_runner` invokes the local NAUTILUS checkout's
  `generator` binary through Cargo and returns generated input bytes.
- `scripts/prototype_nautilus_pipeline.py` composes both pieces and prints the
  conversion state after each run.

Run:

```bash
PYTHONPATH="$PWD/src" python3 scripts/prototype_nautilus_pipeline.py
```

Convert only:

```bash
PYTHONPATH="$PWD/src" python3 -m gdbminer_nautilus.convert \
  evaluation/stm32_applications/stm32_cgidecode/trial-0/parsing_g.json \
  output/prototype_nautilus/gdbminer.nautilus.json
```

Assumption: `third_party/nautilus` is a local SSH clone of
`git@github.com:nautilus-fuzz/nautilus.git`.

This remains a prototype. The next durable decision is whether the thesis
pipeline should keep NAUTILUS JSON as the adapter boundary or move to Python
grammar files to express regex terminals and future semantic constraints.
