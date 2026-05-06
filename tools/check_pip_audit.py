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

- ``0`` — no high/critical CVEs and no UNKNOWN-severity findings
  (medium/low may be present and warned).
- ``1`` — at least one high or critical CVE, OR at least one
  UNKNOWN-severity finding (F-PR29-A7-11: pip-audit's JSON omits
  severity, so UNKNOWN means we cannot prove a vulnerability is
  low-impact; failing closed avoids silent drop), OR the input file is
  missing / unparseable.

Usage::

    pip-audit --format json --output /tmp/pip-audit.json || true
    python3 tools/check_pip_audit.py /tmp/pip-audit.json

Standards-side note: this helper exists to satisfy the ``|| true`` carve-out
in ``docs/standards/testing.md`` (CI bypass discipline).  The bash
``pip-audit --format json > out.json || true`` step that calls into us is
sanctioned ONLY because this helper enforces a severity-tiered (CVE
HIGH / CRITICAL) gate on the captured output — without it, the ``|| true``
would silently swallow real findings.  Removing this helper or replacing
it with ``pip-audit`` directly would break the contract; see the
``|| true`` discipline section of ``testing.md`` before touching either
side.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# pip-audit's JSON shape puts findings under ``dependencies[].vulns``,
# each vuln carrying ``id``, ``aliases``, ``description``, ``fix_versions``.
#
# Empirical note (verified against pip-audit 2.6.0–2.9.0 wheel sources
# during Wave 4 absorption round 2): pip-audit's ``_format/json.py``
# does NOT serialise OSV severity into the JSON output — ``aliases``
# is a flat list of CVE/GHSA identifier strings (per
# ``pip_audit/_service/interface.py``: ``aliases: set[str]``), no
# nested ``severity`` field appears at any nesting level.  This means
# `_vuln_severity` returns ``"UNKNOWN"`` for every vuln in a real
# pip-audit JSON report, and the UNKNOWN summary annotation handles
# the operator-triage path.  We retain the top-level string-severity
# branch to honour the documented CLAUDE.md / pyproject.toml schema
# (operators feeding hand-crafted JSON for non-pip-audit scanners can
# emit a top-level ``severity: "HIGH"`` and have the gate honour it).
_HIGH_TIERS: frozenset[str] = frozenset({"HIGH", "CRITICAL"})
_MED_TIERS: frozenset[str] = frozenset({"MEDIUM", "MODERATE"})


def _normalise_severity(raw: Optional[str]) -> str:
    """Upper-case + collapse synonyms; unknown/missing → ``UNKNOWN``."""
    if not raw:
        return "UNKNOWN"
    upper = raw.upper().strip()
    if upper == "MODERATE":
        return "MEDIUM"
    return upper


def _vuln_severity(vuln: dict[str, Any]) -> str:
    """Extract a single severity tier from a pip-audit vuln entry.

    Honours only the top-level ``severity`` string — pip-audit's JSON
    output never carries severity (verified against 2.6.0–2.9.0 wheel
    sources).  Hand-crafted JSON from non-pip-audit scanners can set
    a top-level ``severity: "HIGH"`` and have the gate honour it.
    Anything else falls through to ``"UNKNOWN"`` and surfaces via the
    UNKNOWN summary annotation in ``main()``.
    """
    direct = vuln.get("severity")
    if isinstance(direct, str):
        return _normalise_severity(direct)
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

    if high:
        for line in high:
            print(f"::error::pip-audit {line}")
        print(f"::error::pip-audit found {len(high)} high/critical-severity finding(s); failing the run.")
        return 1

    if unknown:
        # F-PR29-A7-11 (post-flip policy): UNKNOWN-severity findings now
        # fail the gate.  Rationale: pip-audit's JSON omits OSV severity
        # for almost every real vuln, so the previous "warn only" branch
        # converted nearly all findings into a silent advisory — operators
        # never saw the failures.  Failing closed surfaces every vuln for
        # explicit triage; if a vuln is genuinely low-impact, the operator
        # documents it (e.g. via a pip-audit ignore file or a YAML allow
        # entry) rather than relying on missing severity to skip the gate.
        for line in unknown:
            print(f"::error::pip-audit {line}")
        print(
            f"::error::pip-audit found {len(unknown)} finding(s) without parseable "
            f"severity in {report_path}; pip-audit's JSON does not serialise OSV "
            f"severity, so each must be reviewed manually (failing closed)."
        )
        return 1

    if medium:
        print(f"pip-audit: {len(medium)} medium-severity finding(s) (warning only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
