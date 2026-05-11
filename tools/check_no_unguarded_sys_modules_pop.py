"""CI guard — bare ``sys.modules.pop("torch"/"numpy"/...)`` is forbidden.

Round-3 of the v0.5.7 review absorption traced 35 spurious full-suite test
failures to three call sites that popped ``torch`` or ``numpy`` from
``sys.modules`` without restoring them — the next ``import torch`` then
half-loaded the module (``torch._C`` never re-bound) and every downstream
``from trl import SFTConfig`` failed with ``NameError: name '_C' is not
defined``.  The fix swapped all three for ``monkeypatch.delitem``, which
auto-restores on test teardown.

This guard exists so a future test author who didn't read those inline
comments can't silently re-introduce the bug.  Failure modes the guard
flags:

- ``sys.modules.pop("torch")`` / ``sys.modules.pop("numpy")``
- ``del sys.modules["torch"]`` / ``del sys.modules["numpy"]``
- The same for ``trl``, ``transformers`` — heavyweight ML modules that
  load C extensions and degrade similarly under partial re-import.

What the guard does NOT flag:

- ``monkeypatch.delitem(sys.modules, "torch")`` — the sanctioned pattern.
- ``patch.dict(sys.modules, {"torch": fake_torch})`` — ``patch.dict``
  restores on context exit; safe.
- Production ``sys.modules`` writes (none today; production code never
  needs to evict a module).

Run via::

    python3 tools/check_no_unguarded_sys_modules_pop.py

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface):

- ``0`` — clean
- ``1`` — at least one unguarded site found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Modules whose unguarded eviction has been shown to corrupt the pytest
# session.  Add to this set only when a new offender is empirically
# observed — keeping the list narrow avoids flagging fixture code that
# legitimately evicts a Python-pure helper module.
_GUARDED_MODULES = ("torch", "numpy", "trl", "transformers", "peft", "datasets")

_PATTERNS = [
    # ``sys.modules.pop("torch", ...)`` / single quotes / no default
    re.compile(r"""sys\.modules\.pop\s*\(\s*['"](""" + "|".join(_GUARDED_MODULES) + r""")['"]"""),
    # ``del sys.modules["torch"]`` / single quotes
    re.compile(r"""del\s+sys\.modules\s*\[\s*['"](""" + "|".join(_GUARDED_MODULES) + r""")['"]\s*\]"""),
    # ``sys.modules["torch"] = None`` — equivalent corruption
    re.compile(r"""sys\.modules\s*\[\s*['"](""" + "|".join(_GUARDED_MODULES) + r""")['"]\s*\]\s*=\s*None"""),
]

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _scan_file(path: Path) -> List[Tuple[int, str, str]]:
    """Return ``(line_number, matched_module, raw_line)`` for every hit."""
    findings: List[Tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Allow the guard itself + the comment-only references in tests
        # that document WHY they don't use the pattern.  We detect those
        # by looking for the sanctioned ``monkeypatch.delitem`` call
        # within the same line (the canonical fix) or by scoping to
        # non-comment / non-docstring lines via a coarse heuristic:
        # skip lines that lead with ``#`` after stripping whitespace.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for pattern in _PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append((line_no, match.group(1), line.rstrip()))
    return findings


def _candidate_files() -> List[Path]:
    """Every ``.py`` file under tests/ + forgelm/, plus self-exclusion."""
    roots = [_REPO_ROOT / "tests", _REPO_ROOT / "forgelm"]
    files: List[Path] = []
    self_path = Path(__file__).resolve()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() == self_path:
                continue
            files.append(path)
    return files


def main() -> int:
    all_findings: List[Tuple[Path, int, str, str]] = []
    for path in _candidate_files():
        for line_no, mod, raw in _scan_file(path):
            all_findings.append((path, line_no, mod, raw))

    if not all_findings:
        scanned = len(_candidate_files())
        print(
            f"OK: {scanned} Python file(s) under tests/ + forgelm/ carry no unguarded "
            f"sys.modules eviction for any of: {', '.join(_GUARDED_MODULES)}."
        )
        return 0

    print("FAIL: unguarded sys.modules eviction found — use monkeypatch.delitem instead.\n")
    for path, line_no, mod, raw in all_findings:
        rel = path.relative_to(_REPO_ROOT)
        print(f"  {rel}:{line_no}  (module: {mod})")
        print(f"    > {raw.strip()}")
    print(
        "\nThe v0.5.7 round-3 review absorption traced 35 unrelated test failures to "
        "this exact pattern (torch._C unbound after partial re-import). Replace with:\n"
        '    monkeypatch.delitem(sys.modules, "<module>", raising=False)\n'
        "which auto-restores on test teardown."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
