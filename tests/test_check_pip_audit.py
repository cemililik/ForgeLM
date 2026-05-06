"""Tests for tools/check_pip_audit.py severity gate.

Pins the F-PR29-A7-11 post-flip policy: UNKNOWN severity now fails (was
silent advisory).  pip-audit's JSON shape omits OSV severity for almost
every real finding, so failing closed forces operator triage rather than
relying on missing severity to skip the gate.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = _PROJECT_ROOT / "tools" / "check_pip_audit.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_pip_audit", _TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


def _write_audit(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "pip-audit.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_no_dependencies_passes(tool, tmp_path):
    """Empty pip-audit report exits 0."""
    p = _write_audit(tmp_path, {"dependencies": []})
    assert tool.main([str(_TOOL_PATH), str(p)]) == 0


def test_no_vulnerabilities_passes(tool, tmp_path):
    """Dependencies without vulns exit 0."""
    p = _write_audit(tmp_path, {"dependencies": [{"name": "pytest", "version": "8.0.0", "vulns": []}]})
    assert tool.main([str(_TOOL_PATH), str(p)]) == 0


def test_high_severity_fails(tool, tmp_path, capsys):
    """A single HIGH-severity vuln fails the gate (existing behaviour)."""
    p = _write_audit(
        tmp_path,
        {
            "dependencies": [
                {
                    "name": "synthetic-pkg",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "CVE-2026-9999",
                            "severity": "HIGH",
                            "description": "synthetic test vulnerability",
                            "fix_versions": ["1.0.1"],
                        }
                    ],
                }
            ]
        },
    )
    assert tool.main([str(_TOOL_PATH), str(p)]) == 1
    captured = capsys.readouterr()
    assert "CVE-2026-9999" in captured.out
    assert "high/critical" in captured.out


def test_medium_severity_warns_does_not_fail(tool, tmp_path, capsys):
    """MEDIUM stays advisory — exit 0 with a ::warning:: annotation."""
    p = _write_audit(
        tmp_path,
        {
            "dependencies": [
                {
                    "name": "synthetic-pkg",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "CVE-2026-1111",
                            "severity": "MEDIUM",
                            "description": "synthetic medium vulnerability",
                        }
                    ],
                }
            ]
        },
    )
    assert tool.main([str(_TOOL_PATH), str(p)]) == 0
    captured = capsys.readouterr()
    assert "::warning::pip-audit" in captured.out
    assert "CVE-2026-1111" in captured.out


def test_unknown_severity_fails_after_a7_11_flip(tool, tmp_path, capsys):
    """F-PR29-A7-11: UNKNOWN severity now fails (was silent advisory).

    pip-audit's JSON omits OSV severity for almost every vuln, so the
    previous warn-only branch converted real findings into noise the
    operator never saw.  Failing closed forces explicit triage.
    """
    p = _write_audit(
        tmp_path,
        {
            "dependencies": [
                {
                    "name": "synthetic-pkg",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "GHSA-fake-fake-fake",
                            # No severity field -> _vuln_severity returns "UNKNOWN"
                            "description": "synthetic test vulnerability",
                        }
                    ],
                }
            ]
        },
    )
    assert tool.main([str(_TOOL_PATH), str(p)]) == 1
    captured = capsys.readouterr()
    assert "::error::pip-audit" in captured.out
    assert "GHSA-fake-fake-fake" in captured.out
    assert "without parseable" in captured.out


def test_missing_file_fails_with_error(tool, tmp_path, capsys):
    missing = tmp_path / "does-not-exist.json"
    assert tool.main([str(_TOOL_PATH), str(missing)]) == 1
    captured = capsys.readouterr()
    assert "::error::pip-audit report not readable" in captured.err


def test_invalid_json_fails_with_error(tool, tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert tool.main([str(_TOOL_PATH), str(p)]) == 1
    captured = capsys.readouterr()
    assert "not valid JSON" in captured.err


def test_high_takes_precedence_over_unknown(tool, tmp_path, capsys):
    """HIGH branch still runs first — exit message names HIGH, not UNKNOWN."""
    p = _write_audit(
        tmp_path,
        {
            "dependencies": [
                {
                    "name": "pkg-high",
                    "version": "1.0.0",
                    "vulns": [{"id": "CVE-A", "severity": "HIGH"}],
                },
                {
                    "name": "pkg-unknown",
                    "version": "1.0.0",
                    "vulns": [{"id": "GHSA-B"}],
                },
            ]
        },
    )
    assert tool.main([str(_TOOL_PATH), str(p)]) == 1
    captured = capsys.readouterr()
    assert "high/critical" in captured.out
