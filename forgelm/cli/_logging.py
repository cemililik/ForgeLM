"""Version + logging helpers for the ForgeLM CLI."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

# Module name used both for the package logger and as the `python -m`
# target when forgelm respawns itself for the quickstart subprocess flow.
_CLI_MODULE = "forgelm.cli"

logger = logging.getLogger(_CLI_MODULE)


def _get_version() -> str:
    try:
        return pkg_version("forgelm")
    except PackageNotFoundError:
        from forgelm import __version__

        return __version__


def _setup_logging(log_level: str, json_format: bool = False) -> None:
    """Configure structured logging for the entire forgelm package."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    if json_format:
        # Suppress human-readable logs when JSON output is requested
        numeric_level = logging.WARNING

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
