"""Versioned API contract for the ``forgelm`` library surface.

Phase 19 (Library API).  Two version strings live here so consumers
can pin against either independently:

- ``__version__`` — the package version (mirrors what
  ``importlib.metadata.version("forgelm")`` returns; sourced from
  pyproject.toml at install time, overridden to ``"0.0.0+dev"`` for
  raw-source checkouts).
- ``__api_version__`` — the *public Python API* contract version, bumped
  when a stable symbol's signature changes (additions are minor, removals
  / signature changes are major).  Consumers that depend on the library
  API can pin against this without coupling to the CLI version.

Per ``docs/design/library_api.md`` §4.3, the two versions track separately because the CLI surface and the
Python API have different stability windows — the CLI may grow new
subcommands without affecting library consumers, and library additions
do not necessarily ship a new CLI feature.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("forgelm")
except PackageNotFoundError:  # pragma: no cover — uninstalled-source path
    __version__ = "0.0.0+dev"

# Public Python API contract version.  Bump rules:
#   MAJOR  — removed or signature-changed a stable symbol.
#   MINOR  — added a new stable symbol.
#   PATCH  — implementation change with no API surface impact.
#
# v0.5.5 (this release) introduces the formal Phase 19 library-API
# surface — first publication of the contract, so we anchor at 1.0.0.
__api_version__ = "1.0.0"

__all__ = ["__version__", "__api_version__"]
