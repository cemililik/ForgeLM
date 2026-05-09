"""CI guard — public-tree files must not reference gitignored working-memory.

Scans every file under the project's public tree (forgelm/, docs/ excluding
the gitignored directories themselves, tests/, tools/, site/, plus the
top-level README.md / CHANGELOG.md / CLAUDE.md / CONTRIBUTING.md) and
fails the run when it finds a citation or hyperlink into ``docs/marketing/``
or ``docs/analysis/``.

The rationale lives in ``docs/standards/documentation.md`` ("Working-memory
directories"): those two directories are operator-local research and
audit notes that never appear in fresh clones, so any reference rots
into a 404 the moment the maintainer touches it.

Path-string exemptions
----------------------
Production code (e.g. ``_SKIP_PATH_FRAGMENTS`` in
``tools/check_yaml_snippets.py``) names ``docs/analysis/`` as a directory
filter — that is the OPPOSITE of a content reference, it tells the linter
to descend AROUND those paths.  The exemption list below carries those
known-correct uses.  Add to it only with a written justification in the
comment block immediately above the entry.

Run via::

    python tools/check_no_analysis_refs.py

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface
that ``forgelm/`` honours):

- ``0`` — clean
- ``1`` — at least one prohibited reference found
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Pattern matches any reference to ``docs/analysis/`` or
# ``docs/marketing/`` inside Markdown links, code-quoted strings, plain
# prose, or ``analysis/`` / ``marketing/`` relative paths from inside
# ``docs/``.  The leading word boundary keeps us from matching
# ``docs-analysis-…`` style identifiers.
_PROHIBITED_RE = re.compile(
    r"(?:(?<!/)docs/(analysis|marketing)/|(?<![A-Za-z./])(analysis|marketing)/(?:code_reviews|QKV-Core|Trion|ART|autoresearch|proposals|strategy|drafts)/)",
)

# Files under the public tree to scan.  Gitignored directories
# (docs/marketing/, docs/analysis/) are excluded by construction since
# git ls-files won't list them.  The site/ and tools/ directories are
# scanned in full.
_PUBLIC_GLOBS: Tuple[str, ...] = (
    "*.md",
    "forgelm/**/*.py",
    "docs/**/*.md",
    "tests/**/*.py",
    "tools/**/*.py",
    "site/**/*.html",
    "site/**/*.js",
    "site/**/*.css",
    "site/**/*.md",
    ".claude/**/*.md",
)

# Files where a path-string match is INTENTIONAL (functional path filter
# or documented policy statement), not a content reference.  The
# guard skips lines listed here verbatim.
#
# Format: ``{relative_path: frozenset_of_substrings_that_legitimise_the_match}``
# When a flagged line on *relative_path* contains ANY of the substrings,
# the finding is suppressed.  Keep the substring as specific as possible
# to avoid hiding real regressions.
_EXEMPT: dict[str, frozenset[str]] = {
    # The gitignore itself names the paths it ignores.
    ".gitignore": frozenset({"docs/marketing/", "docs/analysis/"}),
    # CLAUDE.md carries the policy statement that names the directories.
    "CLAUDE.md": frozenset({"docs/marketing/", "docs/analysis/"}),
    # The standards file IS the rule about these directories.
    "docs/standards/documentation.md": frozenset({"docs/marketing/", "docs/analysis/"}),
    # Localization standard names docs/marketing as a mixed-language
    # exception in the bilingual policy table.
    "docs/standards/localization.md": frozenset({"docs/marketing/"}),
    # The skill that warns away from these dirs needs to name them.
    ".claude/skills/sync-bilingual-docs/SKILL.md": frozenset({"docs/marketing/", "docs/analysis/"}),
    # Production code path filters (functional, not citations).
    "tools/check_anchor_resolution.py": frozenset({'"analysis"', "analysis/"}),
    "tools/check_yaml_snippets.py": frozenset(
        {'"docs/analysis/"', '"docs/marketing/"', "docs/analysis/", "docs/marketing/"}
    ),
    "tests/test_check_bilingual_parity.py": frozenset({"docs/marketing/", "docs/analysis/"}),
    # This guard itself contains the prohibited substrings as patterns.
    "tools/check_no_analysis_refs.py": frozenset({"docs/marketing/", "docs/analysis/"}),
    # Roadmap pages publicly disclose the EXISTENCE of the gitignored
    # marketing directory ("internal only"); that's a policy mention,
    # not a content citation, and the explicit "(gitignored)" suffix
    # marks it as such.
    "docs/roadmap.md": frozenset({"`docs/marketing/`"}),
    "docs/roadmap-tr.md": frozenset({"`docs/marketing/`"}),
}


def _enumerate_public_files() -> List[Path]:
    """Return git-tracked files matching the public-tree globs.

    Using ``git ls-files`` (instead of ``Path.glob``) is essential
    here: the gitignored ``docs/marketing/`` and ``docs/analysis/``
    directories STILL exist on the maintainer's disk, but they're
    untracked.  ``git ls-files`` enumerates only tracked files, so
    we naturally skip the working-memory tree without an explicit
    exclude clause.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: outside a git checkout, scan everything via glob.
        # The gitignored dirs may surface as findings; that's the
        # correct behaviour outside git context (no ground truth).
        files: List[Path] = []
        for pat in _PUBLIC_GLOBS:
            for p in _REPO_ROOT.glob(pat):
                if p.is_file():
                    files.append(p)
        return sorted(set(files))
    tracked: List[Path] = []
    suffixes = (".md", ".py", ".html", ".js", ".css")
    for line in result.stdout.splitlines():
        if not line.endswith(suffixes):
            continue
        candidate = _REPO_ROOT / line
        if candidate.is_file():
            tracked.append(candidate)
    return sorted(tracked)


def _check_file(path: Path) -> List[Tuple[int, str]]:
    """Return list of ``(line_no, line_text)`` for prohibited refs in *path*."""
    rel = path.relative_to(_REPO_ROOT).as_posix()
    exempt_substrings = _EXEMPT.get(rel, frozenset())
    findings: List[Tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not _PROHIBITED_RE.search(line):
            continue
        if any(needle in line for needle in exempt_substrings):
            continue
        findings.append((line_no, line.rstrip()))
    return findings


def main() -> int:
    total = 0
    for path in _enumerate_public_files():
        findings = _check_file(path)
        if not findings:
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for line_no, line_text in findings:
            print(f"  ✗ {rel}:{line_no}  {line_text[:200]}")
            total += 1
    if total:
        print(
            f"\n{total} prohibited reference(s) into gitignored working-memory directories.\n"
            "Fix: rewrite the surrounding text to NOT cite docs/marketing/ or docs/analysis/.\n"
            "If the reference is a functional path filter (not a content citation), add the\n"
            "file path to ``_EXEMPT`` in tools/check_no_analysis_refs.py with a written\n"
            "justification.  See docs/standards/documentation.md ('Working-memory directories')."
        )
        return 1
    print("OK: no public-tree references into docs/marketing/ or docs/analysis/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
