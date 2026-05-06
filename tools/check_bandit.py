#!/usr/bin/env python3
"""Wave 4 / Faz 23 — `bandit` JSON output severity gate.

Reads the JSON report produced by ``bandit -f json`` and applies
ForgeLM's severity policy:

- ``HIGH`` issues exit 1 (fail CI / nightly).
- ``MEDIUM`` issues emit a ``::warning::`` GitHub annotation but do
  not fail.
- ``LOW`` issues are silent.

Used in ``.github/workflows/ci.yml`` (every PR) and
``.github/workflows/nightly.yml`` (daily) after the ``bandit`` step.

Exit codes (per ``tools/`` contract — NOT the public 0/1/2/3/4 surface
that ``forgelm/`` honours):

- ``0`` — no high-severity issues (medium/low may be present + warned).
- ``1`` — at least one high-severity issue OR the input file is
  missing / unparseable.

Usage::

    bandit -c pyproject.toml -r forgelm/ -f json -o /tmp/bandit.json || true
    python3 tools/check_bandit.py /tmp/bandit.json

Standards-side note: this helper exists to satisfy the ``|| true`` carve-out
in ``docs/standards/testing.md`` (CI bypass discipline).  The bash
``bandit ... -o out.json || true`` step that calls into us is sanctioned
ONLY because this helper enforces a severity-tiered (B-issue HIGH) gate
on the captured output — without it, the ``|| true`` would silently
swallow real SAST findings.  Removing this helper or replacing it with
``bandit`` directly would break the contract; see the ``|| true``
discipline section of ``testing.md`` before touching either side.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# bandit's severity vocabulary is HIGH / MEDIUM / LOW (UNDEFINED for
# rules that don't carry severity metadata).  Confidence is reported
# separately and not used for gating — operators reviewing warnings
# can read it from the artefact.
_HIGH = "HIGH"
_MED = "MEDIUM"
_UNDEFINED = "UNDEFINED"


def _format_issue(issue: dict[str, Any]) -> str:
    test_id = issue.get("test_id") or "B???"
    test_name = issue.get("test_name") or "<unknown-test>"
    filename = issue.get("filename") or "<unknown>"
    line = issue.get("line_number") or "?"
    severity = (issue.get("issue_severity") or _UNDEFINED).upper()
    confidence = (issue.get("issue_confidence") or _UNDEFINED).upper()
    text = (issue.get("issue_text") or "").splitlines()[0] if issue.get("issue_text") else ""
    return f"[{severity}/{confidence}] {filename}:{line} {test_id} {test_name} — {text}"


def _load_report(report_path: Path) -> dict[str, Any] | int:
    """Read + parse the bandit JSON report; return the dict or an exit code."""
    try:
        raw = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::bandit report not readable at {report_path}: {exc}", file=sys.stderr)
        return 1
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::bandit report at {report_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1


def _extract_results(report: dict[str, Any]) -> list[Any] | int:
    """Validate the ``results`` field shape; return list or an exit code.

    ``null``-valued ``results`` is rejected explicitly (a missing-key
    report is not the same as an empty-results report — ``or []``
    would conflate them and let a malformed bandit run pass silently).
    """
    if "results" not in report:
        print("::error::bandit report missing 'results' field", file=sys.stderr)
        return 1
    results = report["results"]
    if results is None:
        print("::error::bandit report 'results' is null (malformed)", file=sys.stderr)
        return 1
    if not isinstance(results, list):
        print("::error::bandit report 'results' field is not a list", file=sys.stderr)
        return 1
    return results


def _classify_issues(results: list[Any]) -> tuple[list[str], list[str], int]:
    """Bucket issues into (high-lines, medium-lines, undefined-count).

    ``_format_issue`` is only called for the HIGH / MEDIUM branches —
    LOW is silent and UNDEFINED surfaces as a single summary count, so
    formatting LOW / UNDEFINED issues per-finding would be wasted work.
    """
    high: list[str] = []
    medium: list[str] = []
    undefined_count = 0
    for issue in results:
        if not isinstance(issue, dict):
            continue
        severity = (issue.get("issue_severity") or _UNDEFINED).upper()
        if severity == _HIGH:
            high.append(_format_issue(issue))
        elif severity == _MED:
            medium.append(_format_issue(issue))
        elif severity == _UNDEFINED:
            undefined_count += 1
        # LOW is silent; the raw JSON remains in artefacts.
    return high, medium, undefined_count


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <bandit.json>", file=sys.stderr)
        return 1

    report_path = Path(argv[1])
    report_or_code = _load_report(report_path)
    if isinstance(report_or_code, int):
        return report_or_code
    results_or_code = _extract_results(report_or_code)
    if isinstance(results_or_code, int):
        return results_or_code

    high, medium, undefined_count = _classify_issues(results_or_code)

    for line in medium:
        print(f"::warning::bandit {line}")

    if undefined_count:
        # One summary annotation rather than per-finding spam; UNDEFINED
        # rules are bandit's "rule lacks severity metadata" fall-through
        # and merit operator review without burying real signal.  Includes
        # the artefact path so an SRE on the GitHub Actions run summary
        # can grep without walking the workflow YAML (F-W4FU-PS-05
        # absorption).
        print(
            f"::warning::bandit {undefined_count} issue(s) with UNDEFINED "
            f"severity in {report_path}; review the raw report manually."
        )

    if high:
        for line in high:
            print(f"::error::bandit {line}")
        print(f"::error::bandit found {len(high)} high-severity issue(s); failing the run.")
        return 1

    if medium:
        print(f"bandit: {len(medium)} medium-severity issue(s) (warning only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
