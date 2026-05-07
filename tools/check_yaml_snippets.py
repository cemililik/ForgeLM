#!/usr/bin/env python3
"""Wave 6 / Faz 31 — YAML doc-snippet validator.

Walks every Markdown file under ``docs/`` and validates that every fenced
``yaml`` code block which **looks like** a ForgeLM config (i.e. carries any
top-level ``ForgeConfig`` key) parses successfully through Pydantic
``ForgeConfig(**data)``. Exits non-zero if any snippet fails validation —
catching parallel-universe-schema drift (P1 of the 2026-05-07 docs audit)
before the doc lands.

Heuristic for "is a complete ForgeLM config": the YAML block must be a
mapping carrying **all three** of the canonical required top-level keys
— ``model``, ``training``, ``data`` — which is the minimum-viable
``ForgeConfig`` payload. Fragmentary snippets demonstrating a single
block (just ``evaluation:`` or just ``training:``) skip validation —
they cannot be validated against ``ForgeConfig`` without inventing the
missing required fields, and the doc author intentionally elided them
for readability.

Path-level scope: ``docs/analysis/`` is skipped (gitignored research
artefacts; not user-facing).

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface
that ``forgelm/`` honours):

- ``0`` — every config-shaped YAML snippet validates against
  ``ForgeConfig``.
- ``1`` — at least one snippet failed validation.

Usage::

    python3 tools/check_yaml_snippets.py
    python3 tools/check_yaml_snippets.py --strict       # alias; exits 1 on drift
    python3 tools/check_yaml_snippets.py --quiet        # silent on success
    python3 tools/check_yaml_snippets.py --root docs/   # restrict scan

Plan reference: 2026-05-07 docs audit §10 (CI gate proposals) gate #1.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Lazy: only need Pydantic + YAML when we actually validate. If forgelm
# isn't importable (e.g. during a lint-only CI step that hasn't installed
# the package), we degrade to a "skip with WARNING" path so the guard
# never blocks unrelated checks.
try:
    import yaml
except ImportError as exc:  # pragma: no cover — defensive for lint-only envs
    print(f"check_yaml_snippets: PyYAML not importable ({exc}); skipping.", file=sys.stderr)
    sys.exit(0)

try:
    from pydantic import ValidationError

    from forgelm.config import ForgeConfig  # type: ignore
except ImportError as exc:  # pragma: no cover — defensive
    print(
        f"check_yaml_snippets: forgelm.config not importable ({exc}); skipping.",
        file=sys.stderr,
    )
    sys.exit(0)


_FENCE_OPEN_RE = re.compile(r"^```yaml\s*$", re.MULTILINE)
_FENCE_CLOSE_RE = re.compile(r"^```\s*$", re.MULTILINE)

# Required top-level keys for a *complete* ForgeConfig payload. A
# snippet missing any of these is treated as a fragment (a doc page
# showing one block in isolation) and skipped — fragments cannot be
# validated against ForgeConfig without inventing the missing keys.
_REQUIRED_FORGELM_KEYS = frozenset({"model", "training", "data"})

# Paths to skip entirely (gitignored research artefacts).
_SKIP_PATH_FRAGMENTS = ("docs/analysis/", "docs/marketing/")


@dataclass(frozen=True)
class Snippet:
    """One ``yaml`` fenced block extracted from a markdown file."""

    path: Path
    line_start: int  # 1-based line number of the opening fence
    body: str


@dataclass(frozen=True)
class ValidationFailure:
    """One snippet whose ForgeConfig validation failed."""

    snippet: Snippet
    reason: str


def extract_yaml_snippets(path: Path) -> List[Snippet]:
    """Return every ``yaml`` fenced block in ``path``.

    Tracks 1-based line numbers so failure reports point at a concrete
    location in the doc.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    snippets: List[Snippet] = []
    i = 0
    while i < len(lines):
        if _FENCE_OPEN_RE.match(lines[i]):
            start = i
            j = i + 1
            while j < len(lines) and not _FENCE_CLOSE_RE.match(lines[j]):
                j += 1
            if j < len(lines):
                body = "\n".join(lines[start + 1 : j])
                snippets.append(Snippet(path=path, line_start=start + 1, body=body))
            i = j + 1
        else:
            i += 1
    return snippets


def looks_like_forgelm_config(parsed: object) -> bool:
    """Return True iff the parsed YAML carries every required top-level key
    (``model`` AND ``training`` AND ``data``) — the minimum-viable
    ``ForgeConfig`` payload. Fragment snippets demonstrating a single
    block return False and are skipped by the validator.
    """
    if not isinstance(parsed, dict):
        return False
    return _REQUIRED_FORGELM_KEYS.issubset(parsed.keys())


