#!/usr/bin/env python3
"""Wave 6 / Phase 31 — `forgelm.__all__` ↔ library_api_reference.md cross-check.

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
import os
import re
import sys
from pathlib import Path
from typing import Optional, Set

_DOC_ROW_RE = re.compile(
    r"^\|\s*`forgelm\.(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`\s*\|",
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


def _validate_doc_arg(doc_path: Path) -> Optional[str]:
    """Return an error message if ``--doc`` can't be opened for reading; else None.

    Catches: missing file, directory passed in place of a file, and
    permission-denied (``os.access``). Callers map a non-None return to
    exit code 1 with the message printed on stderr.
    """
    if not doc_path.exists():
        return f"check_library_api_doc: --doc {doc_path!r} does not exist."
    if not doc_path.is_file():
        return f"check_library_api_doc: --doc {doc_path!r} is not a regular file."
    if not os.access(doc_path, os.R_OK):
        return f"check_library_api_doc: --doc {doc_path!r} is not readable (permission denied)."
    return None


def _build_arg_parser() -> argparse.ArgumentParser:
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
    return parser


def _import_forgelm_or_explain():
    """Return ``forgelm`` module on success; print install hint and return None on ImportError.

    Fail-closed callers map the ``None`` return to exit code 2.
    """
    try:
        import forgelm  # type: ignore

        return forgelm
    except ImportError as exc:
        print(
            f"check_library_api_doc: cannot import forgelm ({exc}). "
            "Install ForgeLM (`pip install -e .`) before running this guard.",
            file=sys.stderr,
        )
        return None


def _print_drift_section(title: str, names: Set[str]) -> None:
    """Print one numbered drift bucket (e.g. 'In __all__ but missing from doc')."""
    if not names:
        return
    print(f"\n  {title} ({len(names)}):")
    for name in sorted(names):
        print(f"    - forgelm.{name}")


def main(argv=None) -> int:
    args = _build_arg_parser().parse_args(argv)

    err = _validate_doc_arg(args.doc)
    if err is not None:
        print(err, file=sys.stderr)
        return 1

    forgelm = _import_forgelm_or_explain()
    if forgelm is None:
        return 2

    runtime_all: Set[str] = set(forgelm.__all__)
    try:
        doc_names: Set[str] = doc_symbols(args.doc)
    except OSError as exc:
        # _validate_doc_arg covers the predictable cases; this catches
        # racier failures (file deleted between the check and the read).
        print(f"check_library_api_doc: failed to read --doc {args.doc!r} ({exc}).", file=sys.stderr)
        return 1

    # Method-style names under documented classes count toward
    # 'doc has it'. Top-level names go in __all__ directly; dotted
    # names must reference a class that IS in __all__.
    doc_top_level: Set[str] = {n for n in doc_names if "." not in n}
    doc_methods: Set[str] = {n for n in doc_names if "." in n}

    missing_in_doc = runtime_all - doc_top_level
    extra_in_doc = doc_top_level - runtime_all
    orphan_methods = {m for m in doc_methods if m.split(".", 1)[0] not in runtime_all}

    if missing_in_doc or extra_in_doc or orphan_methods:
        print("FAIL: forgelm.__all__ ↔ library_api_reference.md drift detected.")
        _print_drift_section("In __all__ but missing from doc", missing_in_doc)
        _print_drift_section("In doc but not in __all__", extra_in_doc)
        _print_drift_section("Method rows whose parent is not in __all__", orphan_methods)
        return 1

    if not args.quiet:
        print(
            f"OK: {len(runtime_all)} symbols in forgelm.__all__ all match the "
            f"{len(doc_top_level)} top-level row(s) (+ {len(doc_methods)} method rows) under {args.doc}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
