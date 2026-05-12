#!/usr/bin/env python3
"""Site version sync — derive the marketing site's displayed version
from the canonical CHANGELOG release header.

The marketing surface under ``site/`` advertises the *latest released*
ForgeLM version in three places (hero badge, JSON-LD ``softwareVersion``,
``pip install`` snippets).  Pre-this-tool every release required hand-
editing 15+ literals across 7 HTML files + 6 i18n locales — drift
inevitably leaked in (the v0.5.5 → v0.6.0 cycle shipped with the badge
still reading ``v0.5.5``).

Source of truth
---------------
``CHANGELOG.md``'s most recent released section header
(``## [X.Y.Z] — YYYY-MM-DD``, skipping ``[Unreleased]``).  We use the
CHANGELOG rather than ``pyproject.toml`` because pyproject sits on a
``X.Y.ZrcN`` pre-release marker during the dev cycle that precedes the
next release; the site should advertise the *previous* release in that
window, not an rc.

Surfaces rewritten
------------------
* ``site/*.html`` JSON-LD ``"softwareVersion": "X.Y.Z"`` blocks.
* ``site/index.html`` hero-badge fallback text
  (``Open source · Apache 2.0 · vX.Y.Z``).
* ``site/quickstart.html`` ``pip install`` snippets
  (``forgelm==X.Y.Z`` + the three extras-variant lines).
* ``site/js/translations.js`` ``"home.hero.badge"`` entries across
  every locale (currently en / tr / de / fr / es / zh).

Modes
-----
* No flag → rewrite in place; print one line per file touched and the
  total substitution count.  Exits 0.
* ``--check`` → dry-run; print a diff-style summary and exit 1 if any
  file would change.  Wired into the repo gauntlet so the next release
  cycle cannot ship with a stale badge.

The generator is intentionally pattern-anchored (not a global
``s/oldver/newver/g``) so that historical version mentions inside
free-form prose (e.g. ``"v0.5.0 introduced X"`` in a changelog
embed) are not collaterally rewritten.  Each pattern carries a
contextual prefix that pins it to a current-version surface.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
SITE = REPO_ROOT / "site"

# ---------------------------------------------------------------------------
# CHANGELOG → latest released version
# ---------------------------------------------------------------------------

# Matches ``## [X.Y.Z] — YYYY-MM-DD`` (Keep-a-Changelog header for a
# released section).  Skips ``## [Unreleased]`` by requiring a numeric
# version inside the brackets.
_RELEASED_HEADER = re.compile(r"^##\s+\[(\d+\.\d+\.\d+)\]\s+—\s+\d{4}-\d{2}-\d{2}\s*$", re.MULTILINE)


def latest_released_version() -> str:
    """Return the most recent released version listed in CHANGELOG.md.

    Order in CHANGELOG is most-recent-first by the project's convention
    (Keep-a-Changelog).  We trust the first match rather than parsing all
    headers + sorting, because the cut-release skill adds new headers at
    the top.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    m = _RELEASED_HEADER.search(text)
    if not m:
        raise RuntimeError(f"{CHANGELOG.name}: no '## [X.Y.Z] — YYYY-MM-DD' header found.")
    return m.group(1)


# ---------------------------------------------------------------------------
# Site rewrite rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rewrite:
    """A single anchored substitution to apply across one or more files."""

    label: str
    pattern: re.Pattern[str]
    template: str  # uses ``{version}`` placeholder

    def apply(self, text: str, version: str) -> tuple[str, int]:
        replacement = self.template.format(version=version)
        new_text, n = self.pattern.subn(replacement, text)
        return new_text, n


# JSON-LD ``"softwareVersion": "X.Y.Z"`` inside a SoftwareApplication
# structured-data block.  The leading ``softwareVersion":`` anchor keeps
# the substitution scoped to JSON-LD; unrelated literal versions inside
# prose are not touched.
RW_JSONLD_SOFTWARE_VERSION = Rewrite(
    label='JSON-LD "softwareVersion"',
    pattern=re.compile(r'("softwareVersion"\s*:\s*")(\d+\.\d+\.\d+)(")'),
    template=r"\g<1>{version}\g<3>",
)

