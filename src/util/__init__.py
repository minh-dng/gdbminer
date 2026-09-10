from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(output_directory: Path, loglevel: str) -> None:
    logger = logging.getLogger()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s %(funcName)s()] %(message)s"
    )

    file_logger = logging.FileHandler(output_directory / "out.log")
    file_logger.setLevel(loglevel)
    file_logger.setFormatter(formatter)
    logger.addHandler(file_logger)

    stdout_logger = logging.StreamHandler()
    stdout_logger.setLevel(loglevel)
    stdout_logger.setFormatter(formatter)
    logger.addHandler(stdout_logger)

    logging.root.setLevel(loglevel)


def find_output_directory(output_directory_base: Path) -> Path:
    """Find the last 'trial-*' folder in the output directory base."""
    return next(
        iter(
            sorted(
                output_directory_base.glob("trial-*"),
                key=lambda x: int(x.name.split("-")[1]),
                reverse=True,
            )
        )
    )
