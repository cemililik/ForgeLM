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


def _format_issue(issue: dict[str, Any]) -> str:
    test_id = issue.get("test_id") or "B???"
    test_name = issue.get("test_name") or "<unknown-test>"
    filename = issue.get("filename") or "<unknown>"
    line = issue.get("line_number") or "?"
    severity = (issue.get("issue_severity") or "UNDEFINED").upper()
    confidence = (issue.get("issue_confidence") or "UNDEFINED").upper()
    text = (issue.get("issue_text") or "").splitlines()[0] if issue.get("issue_text") else ""
    return f"[{severity}/{confidence}] {filename}:{line} {test_id} {test_name} — {text}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <bandit.json>", file=sys.stderr)
        return 1

    report_path = Path(argv[1])
    try:
        raw = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::bandit report not readable at {report_path}: {exc}", file=sys.stderr)
        return 1

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::bandit report at {report_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    results = report.get("results") or []
    if not isinstance(results, list):
        print("::error::bandit report 'results' field is not a list", file=sys.stderr)
        return 1

    high: list[str] = []
    medium: list[str] = []
    for issue in results:
        if not isinstance(issue, dict):
            continue
        severity = (issue.get("issue_severity") or "UNDEFINED").upper()
        line = _format_issue(issue)
        if severity == _HIGH:
            high.append(line)
        elif severity == _MED:
            medium.append(line)
        # LOW / UNDEFINED are silent; the raw JSON remains in artefacts.

    for line in medium:
        print(f"::warning::bandit {line}")

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
