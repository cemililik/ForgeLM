#!/usr/bin/env python3
"""Wave 2-9 — module-size ceiling guard for ``forgelm/``.

The architecture standard
(:doc:`docs/standards/architecture.md`, "~1000-line ceiling is the
trigger for a sub-package split") sets a soft cap of **1000 lines of
code** per module under ``forgelm/``.  Beyond that, the file owns too
many concerns and should be split into a sub-package
(``module_name/`` directory with the same public import path).

This guard catches **future drift** without forcing an immediate
refactor of the seven modules that already sit over the ceiling at
PR #29 HEAD.  Those seven are recorded in
:data:`_GRANDFATHERED_OVER_CEILING`; their splits are tracked for
the v0.6.x cycle (see ``docs/roadmap/risks-and-decisions.md``).

LOC metric
----------
The canonical metric is **non-blank, non-comment-only lines** —
i.e. the standard "code lines" notion used by ``cloc`` / ``tokei``.
Excluded from the count:

* Blank lines.
* Lines whose stripped content starts with ``#`` (pure-comment lines,
  including shebangs and the file-level ``# noqa`` markers).

Included (intentionally):

* Module / class / function docstrings.  They are part of the file's
  review burden — a 600-line docstring still represents 600 lines of
  prose someone has to maintain — and excluding them would let
  contributors silently grow a module by inflating its docstrings.

Thresholds
----------
* **Warn at ``> 1000``** — non-fatal in default mode.  The guard
  prints a one-line warning per offender; CI may surface this as a
  soft signal.
* **Fail at ``> 1500``** — fatal (exit 1) for non-grandfathered
  modules.  A 50% over-ceiling module is an architectural emergency.
* ``--strict`` mode promotes the warn threshold to a fatal one for
  non-grandfathered modules.  Grandfathered modules continue to emit
  WARN (with the "v0.6.x defer" hint) regardless of mode.

Exit codes (per the ``tools/`` contract — NOT the public 0/1/2/3/4
surface that ``forgelm/`` honours):

* ``0`` — no NEW drift; every over-threshold module is grandfathered.
* ``1`` — at least one NEW over-threshold module (or ``--strict``
  applied to a NEW over-warn module), or invalid arguments.

Usage::

    python3 tools/check_module_size.py
    python3 tools/check_module_size.py --strict
    python3 tools/check_module_size.py --quiet
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_WARN_THRESHOLD = 1000
_FAIL_THRESHOLD = 1500

# Modules that already exceeded the architecture-doc ceiling at PR #29
# HEAD (v0.5.5-prerelease cleanup).  Splits are deferred to v0.6.x —
# the guard's job is to prevent NEW drift, not force their refactor
# today.  When a grandfathered module is split (or trimmed below
# threshold), remove its entry here in the same PR that lands the
# split.
#
# Paths are POSIX-style relative to the repository root so behaviour
# is identical on macOS / Linux / Windows-WSL.
_GRANDFATHERED_OVER_CEILING: frozenset[str] = frozenset(
    {
        "forgelm/compliance.py",
        "forgelm/trainer.py",
        "forgelm/ingestion.py",
        "forgelm/cli/subcommands/_purge.py",
        "forgelm/config.py",
        "forgelm/cli/_parser.py",
        "forgelm/cli/subcommands/_doctor.py",
    }
)


@dataclass(frozen=True)
class _Measurement:
    """One ``forgelm/`` Python file with its measured code-line count."""

    path: str  # POSIX-relative to the repo root.
    loc: int


def _count_code_lines(path: Path) -> int:
    """Count non-blank, non-comment-only lines in a Python file.

    Docstrings are intentionally counted (see module docstring for
    rationale).  We do not parse the file as Python AST; a line-level
    classification is sufficient for the size signal and orders of
    magnitude faster on a 75-file walk.
    """
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


def _walk_forgelm(root: Path) -> list[Path]:
    """Return all ``.py`` files under ``root``, sorted, excluding caches."""
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _measure(repo_root: Path, forgelm_root: Path) -> list[_Measurement]:
    """Walk ``forgelm/`` and return one :class:`_Measurement` per file."""
    out: list[_Measurement] = []
    for f in _walk_forgelm(forgelm_root):
        rel = f.relative_to(repo_root).as_posix()
        out.append(_Measurement(path=rel, loc=_count_code_lines(f)))
    return out


def _classify(
    measurements: Sequence[_Measurement],
) -> tuple[list[_Measurement], list[_Measurement]]:
    """Partition measurements into (over-warn, over-fail) bands.

    ``over-fail`` is a strict subset relationship: a module over the
    fail threshold is reported in ``over-fail`` only (not also in
    ``over-warn``) so callers can render the two bands without
    duplication.
    """
    over_warn: list[_Measurement] = []
    over_fail: list[_Measurement] = []
    for m in measurements:
        if m.loc > _FAIL_THRESHOLD:
            over_fail.append(m)
        elif m.loc > _WARN_THRESHOLD:
            over_warn.append(m)
    return over_warn, over_fail


def _is_grandfathered(path: str) -> bool:
    return path in _GRANDFATHERED_OVER_CEILING


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Walk ``forgelm/`` and apply the size-ceiling policy.

    Returns the process exit code (0 / 1).  Centralised so tests can
    invoke ``main([...])`` without ``sys.exit``-ing the test runner.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Verify no module under forgelm/ has drifted past the architecture-doc 1000-LOC sub-package-split ceiling."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Treat the warn threshold (>1000 LOC) as fatal for "
            "non-grandfathered modules.  Grandfathered modules still "
            "emit WARN (with v0.6.x defer hint) regardless of mode."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the per-file WARN lines and the OK summary; print only on FAIL.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Override the repository root (defaults to the parent of "
            "the directory containing this script).  Test-only knob."
        ),
    )
    args = parser.parse_args(argv)

    if args.repo_root is not None:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent
    forgelm_root = repo_root / "forgelm"
    if not forgelm_root.is_dir():
        print(
            f"ERROR: forgelm/ source tree not found at {forgelm_root}",
            file=sys.stderr,
        )
        return 1

    measurements = _measure(repo_root, forgelm_root)
    over_warn, over_fail = _classify(measurements)

    # Bucket each band by grandfathered-vs-new for reporting + exit logic.
    new_over_fail = [m for m in over_fail if not _is_grandfathered(m.path)]
    grandfathered_over_fail = [m for m in over_fail if _is_grandfathered(m.path)]
    new_over_warn = [m for m in over_warn if not _is_grandfathered(m.path)]
    grandfathered_over_warn = [m for m in over_warn if _is_grandfathered(m.path)]

    fatal = False

    # Always print FAIL lines — the loudest signal first.
    for m in new_over_fail:
        print(
            f"FAIL: {m.path} = {m.loc} LOC (> {_FAIL_THRESHOLD} fail-threshold; "
            f"NEW drift — split into a sub-package before merge)",
            file=sys.stderr,
        )
        fatal = True
    for m in grandfathered_over_fail:
        if not args.quiet:
            print(
                f"WARN: {m.path} = {m.loc} LOC (> {_FAIL_THRESHOLD} fail-threshold; "
                f"grandfathered, defer to v0.6.x split)"
            )

    # WARN lines for over-1000 (non-grandfathered): fatal only under --strict.
    for m in new_over_warn:
        if args.strict:
            print(
                f"FAIL: {m.path} = {m.loc} LOC (> {_WARN_THRESHOLD} warn-threshold; "
                f"--strict mode — NEW drift, plan a sub-package split)",
                file=sys.stderr,
            )
            fatal = True
        elif not args.quiet:
            print(
                f"WARN: {m.path} = {m.loc} LOC (> {_WARN_THRESHOLD} warn-threshold; "
                f"plan a sub-package split before this grows further)"
            )
    for m in grandfathered_over_warn:
        if not args.quiet:
            print(
                f"WARN: {m.path} = {m.loc} LOC (> {_WARN_THRESHOLD} warn-threshold; "
                f"grandfathered, defer to v0.6.x split)"
            )

    grandfathered_count = len(grandfathered_over_fail) + len(grandfathered_over_warn)
    if not args.quiet:
        print(
            f"Checked {len(measurements)} modules under forgelm/; "
            f"{len(over_warn)} over warn-threshold ({_WARN_THRESHOLD}), "
            f"{len(over_fail)} over fail-threshold ({_FAIL_THRESHOLD}), "
            f"{grandfathered_count} grandfathered."
        )

    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
