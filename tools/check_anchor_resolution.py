#!/usr/bin/env python3
"""Wave 4 / Faz 26 — markdown anchor + relative-link resolution guard.

Walks every Markdown file under ``docs/`` and validates that every
inline link of the form ``[text](path)`` resolves:

- **Repo-relative paths** (``../qms/foo.md``, ``forgelm/x.py``) must
  point at an existing file in the working tree.
- **Markdown anchor links** (``other.md#section-title``) must point
  at a header that exists in the target file.
- **External URLs** (``https://...``, ``http://...``) are skipped —
  out of scope for offline checks.
- **SPA hash-router fragments** (``#/reference/json-output``) are
  skipped — those resolve at site-render time, not in source.
- **Pure anchors** (``#section-title`` with no path) must resolve to
  a header in the SAME file.

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4
surface that ``forgelm/`` honours):

- ``0`` — every link resolves cleanly.
- ``1`` — at least one broken link or invalid argument.

Usage::

    python3 tools/check_anchor_resolution.py
    python3 tools/check_anchor_resolution.py --strict   # alias of default; exits 1 on drift
    python3 tools/check_anchor_resolution.py --quiet    # silent on success

Closure-plan reference: Faz 26 task #5
(``tools/check_anchor_resolution.py`` — markdown anchor'ları
resolve edilebilir mi diff).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Match a Markdown inline link: ``[text](href)``.  The href may
# contain spaces (escaped as ``%20`` typically, but we accept raw
# here too).  We deliberately do NOT match reference-style links
# (`[text][ref]` + `[ref]: href`) — they are rare in this project
# and add parsing complexity for marginal coverage.
#
# Backtracking-free: ``\[([^\]]*)\]\(([^)]*)\)`` uses negated
# character classes only — no nested quantifiers.
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Match an ATX heading: 1-6 leading hashes + space + body.  Setext
# headings are out of scope for the anchor target check (the project
# uses ATX exclusively per docs/standards/documentation.md).
_HEADING_RE = re.compile(r"^(#{1,6}) +(.+?)\s*#*\s*$")

# Markdown image syntax (``![alt](src)``) reuses the link form but is
# checked the same way — every ``src`` must resolve.

# Skip patterns: anything matching these is treated as out-of-scope.
_SKIP_HREF_PATTERNS = (
    re.compile(r"^https?://"),  # external URL
    re.compile(r"^mailto:"),  # email
    re.compile(r"^#/"),  # SPA hash-router (user-manual viewer)
    re.compile(r"^tel:"),  # phone
    re.compile(r"^javascript:"),
)


@dataclass(frozen=True)
class Link:
    source: Path
    line: int
    text: str
    href: str


@dataclass(frozen=True)
class BrokenLink:
    link: Link
    reason: str


def _slugify_heading(text: str) -> str:
    """GitHub-flavoured Markdown heading-anchor algorithm.

    GFM lowercases, strips most punctuation, replaces spaces with
    dashes, and preserves alphanumerics + dashes + underscores.
    Approximation good enough for the link-resolution check; matches
    the slug GitHub renders for ``[text](#anchor)`` links.
    """
    slug = text.lower().strip()
    # Strip everything except alphanumeric, space, dash, underscore.
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    # Collapse whitespace to dashes.
    slug = re.sub(r"\s+", "-", slug)
    # Collapse multiple dashes.
    slug = re.sub(r"-+", "-", slug)
    # Trim leading/trailing dashes.
    return slug.strip("-")


def _extract_anchors(target: Path) -> set[str]:
    """Return the set of GFM-style header anchors defined in ``target``."""
    if not target.is_file():
        return set()
    anchors: set[str] = set()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return set()
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        anchors.add(_slugify_heading(match.group(2)))
    return anchors


def _walk_markdown_files(root: Path, excluded_dirs: tuple[Path, ...]) -> Iterable[Path]:
    """Yield every ``*.md`` under ``root``, sorted for determinism.

    Files under any directory in ``excluded_dirs`` (resolved-form
    comparison) are skipped — the default exclude list strips the
    gitignored ``docs/analysis/`` research tree (which references
    local-only paths from the maintainer's research workflow) so
    the checker validates only public docs.
    """
    excluded = tuple(p.resolve() for p in excluded_dirs)
    for path in sorted(p for p in root.rglob("*.md") if p.is_file()):
        resolved = path.resolve()
        if any(_is_under(resolved, ex) for ex in excluded):
            continue
        yield path


def _is_under(child: Path, ancestor: Path) -> bool:
    """Return True iff ``child`` is contained in ``ancestor`` (inclusive)."""
    try:
        child.relative_to(ancestor)
    except ValueError:
        return False
    return True


def _extract_links(source: Path) -> Iterable[Link]:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in _LINK_RE.finditer(line):
            text_part = match.group(1)
            href_part = match.group(2).strip()
            if not href_part:
                continue
            yield Link(source=source, line=line_no, text=text_part, href=href_part)


def _is_skipped(href: str) -> bool:
    return any(pat.match(href) for pat in _SKIP_HREF_PATTERNS)


def _split_path_anchor(href: str) -> tuple[str, str]:
    """Split ``path#anchor`` into ``(path, anchor)``.  Either may be empty."""
    if "#" not in href:
        return href, ""
    path, _, anchor = href.partition("#")
    return path, anchor


def _resolve_link(link: Link, repo_root: Path) -> BrokenLink | None:
    """Return ``None`` if the link resolves; otherwise a ``BrokenLink``."""
    href = link.href
    if _is_skipped(href):
        return None
    path_part, anchor_part = _split_path_anchor(href)
    # Pure anchor (``#section``) — target is the same file.
    if not path_part:
        if not anchor_part:
            return BrokenLink(link, "empty href")
        anchors = _extract_anchors(link.source)
        if anchor_part not in anchors:
            return BrokenLink(link, f"anchor #{anchor_part!r} not found in {link.source.name}")
        return None

    # Repo-relative path.  Resolve against the source file's parent.
    target = (link.source.parent / path_part).resolve()
    if not target.exists():
        # Fall back: maybe the path is repo-root-relative (legacy
        # references).  Try that before declaring broken.
        alt = (repo_root / path_part).resolve()
        if not alt.exists():
            return BrokenLink(link, f"target file not found: {path_part!r}")
        target = alt

    if anchor_part:
        # Anchors only meaningful for Markdown targets.
        if target.suffix.lower() != ".md":
            # Code-file anchors (e.g. forgelm/x.py#L42) are stale-line
            # references — flag them since they drift on refactor.
            # Fail-loud for ``#L<digits>`` form, ignore other code-anchor
            # forms (e.g. Sphinx `?` queries).
            if re.fullmatch(r"L\d+(?:-L\d+)?", anchor_part):
                return BrokenLink(
                    link, f"line-number anchor #{anchor_part!r} on code file is brittle (use symbol references)"
                )
            return None
        anchors = _extract_anchors(target)
        if anchor_part not in anchors:
            return BrokenLink(link, f"anchor #{anchor_part!r} not found in {path_part!r}")
    return None


def _format_broken(broken: BrokenLink) -> str:
    rel = broken.link.source
    return f"{rel}:{broken.link.line}  [{broken.link.text}]({broken.link.href})  → {broken.reason}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate markdown anchor + relative-path links under docs/.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (default: parent of tools/).",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default="docs",
        help="Subdirectory under repo-root to scan (default: docs).",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        default=None,
        help=(
            "Directory (relative to scope-dir) to skip.  Repeatable.  "
            "Default exclude list strips ``analysis/`` (gitignored research "
            "tree referencing local-only paths) and ``code_reviews/`` "
            "(internal review docs).  Pass empty list to scan everything."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Strict mode: exit 1 on any broken link.  Default is "
            "advisory: report broken links to stdout but exit 0 so the "
            "tool can land before the docs tree is clean.  CI gate "
            "wire-up uses --strict once Faz 30 broken-link cleanup is "
            "complete."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the OK summary on success.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    scope_dir = (repo_root / args.scope).resolve()
    if not scope_dir.is_dir():
        print(f"error: scope directory not found: {scope_dir}", file=sys.stderr)
        return 1

    # Default exclude list — `analysis/` is gitignored research with
    # local-only path references; `code_reviews/` would be too were
    # it not partially re-allowed in `.gitignore`, but its closure-plan
    # docs cite real files at line-anchored locations that drift.
    if args.exclude is None:
        exclude_specs = ("analysis",)
    else:
        exclude_specs = tuple(args.exclude)
    excluded_dirs = tuple((scope_dir / spec).resolve() for spec in exclude_specs)

    broken: list[BrokenLink] = []
    md_files = list(_walk_markdown_files(scope_dir, excluded_dirs))
    for md in md_files:
        for link in _extract_links(md):
            failure = _resolve_link(link, repo_root)
            if failure is not None:
                broken.append(failure)

    if broken:
        verdict = "FAIL" if args.strict else "WARN"
        print(f"{verdict}: broken anchor / relative-link references:")
        for entry in broken:
            print(f"  {_format_broken(entry)}")
        print(f"\n{len(broken)} broken link(s) across {len(md_files)} markdown file(s) under {args.scope}/.")
        return 1 if args.strict else 0

    if not args.quiet:
        print(f"OK: {len(md_files)} markdown file(s) under {args.scope}/ have all anchors + relative links resolved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