# Hero-badge fallback inside the HTML body — the visible literal that
# i18n.js replaces at runtime when JavaScript is enabled, but which
# SEO crawlers + no-JS visitors see.
RW_HERO_BADGE_HTML = Rewrite(
    label="hero badge HTML fallback",
    pattern=re.compile(r"(Open source\s*·\s*Apache 2\.0\s*·\s*v)\d+\.\d+\.\d+"),
    template=r"\g<1>{version}",
)

# Localised hero-badge strings in translations.js.  Multilingual prefixes
# all converge on ``· Apache 2.0 · vX.Y.Z`` — anchor on that tail so we
# don't need a per-locale rule.
RW_HERO_BADGE_I18N = Rewrite(
    label="hero badge i18n (translations.js)",
    pattern=re.compile(r"(·\s*Apache 2\.0\s*·\s*v)\d+\.\d+\.\d+"),
    template=r"\g<1>{version}",
)

# ``pip install forgelm==X.Y.Z`` and the extras variants in quickstart.html.
# The ``forgelm`` package-name anchor scopes the substitution.
RW_PIP_INSTALL = Rewrite(
    label="pip install pin",
    pattern=re.compile(r"(forgelm(?:\[[a-z-]+\])?==)(\d+\.\d+\.\d+)"),
    template=r"\g<1>{version}",
)


HTML_RULES: list[Rewrite] = [
    RW_JSONLD_SOFTWARE_VERSION,
    RW_HERO_BADGE_HTML,
    RW_PIP_INSTALL,
]

JS_RULES: list[Rewrite] = [
    RW_HERO_BADGE_I18N,
]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class FileResult:
    path: Path
    substitutions: dict[str, int]
    new_text: str
    old_text: str

    @property
    def touched(self) -> bool:
        return any(self.substitutions.values()) and self.new_text != self.old_text


def _process(path: Path, rules: list[Rewrite], version: str) -> FileResult:
    old = path.read_text(encoding="utf-8")
    text = old
    counts: dict[str, int] = {}
    for rule in rules:
        text, n = rule.apply(text, version)
        if n:
            counts[rule.label] = n
    return FileResult(path=path, substitutions=counts, new_text=text, old_text=old)


def collect_results(version: str) -> list[FileResult]:
    results: list[FileResult] = []
    for html in sorted(SITE.glob("*.html")):
        results.append(_process(html, HTML_RULES, version))
    translations = SITE / "js" / "translations.js"
    if translations.exists():
        results.append(_process(translations, JS_RULES, version))
    return results


def _summarise(results: list[FileResult]) -> tuple[int, int]:
    total_files = sum(1 for r in results if r.touched)
    total_subs = sum(sum(r.substitutions.values()) for r in results if r.touched)
    return total_files, total_subs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run; exit 1 if any file would be rewritten.",
    )
    args = parser.parse_args(argv)

    version = latest_released_version()
    results = collect_results(version)
    files, subs = _summarise(results)

    if args.check:
        if files == 0:
            print(f"OK: site/ version literals match CHANGELOG latest release ({version}).")
            return 0
        print(f"DRIFT: site/ references stale versions; CHANGELOG latest is {version}.")
        for r in results:
            if not r.touched:
                continue
            detail = ", ".join(f"{label}×{n}" for label, n in r.substitutions.items())
            print(f"  {r.path.relative_to(REPO_ROOT)} — would rewrite: {detail}")
        print("Fix: python3 tools/update_site_version.py")
        return 1

    if files == 0:
        print(f"OK: site/ version literals already at {version}; no rewrite needed.")
        return 0

    for r in results:
        if not r.touched:
            continue
        r.path.write_text(r.new_text, encoding="utf-8")
        detail = ", ".join(f"{label}×{n}" for label, n in r.substitutions.items())
        print(f"wrote {r.path.relative_to(REPO_ROOT)} — {detail}")
    print(f"Rewrote {files} file(s), {subs} substitution(s), target version {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
