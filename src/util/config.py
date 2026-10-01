"""Load TOML without interpreting settings owned by individual backends."""

import tomllib
from pathlib import Path
from typing import Any

# tomllib returns nested dictionaries with native TOML value types.
type Config = dict[str, Any]


def load_config(path: Path) -> Config:
    with path.expanduser().open("rb") as config_file:
        return tomllib.load(config_file)