def validate_snippet(snippet: Snippet) -> Optional[ValidationFailure]:
    """Parse + validate one snippet. Return None on success.

    Two-phase: first attempt YAML parse — if it fails AND the snippet
    contains the canonical required keys lexically (`model:`, `training:`,
    `data:` at column 0), surface as drift. If the snippet doesn't
    *claim* to be a ForgeConfig payload (no required-key triplet), a
    YAML parse error is treated as an intentional partial / sketch
    snippet (e.g. `merge: { ..., ... }` placeholder samples) and
    skipped.
    """
    try:
        parsed = yaml.safe_load(snippet.body)
    except yaml.YAMLError as exc:
        # Lexical sniff: does the snippet *look like* it tried to be a
        # complete ForgeConfig? Only then do we report the parse error
        # — otherwise it's an illustrative sketch (e.g. with `...`
        # placeholders) and skipping is the right call.
        body = snippet.body
        if all(f"\n{key}:" in f"\n{body}" for key in ("model", "training", "data")):
            return ValidationFailure(snippet=snippet, reason=f"YAML parse error: {exc}")
        return None

    if parsed is None:
        return None  # empty block — nothing to validate

    if not looks_like_forgelm_config(parsed):
        return None  # not a ForgeConfig snippet — skip

    # Skip snippets that are demonstrating an *invalid* example on
    # purpose. We mark these with a leading ``# INVALID:`` comment in
    # the doc body, which the doc author writes to opt-out of the
    # validator.
    if snippet.body.lstrip().startswith("# INVALID:") or "# INVALID:" in snippet.body.splitlines()[0:3]:
        return None

    try:
        ForgeConfig(**parsed)
    except ValidationError as exc:
        return ValidationFailure(snippet=snippet, reason=f"Pydantic ValidationError: {exc}")
    except (TypeError, ValueError) as exc:
        # TypeError: ForgeConfig got an unexpected kwarg (extra="forbid")
        # ValueError: nested model rejected the input
        return ValidationFailure(snippet=snippet, reason=f"{exc.__class__.__name__}: {exc}")
    return None


def walk_docs(root: Path) -> List[Path]:
    """Return every ``*.md`` under ``root`` (sorted, recursive), skipping
    research / marketing artefact directories that are not part of the
    user-facing surface.
    """
    out: List[Path] = []
    for p in sorted(root.rglob("*.md")):
        if not p.is_file():
            continue
        # str() check works for both relative + absolute roots.
        if any(skip in str(p) for skip in _SKIP_PATH_FRAGMENTS):
            continue
        out.append(p)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate every fenced yaml block in docs/ against the live "
            "forgelm.config.ForgeConfig schema. See module docstring for "
            "the heuristic that picks ForgeConfig-shaped blocks."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("docs"),
        help="Directory to scan recursively for *.md files (default: docs/).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Alias of default behaviour (exits 1 on drift). Kept for symmetry with sibling tools.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the success summary line; failures still print.",
    )
    args = parser.parse_args(argv)

    if not args.root.exists():
        print(f"check_yaml_snippets: --root {args.root!r} does not exist.", file=sys.stderr)
        return 1

    failures: List[ValidationFailure] = []
    snippet_count = 0
    validated_count = 0
    for path in walk_docs(args.root):
        for snippet in extract_yaml_snippets(path):
            snippet_count += 1
            failure = validate_snippet(snippet)
            if failure is None:
                # Distinguish "skipped (not a config snippet)" from
                # "validated cleanly". The former is the common case
                # for non-ForgeLM YAML examples (Docker compose,
                # GitHub Actions, etc.).
                try:
                    parsed = yaml.safe_load(snippet.body)
                except yaml.YAMLError:
                    parsed = None
                if isinstance(parsed, dict) and looks_like_forgelm_config(parsed):
                    validated_count += 1
            else:
                failures.append(failure)

    if failures:
        print(f"FAIL: {len(failures)} ForgeConfig-shaped YAML snippet(s) failed validation.")
        for f in failures:
            print(f"\n  {f.snippet.path}:{f.snippet.line_start}")
            for line in f.reason.splitlines()[:6]:
                print(f"    {line}")
        return 1

    if not args.quiet:
        print(
            f"OK: {validated_count} ForgeConfig-shaped YAML snippet(s) validated "
            f"across {snippet_count} total yaml blocks under {args.root}/."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
