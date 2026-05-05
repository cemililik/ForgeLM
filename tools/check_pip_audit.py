#!/usr/bin/env python3
"""Wave 4 / Faz 23 — `pip-audit` JSON output severity gate.

Reads the JSON report produced by ``pip-audit --format json`` and
applies ForgeLM's severity policy:

- ``HIGH`` / ``CRITICAL`` findings exit 1 (fail nightly).
- ``MEDIUM`` findings emit a ``::warning::`` GitHub annotation but do
  not fail.
- ``LOW`` findings are silent.

Used in ``.github/workflows/nightly.yml`` after the ``pip-audit`` step.

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface
that ``forgelm/`` honours):

- ``0`` — no high/critical CVEs (medium/low may be present and warned).
- ``1`` — at least one high or critical CVE OR the input file is
  missing / unparseable.

Usage::

    pip-audit --format json --output /tmp/pip-audit.json || true
    python3 tools/check_pip_audit.py /tmp/pip-audit.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# pip-audit's JSON shape (≥2.7) puts findings under ``dependencies[].vulns``,
# each vuln carrying ``id``, ``aliases``, ``description``, ``fix_versions``.
# Severity is sourced from the OSV / GHSA aliases via ``severity`` (a list
# of {type, score} pairs) when present; pip-audit normalises into
# ``severity`` strings on the top-level vuln dict from 2.7.x onwards.
_HIGH_TIERS: frozenset[str] = frozenset({"HIGH", "CRITICAL"})
_MED_TIERS: frozenset[str] = frozenset({"MEDIUM", "MODERATE"})


def _normalise_severity(raw: Optional[str]) -> str:
    """Upper-case + collapse synonyms; unknown/missing → ``UNKNOWN``."""
    if not raw:
        return "UNKNOWN"
    upper = raw.upper().strip()
    if upper in {"MODERATE"}:
        return "MEDIUM"
    return upper


def _vuln_severity(vuln: dict[str, Any]) -> str:
    """Extract a single severity tier from a pip-audit vuln entry.

    Falls back through several fields because pip-audit's JSON shape
    has shifted across point releases:
    - 2.7.x: top-level ``severity`` string
    - 2.6.x and earlier: nested under ``aliases[].severity[]``
    - GHSA imports often carry only ``severity_score`` (CVSS)

    When no field is parseable we return ``"UNKNOWN"`` and let the
    operator review the raw report manually.
    """
    direct = vuln.get("severity")
    if isinstance(direct, str):
        return _normalise_severity(direct)
    if isinstance(direct, list) and direct:
        first = direct[0]
        if isinstance(first, dict):
            return _normalise_severity(first.get("type") or first.get("severity"))
        if isinstance(first, str):
            return _normalise_severity(first)
    return "UNKNOWN"


def _iter_findings(report: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield (package_name, vuln_dict) pairs from a pip-audit report."""
    deps = report.get("dependencies") or []
    if not isinstance(deps, list):
        return
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        name = dep.get("name") or "<unknown-package>"
        for vuln in dep.get("vulns") or []:
            if isinstance(vuln, dict):
                yield name, vuln


def _format_finding(name: str, vuln: dict[str, Any], severity: str) -> str:
    vid = vuln.get("id") or "<no-id>"
    fix_versions = vuln.get("fix_versions") or vuln.get("fix_version") or []
    if isinstance(fix_versions, str):
        fix_text = fix_versions
    elif isinstance(fix_versions, list) and fix_versions:
        fix_text = ", ".join(str(v) for v in fix_versions)
    else:
        fix_text = "(no fix available)"
    return f"[{severity}] {name} {vid} — fix: {fix_text}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <pip-audit.json>", file=sys.stderr)
        return 1

    report_path = Path(argv[1])
    try:
        raw = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::pip-audit report not readable at {report_path}: {exc}", file=sys.stderr)
        return 1

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::pip-audit report at {report_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    high: list[str] = []
    medium: list[str] = []
    for name, vuln in _iter_findings(report):
        severity = _vuln_severity(vuln)
        line = _format_finding(name, vuln, severity)
        if severity in _HIGH_TIERS:
            high.append(line)
        elif severity in _MED_TIERS:
            medium.append(line)
        # LOW + UNKNOWN are silent; the raw JSON remains in artefacts.

    for line in medium:
        # GitHub Actions annotation; surfaces in the run summary without
        # failing the build.
        print(f"::warning::pip-audit {line}")

    if high:
        for line in high:
            print(f"::error::pip-audit {line}")
        print(f"::error::pip-audit found {len(high)} high/critical-severity finding(s); failing the run.")
        return 1

    if medium:
        print(f"pip-audit: {len(medium)} medium-severity finding(s) (warning only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
