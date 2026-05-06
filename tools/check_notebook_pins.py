#!/usr/bin/env python3
"""Notebook ``forgelm`` pin guard — keeps tutorial installs in lockstep with the release.

Walks every ``notebooks/*.ipynb`` file, scans each code cell for
``!pip install`` invocations that target the ``forgelm`` distribution,
and asserts the version specifier is ``==<pyproject.version>``. This
catches the failure mode where a release bumps ``pyproject.toml`` but
the colab/jupyter quickstart cells still install the previous patch
version — first-time users would otherwise pull stale wheels.

Recognised forms (extras + flags preserved)::

    !pip install forgelm==0.5.5
    !pip install -q --no-cache-dir 'forgelm[qlora]==0.5.5' bitsandbytes
    !pip install --upgrade "forgelm[ingestion]==0.5.5"

Drift examples (caught)::

    !pip install forgelm                  # no pin
    !pip install forgelm>=0.5.2           # range, not exact
    !pip install 'forgelm[export]==0.5.4' # wrong version

Markdown cells, sibling installs (``!pip install datasets``), and the
``forgelm`` *invocation* lines (``!forgelm --version``) are ignored.

Usage::

    # Advisory (default): exit 0 even on drift; print the report.
    python3 tools/check_notebook_pins.py

    # CI gate: exit 1 when any pin drifts from pyproject.toml.
    python3 tools/check_notebook_pins.py --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# Capture group covers the *whole* requirement spec including extras and
# version pin (no internal whitespace) so we can validate it as one
# token.  Examples that match the inner group:
#   forgelm
#   forgelm==0.5.5
#   forgelm[qlora]==0.5.5
#   forgelm[ingestion-scale]==0.5.5
#   forgelm>=0.5.2
# We deliberately reject embedded whitespace inside the spec so that an
# installed sibling package (e.g. ``forgelm-extras``) does not match.
_PIP_INSTALL_RE = re.compile(
    r"!\s*pip\s+install\b[^\n]*?(?P<spec>(?<![\w-])forgelm(?:\[[^\]]+\])?(?:[<>=!~]=?[^\s'\"]+)?)",
)


@dataclass(frozen=True)
class PinIssue:
    """One ``forgelm`` requirement that drifts from the pyproject pin."""

    notebook: Path
    cell_index: int
    spec: str
    reason: str


def _load_pyproject_version(path: Path = PYPROJECT_PATH) -> str:
    """Return the ``project.version`` string from ``pyproject.toml``."""
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    try:
        return str(data["project"]["version"])
    except KeyError as exc:  # pragma: no cover — malformed pyproject is a build error elsewhere
        raise SystemExit(f"check_notebook_pins: missing project.version in {path}") from exc


def _iter_code_cells(notebook: Path) -> Iterable[tuple[int, str]]:
    """Yield ``(cell_index, joined_source_text)`` for each code cell."""
    with notebook.open("r", encoding="utf-8") as fh:
        nb = json.load(fh)
    for idx, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            text = "".join(src)
        else:
            text = str(src)
        yield idx, text


def _check_notebook(notebook: Path, expected_version: str) -> List[PinIssue]:
    """Return any drift issues found in ``notebook`` against ``expected_version``."""
    issues: List[PinIssue] = []
    expected_pin = f"=={expected_version}"
    for cell_idx, text in _iter_code_cells(notebook):
        for match in _PIP_INSTALL_RE.finditer(text):
            spec = match.group("spec")
            # Strip extras (``forgelm[qlora]``) for the version-pin check.
            base_and_extra, _, version_part = spec.partition("==")
            if "==" not in spec:
                # Either no operator (bare ``forgelm``) or a range/inequality.
                if any(op in spec for op in ("<", ">", "!=", "~=")):
                    reason = f"non-exact specifier (expected '{expected_pin}')"
                else:
                    reason = f"missing version pin (expected '{expected_pin}')"
                issues.append(PinIssue(notebook, cell_idx, spec, reason))
                continue
            if version_part != expected_version:
                reason = f"pin '=={version_part}' does not match pyproject version '{expected_version}'"
                issues.append(PinIssue(notebook, cell_idx, spec, reason))
    return issues


def _collect_notebooks(directory: Path) -> Sequence[Path]:
    return sorted(directory.glob("*.ipynb"))


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify every notebooks/*.ipynb pins forgelm to the pyproject "
            "version. Useful immediately before cutting a release so the "
            "quickstart cells stay in lockstep with the wheel."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when any drift is detected (default: advisory, exit 0).",
    )
    parser.add_argument(
        "--notebooks-dir",
        type=Path,
        default=NOTEBOOKS_DIR,
        help="Directory of notebooks to scan (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    expected = _load_pyproject_version()
    notebooks = _collect_notebooks(args.notebooks_dir)
    if not notebooks:
        print(f"check_notebook_pins: no notebooks under {args.notebooks_dir}")
        return 0

    all_issues: List[PinIssue] = []
    for nb in notebooks:
        all_issues.extend(_check_notebook(nb, expected))

    if not all_issues:
        print(f"check_notebook_pins: OK — {len(notebooks)} notebook(s) all pin forgelm=={expected}")
        return 0

    print(f"check_notebook_pins: {len(all_issues)} drift issue(s) against forgelm=={expected}:")
    for issue in all_issues:
        rel = issue.notebook.relative_to(REPO_ROOT)
        print(f"  - {rel} (cell {issue.cell_index}): {issue.spec!r} — {issue.reason}")

    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
