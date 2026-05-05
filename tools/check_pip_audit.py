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

# OSV severity-list ``type`` values are scoring-system labels, NOT tier
# names — recognising them lets us avoid mistaking the label for a
# severity (otherwise the original CVSS_V3 string would resolve to
# UNKNOWN by chance, but a renamed system would silently mis-tier).
_SCORE_TYPE_LABELS: frozenset[str] = frozenset({"CVSS", "CVSS_V2", "CVSS_V3", "CVSS_V4", "CVSS_V31", "CVSS_V40"})


def _normalise_severity(raw: Optional[str]) -> str:
    """Upper-case + collapse synonyms; unknown/missing → ``UNKNOWN``."""
    if not raw:
        return "UNKNOWN"
    upper = raw.upper().strip()
    if upper in {"MODERATE"}:
        return "MEDIUM"
    if upper in _SCORE_TYPE_LABELS:
        # CVSS_V3 etc. is a scoring-system label, not a tier name.
        return "UNKNOWN"
    return upper


def _tier_from_cvss_score(score: Any) -> str:
    """Map a CVSS base score to a severity tier per FIRST.org guidance.

    CVSS v3 / v4 cut-points: 0.0 NONE · 0.1–3.9 LOW · 4.0–6.9 MEDIUM ·
    7.0–8.9 HIGH · 9.0–10.0 CRITICAL.  Falls back to ``UNKNOWN`` on
    any parse failure rather than guessing.
    """
    if isinstance(score, (int, float)):
        value = float(score)
    elif isinstance(score, str):
        try:
            value = float(score.strip())
        except ValueError:
            return "UNKNOWN"
    else:
        return "UNKNOWN"
    if value >= 9.0:
        return "CRITICAL"
    if value >= 7.0:
        return "HIGH"
    if value >= 4.0:
        return "MEDIUM"
    if value > 0.0:
        return "LOW"
    return "UNKNOWN"


def _severity_from_entry(entry: Any) -> str:
    """Extract a severity tier from a single ``severity[]`` element."""
    if isinstance(entry, dict):
        # Only the ``severity`` field carries a tier label; ``type`` is
        # the scoring-system identifier (CVSS_V3, ...).  Try the tier
        # first, then derive from the CVSS score when only the type +
        # score pair is available.
        explicit = _normalise_severity(entry.get("severity"))
        if explicit != "UNKNOWN":
            return explicit
        return _tier_from_cvss_score(entry.get("score"))
    if isinstance(entry, str):
        return _normalise_severity(entry)
    return "UNKNOWN"


def _vuln_severity(vuln: dict[str, Any]) -> str:
    """Extract a single severity tier from a pip-audit vuln entry.

    Falls back through several fields because pip-audit's JSON shape
    has shifted across point releases:
    - 2.7.x: top-level ``severity`` string
    - 2.7.x list form: top-level ``severity[]`` of ``{type, score}`` /
      ``{severity}`` / plain string entries
    - 2.6.x and earlier: nested under ``aliases[].severity[]``

    When no field is parseable we return ``"UNKNOWN"`` and let the
    caller surface a single summary annotation so the operator can
    review the raw report.
    """
    direct = vuln.get("severity")
    if isinstance(direct, str):
        return _normalise_severity(direct)
    if isinstance(direct, list):
        for entry in direct:
            tier = _severity_from_entry(entry)
            if tier != "UNKNOWN":
                return tier
    # 2.6.x fallback — severity buried inside aliases[].severity[].
    aliases = vuln.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if not isinstance(alias, dict):
                continue
            nested = alias.get("severity")
            if isinstance(nested, list):
                for entry in nested:
                    tier = _severity_from_entry(entry)
                    if tier != "UNKNOWN":
                        return tier
            elif isinstance(nested, str):
                tier = _normalise_severity(nested)
                if tier != "UNKNOWN":
                    return tier
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
    unknown: list[str] = []
    for name, vuln in _iter_findings(report):
        severity = _vuln_severity(vuln)
        line = _format_finding(name, vuln, severity)
        if severity in _HIGH_TIERS:
            high.append(line)
        elif severity in _MED_TIERS:
            medium.append(line)
        elif severity == "UNKNOWN":
            unknown.append(line)
        # LOW is silent; the raw JSON remains in artefacts.

    for line in medium:
        # GitHub Actions annotation; surfaces in the run summary without
        # failing the build.
        print(f"::warning::pip-audit {line}")

    if unknown:
        # One summary annotation rather than per-finding spam — UNKNOWN
        # findings need operator review, not noise that buries real
        # signal (F-W4-PS-07 / F-W4-TR-05 absorption).
        print(
            f"::warning::pip-audit {len(unknown)} finding(s) without parseable "
            "severity; review the raw report manually."
        )

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
