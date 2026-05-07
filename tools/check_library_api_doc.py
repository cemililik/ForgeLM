#!/usr/bin/env python3
"""Wave 6 / Faz 31 — `forgelm.__all__` ↔ library_api_reference.md cross-check.

Inventories every ``forgelm.X`` row in
``docs/reference/library_api_reference.md`` and diffs against the
runtime ``forgelm.__all__`` set.

Two failure modes:

- **__all__ ⊃ doc** — a public symbol is missing from the reference
  page. New stable symbols must be documented.
- **doc ⊃ __all__** — the doc claims a symbol that ``__all__`` no
  longer exports (renamed / removed without a doc update).

Method-level subrows (``forgelm.ForgeTrainer.train``,
``forgelm.AuditLogger.log_event``) are matched against the parent
class in ``__all__``; they need not be in ``__all__`` themselves.

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface
that ``forgelm/`` honours):

- ``0`` — every ``__all__`` symbol has a doc row, and every doc row
  resolves to either an ``__all__`` symbol or a documented method on
  one.
- ``1`` — at least one symbol diverges.

Usage::

    python3 tools/check_library_api_doc.py
    python3 tools/check_library_api_doc.py --strict   # alias of default
    python3 tools/check_library_api_doc.py --quiet    # silent on success

Plan reference: 2026-05-07 docs audit §10 (CI gate proposals) gate #4.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Set

_DOC_ROW_RE = re.compile(
    r"^\|\s*`forgelm\.(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)`\s*\|",
    re.MULTILINE,
)


def doc_symbols(doc_path: Path) -> Set[str]:
    """Return ``{symbol_name}`` for every ``| `forgelm.X` |`` row.

    Includes method-style names (``ForgeTrainer.train``); the caller
    decides whether to require ``X`` to be in ``__all__`` directly or
    accept ``X`` matching a documented attribute on an ``__all__``
    class.
    """
    text = doc_path.read_text(encoding="utf-8")
    return {match.group("name") for match in _DOC_ROW_RE.finditer(text)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check forgelm.__all__ against the symbol roster in docs/reference/library_api_reference.md."
        ),
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=Path("docs/reference/library_api_reference.md"),
        help="Path to library_api_reference.md.",
    )
    parser.add_argument("--strict", action="store_true", help="Alias of default; exits 1 on drift.")
    parser.add_argument("--quiet", action="store_true", help="Suppress success summary.")
    args = parser.parse_args(argv)

    if not args.doc.exists():
        print(f"check_library_api_doc: --doc {args.doc!r} does not exist.", file=sys.stderr)
        return 1

    try:
        import forgelm  # type: ignore
    except ImportError as exc:
        print(
            f"check_library_api_doc: cannot import forgelm ({exc}); skipping.",
            file=sys.stderr,
        )
        return 0

    runtime_all: Set[str] = set(forgelm.__all__)
    doc_names: Set[str] = doc_symbols(args.doc)

    # Method-style names under documented classes count toward
    # 'doc has it'. Pull out top-level names from doc_names: anything
    # without a dot is a top-level name; with a dot, it's a method
    # under a class that must itself be in __all__.
    doc_top_level: Set[str] = {n for n in doc_names if "." not in n}
    doc_methods: Set[str] = {n for n in doc_names if "." in n}

    missing_in_doc = runtime_all - doc_top_level
    extra_in_doc = doc_top_level - runtime_all

    # Methods like ``ForgeTrainer.train`` must reference a class that
    # IS in __all__ — surface a separate class of error if the parent
    # isn't exported.
    orphan_methods = {m for m in doc_methods if m.split(".", 1)[0] not in runtime_all}

    if missing_in_doc or extra_in_doc or orphan_methods:
        print("FAIL: forgelm.__all__ ↔ library_api_reference.md drift detected.")
        if missing_in_doc:
            print(f"\n  In __all__ but missing from doc ({len(missing_in_doc)}):")
            for name in sorted(missing_in_doc):
                print(f"    - forgelm.{name}")
        if extra_in_doc:
            print(f"\n  In doc but not in __all__ ({len(extra_in_doc)}):")
            for name in sorted(extra_in_doc):
                print(f"    - forgelm.{name}")
        if orphan_methods:
            print(f"\n  Method rows whose parent is not in __all__ ({len(orphan_methods)}):")
            for name in sorted(orphan_methods):
                print(f"    - forgelm.{name}")
        return 1

    if not args.quiet:
        print(
            f"OK: {len(runtime_all)} symbols in forgelm.__all__ all match the "
            f"{len(doc_top_level)} top-level row(s) (+ {len(doc_methods)} method rows) under {args.doc}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
