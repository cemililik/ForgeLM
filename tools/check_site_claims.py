#!/usr/bin/env python3
"""Site-as-tested-surface CI guard for ForgeLM.

The marketing site under ``site/`` makes concrete claims about ForgeLM's
behaviour — artefact filenames, quickstart templates, GPU profile counts,
the current PyPI version. When the underlying Python code drifts (a file is
renamed, a template is added or removed, a GPU is added to the pricing
table) those site claims silently rot. This script diffs the site against
the Python sources of truth so reviewers and CI catch the drift.

Sources of truth
----------------
* ``forgelm/compliance.py::export_compliance_artifacts`` — the artefact
  filenames it writes for every successful run.
* ``forgelm/quickstart.py::TEMPLATES`` — the canonical template registry.
* ``forgelm/trainer.py::ForgeTrainer._GPU_PRICING`` — the GPU profile count
  the home page advertises.
* ``pyproject.toml [project] version`` — the version mentioned in the hero
  badge / release lines on the site.

Behaviour
---------
* Default mode: print one line per check (``OK`` or ``MISMATCH:``) and exit
  ``0`` regardless. Useful for local inspection.
* ``--strict``: exit ``1`` on any mismatch. Wired into ``ci.yml`` so a
  drifted site fails the build.

Parsing rules (rule #2 of docs/standards/regex.md):
    * Site HTML is parsed with simple ``in`` / regex on the rendered text —
      the structural claims we check are stable substrings, not nested
      tags.
    * Python is parsed with :mod:`ast` — never with regex — so renames and
      decorator changes in the source modules don't fool the guard.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
FORGELM = REPO_ROOT / "forgelm"
PYPROJECT = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _module_ast(path: Path) -> ast.Module:
    """Parse a Python source file and return its AST module node."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_function(module: ast.Module, name: str) -> ast.FunctionDef | None:
    """Return the top-level ``def name`` node, or None if absent."""
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _find_class(module: ast.Module, name: str) -> ast.ClassDef | None:
    """Return the top-level ``class name`` node, or None if absent."""
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_assignment(scope: Iterable[ast.stmt], name: str) -> ast.AST | None:  # NOSONAR
    """Return the value AST of ``name = …`` inside *scope*, or None."""
    for node in scope:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return node.value
    return None


def _string_literals_from_function(fn: ast.FunctionDef) -> list[str]:  # NOSONAR
    """Walk a function body and return every string literal found in
    ``os.path.join(output_dir, "<filename>")`` calls — the convention
    :func:`forgelm.compliance.export_compliance_artifacts` follows.

    Pure AST walk; no regex.
    """
    found: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        # Only consider os.path.join(...) calls.
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "join":
            owner = func.value
            if (
                isinstance(owner, ast.Attribute)
                and owner.attr == "path"
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "os"
            ):
                # The trailing constant string in the join call is the artefact
                # filename; ignore directory-only joins.
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if "/" not in arg.value and arg.value.endswith((".json", ".yaml", ".jsonl", ".md")):
                            found.append(arg.value)
    return found


def _dict_keys_from_assignment(value: ast.AST) -> list[str]:
    """Return the string keys of an ``ast.Dict`` literal, or [] otherwise."""
    if not isinstance(value, ast.Dict):
        return []
    keys: list[str] = []
    for k in value.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
    return keys


# ---------------------------------------------------------------------------
# Source-of-truth extractors
# ---------------------------------------------------------------------------


def compliance_artifact_filenames() -> set[str]:
    """Filenames that :func:`export_compliance_artifacts` writes."""
    module = _module_ast(FORGELM / "compliance.py")
    fn = _find_function(module, "export_compliance_artifacts")
    if fn is None:
        raise RuntimeError(
            "forgelm/compliance.py::export_compliance_artifacts not found — "
            "rename or refactor the function and update this guard together."
        )
    return set(_string_literals_from_function(fn))


def quickstart_template_names() -> set[str]:
    """Template handles registered in :data:`forgelm.quickstart.TEMPLATES`."""
    module = _module_ast(FORGELM / "quickstart.py")
    value = _find_assignment(module.body, "TEMPLATES")
    if value is None:
        raise RuntimeError(
            "forgelm/quickstart.py::TEMPLATES not found — rename or refactor "
            "the registry and update this guard together."
        )
    keys = _dict_keys_from_assignment(value)
    if not keys:
        raise RuntimeError("forgelm/quickstart.py::TEMPLATES has no string keys.")
    return set(keys)


def gpu_pricing_count() -> int:
    """Number of GPU profiles in :class:`ForgeTrainer._GPU_PRICING`."""
    module = _module_ast(FORGELM / "trainer.py")
    cls = _find_class(module, "ForgeTrainer")
    if cls is None:
        raise RuntimeError(
            "forgelm/trainer.py::ForgeTrainer not found — rename or refactor the class and update this guard together."
        )
    value = _find_assignment(cls.body, "_GPU_PRICING")
    if value is None or not isinstance(value, ast.Dict):
        raise RuntimeError("forgelm/trainer.py::ForgeTrainer._GPU_PRICING dict literal not found.")
    return len(value.keys)


_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def pyproject_version() -> str:
    """Return the ``[project] version`` declared in pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    in_project_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project_section = stripped == "[project]"
            continue
        if in_project_section:
            m = _VERSION_LINE.match(line)
            if m:
                return m.group(1)
    raise RuntimeError("pyproject.toml: [project] version not found.")


# ---------------------------------------------------------------------------
# Site readers
# ---------------------------------------------------------------------------


def _read_site(path: str) -> str:
    return (SITE / path).read_text(encoding="utf-8")


_HTML_TAG = re.compile(r"<[^>]+>")
_FILENAME_RE = re.compile(r"\b\w+\.(?:json|yaml|jsonl|md)\b", re.ASCII)

_CHECK_GPU_PROFILE_COUNT = "GPU profile count"
_CHECK_PYPI_VERSION = "PyPI version mention"


def site_artifact_filenames() -> set[str]:
    """Artefact filenames mentioned on ``site/compliance.html``.

    We strip HTML tags first so attribute values inside ``<b>`` or ``<span>``
    don't confuse the filename regex.
    """
    text = _read_site("compliance.html")
    cleaned = _HTML_TAG.sub(" ", text)
    return set(_FILENAME_RE.findall(cleaned))


def site_template_names() -> set[str]:
    """Template names mentioned on ``site/quickstart.html``.

    Picks any token of the form ``forgelm quickstart <name>`` or whitespace-
    delimited slug-style names that appear in the documented template list.
    """
    text = _read_site("quickstart.html")
    cleaned = _HTML_TAG.sub(" ", text)
    found: set[str] = set()
    # Accept both "forgelm quickstart X" and the per-line "  X   description"
    # form used in the --list output snippet.
    for match in re.finditer(r"forgelm\s+quickstart\s+([a-z][a-z0-9-]+(?:-[a-z0-9]+)*)", cleaned):
        found.add(match.group(1))
    # Add any standalone slug that appears in the snippet body (e.g. the
    # bulleted list of templates in <pre>).
    for match in re.finditer(
        r"^\s+([a-z][a-z0-9-]+-[a-z0-9-]+)\s{2,}", cleaned, flags=re.MULTILINE
    ):  # NOSONAR — applied to controlled static HTML, not user input; ReDoS risk is not exploitable here
        found.add(match.group(1))
    return found


_GPU_COUNT_BLOCK = re.compile(
    r'<div class="stat-value">(\d+)</div>\s*<div class="stat-label" data-i18n="home\.stats\.gpus">'
)


def site_gpu_count() -> int | None:
    """The integer in the ``home.stats.gpus`` stat tile of ``index.html``."""
    text = _read_site("index.html")
    m = _GPU_COUNT_BLOCK.search(text)
    return int(m.group(1)) if m else None


_VERSION_BADGE = re.compile(r"\bv(\d+\.\d+\.\d+(?:[a-z]+\d*)?)\b")


def site_version_mentions() -> set[str]:
    """Versions mentioned anywhere in the ``site/*.html`` pages."""
    found: set[str] = set()
    for html in SITE.glob("*.html"):
        for m in _VERSION_BADGE.finditer(html.read_text(encoding="utf-8")):
            found.add(m.group(1))
    return found


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str = ""
    details: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.ok:
            return f"OK: {self.name} — {self.message}"
        head = f"MISMATCH: {self.name} — {self.message}"
        if self.details:
            return head + "\n  " + "\n  ".join(self.details)
        return head


def check_artifacts() -> CheckResult:
    code = compliance_artifact_filenames()
    site = site_artifact_filenames()
    # The site lists artefacts produced by *several* modules (audit log, model
    # card, etc.); the guard verifies that every artefact emitted by
    # export_compliance_artifacts is mentioned on the page. The reverse is not
    # required because non-compliance artefacts (audit log, model_card.md,
    # data_audit_report.json) come from other functions.
    missing = sorted(code - site)
    if missing:
        return CheckResult(
            "compliance artefacts",
            ok=False,
            message=f"{len(missing)} artefact(s) emitted by code but not listed in site/compliance.html",
            details=missing,
        )
    return CheckResult(
        "compliance artefacts",
        ok=True,
        message=f"all {len(code)} artefact filenames listed",
    )


def check_templates() -> CheckResult:
    code = quickstart_template_names()
    site = site_template_names()
    missing_from_site = sorted(code - site)
    extra_on_site = sorted(site - code)
    if missing_from_site or extra_on_site:
        details = []
        if missing_from_site:
            details.append("only in code: " + ", ".join(missing_from_site))
        if extra_on_site:
            details.append("only on site: " + ", ".join(extra_on_site))
        return CheckResult(
            "quickstart templates",
            ok=False,
            message="set diff between forgelm/quickstart.py::TEMPLATES and site/quickstart.html",
            details=details,
        )
    return CheckResult(
        "quickstart templates",
        ok=True,
        message=f"all {len(code)} templates listed",
    )


def check_gpu_count() -> CheckResult:  # NOSONAR
    code = gpu_pricing_count()
    site = site_gpu_count()
    if site is None:
        return CheckResult(
            _CHECK_GPU_PROFILE_COUNT,
            ok=False,
            message="home.stats.gpus stat tile not found in site/index.html",
        )
    if code != site:
        return CheckResult(
            _CHECK_GPU_PROFILE_COUNT,
            ok=False,
            message=f"site says {site}, _GPU_PRICING has {code}",
        )
    return CheckResult(
        _CHECK_GPU_PROFILE_COUNT,
        ok=True,
        message=f"site and _GPU_PRICING both report {code}",
    )


_VERSION_PARTS = re.compile(r"^(\d+)\.(\d+)\.(\d+)([a-zA-Z]+\d*)?$")


def _version_tuple(v: str) -> tuple[int, int, int, int] | None:
    """Parse ``A.B.C[suffix]`` into a sortable tuple. Suffix yields ``-1``
    so that a pre-release sorts BEFORE the matching public release; absent
    suffix sorts after (treated as the released form)."""
    m = _VERSION_PARTS.match(v)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
    rank = -1 if m.group(4) else 0
    return (a, b, c, rank)


def check_version() -> CheckResult:  # NOSONAR
    code = pyproject_version()
    mentions = site_version_mentions()
    code_t = _version_tuple(code)
    if code_t is None:
        return CheckResult(
            _CHECK_PYPI_VERSION,
            ok=False,
            message=f"pyproject version {code!r} is not parseable as A.B.C[rcN]",
        )
    # Each version mention on the site must be either:
    #   (a) the exact pyproject version, or
    #   (b) the most recent *released* (= no suffix) version <= pyproject.
    # This lets the site display "v0.5.0" while pyproject is on "0.5.1rc1"
    # (next-dev-cycle) without false positives.
    bad: list[str] = []
    for m in mentions:
        m_t = _version_tuple(m)
        if m_t is None:
            bad.append(m)
            continue
        if m == code:
            continue
        # Released versions (rank == 0) <= pyproject are accepted; the
        # latest release lives just below the dev-cycle marker.
        if m_t[3] == 0 and m_t <= code_t:
            continue
        bad.append(m)
    if bad:
        return CheckResult(
            _CHECK_PYPI_VERSION,
            ok=False,
            message=f"pyproject={code}; site mentions inconsistent versions",
            details=sorted(bad),
        )
    shown = sorted(mentions) or ["(no version badges)"]
    return CheckResult(
        _CHECK_PYPI_VERSION,
        ok=True,
        message=f"site mentions {shown} (pyproject={code})",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_checks() -> list[CheckResult]:
    return [
        check_artifacts(),
        check_templates(),
        check_gpu_count(),
        check_version(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on any mismatch (default: warn-only, exit 0).",
    )
    args = parser.parse_args(argv)

    results = run_checks()
    for r in results:
        print(r.render())

    has_mismatch = any(not r.ok for r in results)
    if has_mismatch and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
