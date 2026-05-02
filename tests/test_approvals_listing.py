"""Phase 37: ``forgelm approvals`` listing + show subcommand.

Mirrors the ``test_human_approval_gate.py`` style — synthetic JSONL audit
log fixtures so the tests stay torch-free and run on every CI matrix combo.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_human_approval_gate.py)
# ---------------------------------------------------------------------------


def _write_event(audit_path: Path, event: str, run_id: str, **fields: object) -> None:
    """Append a synthetic event to ``audit_path``.

    Produces the same JSONL shape AuditLogger writes: one event per line,
    a ``timestamp`` / ``operator`` / ``event`` / ``run_id`` core, and
    whatever extra fields the caller passes (``staging_path``, ``metrics``,
    ``approver``, ``comment`` etc.).
    """
    entry = {
        "timestamp": "2026-04-30T12:00:00+00:00",
        "operator": "tester",
        "event": event,
        "run_id": run_id,
        "prev_hash": "genesis",
    }
    entry.update(fields)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _seed_run(
    output_dir: Path,
    run_id: str,
    *,
    decision: str | None = None,
    create_staging: bool = True,
) -> Path:
    """Create a run layout: staging dir + ``human_approval.required`` event.

    When ``decision`` is given (``"granted"`` / ``"rejected"``), append the
    matching terminal event so the run is no longer pending.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / "final_model.staging"
    if create_staging:
        staging_dir.mkdir(exist_ok=True)
        (staging_dir / "adapter_config.json").write_text('{"r": 8}', encoding="utf-8")
    audit_path = output_dir / "audit_log.jsonl"
    _write_event(
        audit_path,
        "human_approval.required",
        run_id,
        staging_path=str(staging_dir),
        gate="final_model",
        reason="require_human_approval=true",
        metrics={"eval_loss": 0.42},
    )
    if decision == "granted":
        _write_event(
            audit_path,
            "human_approval.granted",
            run_id,
            approver="alice",
            comment="LGTM",
            promote_strategy="rename",
        )
    elif decision == "rejected":
        _write_event(
            audit_path,
            "human_approval.rejected",
            run_id,
            approver="bob",
            comment="regression",
            staging_path=str(staging_dir),
        )
    return staging_dir


def _build_args(output_dir: Path, *, pending: bool = False, show: str | None = None) -> MagicMock:
    """Build a MagicMock ``args`` namespace mimicking argparse output."""
    args = MagicMock()
    args.pending = pending
    args.show = show
    args.output_dir = str(output_dir)
    return args


# ---------------------------------------------------------------------------
# --pending mode
# ---------------------------------------------------------------------------


class TestApprovalsPending:
    def test_empty_audit_log_returns_empty_list(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        # No audit_log.jsonl on disk → friendly empty path, exit 0.
        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="text")
        assert ei.value.code == 0
        captured = capsys.readouterr().out
        assert "nothing to list" in captured.lower() or "no pending" in captured.lower()

    def test_three_runs_one_decided_two_pending(self, tmp_path: Path, capsys) -> None:
        # Three runs, one already granted → listing returns the other two.
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-aaaa00000000")
        _seed_run(output_dir, "fg-bbbb00000000", decision="granted")
        _seed_run(output_dir, "fg-cccc00000000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="json")
        assert ei.value.code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["count"] == 2
        run_ids = {summary["run_id"] for summary in payload["pending"]}
        assert run_ids == {"fg-aaaa00000000", "fg-cccc00000000"}

    def test_rejected_run_also_excluded_from_pending(self, tmp_path: Path, capsys) -> None:
        # Reject (like granted) is a terminal decision; rejected runs must
        # not appear in --pending even though their staging dir lingers.
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-rejected0000", decision="rejected")
        _seed_run(output_dir, "fg-pending00000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="json")
        assert ei.value.code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert payload["pending"][0]["run_id"] == "fg-pending00000"

    def test_pending_summary_carries_metrics_and_staging_path(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        staging_dir = _seed_run(output_dir, "fg-zzzz00000000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit):
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="json")
        payload = json.loads(capsys.readouterr().out)
        summary = payload["pending"][0]
        assert summary["staging_path"] == str(staging_dir)
        assert summary["staging_exists"] is True
        assert summary["metrics"] == {"eval_loss": 0.42}
        assert summary["reason"] == "require_human_approval=true"

    def test_text_output_renders_table(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-xyz000000000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit):
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="text")
        out = capsys.readouterr().out
        # Table headers + run id present.
        assert "RUN_ID" in out
        assert "fg-xyz000000000" in out
        # The "present" / "MISSING" staging column is rendered.
        assert "present" in out


# ---------------------------------------------------------------------------
# --show mode
# ---------------------------------------------------------------------------


class TestApprovalsShow:
    def test_show_pending_run_emits_full_chain(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-pp0000000000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, show="fg-pp0000000000"), output_format="json")
        assert ei.value.code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["status"] == "pending"
        assert len(payload["chain"]) == 1
        assert payload["chain"][0]["event"] == "human_approval.required"
        # Staging dir was seeded, so contents include adapter_config.json.
        assert "adapter_config.json" in payload["staging_contents"]

    def test_show_granted_run_status_granted(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-gr0000000000", decision="granted")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, show="fg-gr0000000000"), output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "granted"
        # Two events: required + granted.
        assert len(payload["chain"]) == 2
        assert payload["chain"][-1]["event"] == "human_approval.granted"

    def test_show_unknown_run_id_exits_1(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-real00000000")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, show="fg-fake00000000"), output_format="text")
        assert ei.value.code == 1
        # Error message names the missing run id.
        # (Captured in stderr via the logger; capsys captures stdout for the
        # JSON path but the text path goes through ``logger.error``; assert
        # via caplog instead in a dedicated test below.)

    def test_show_no_audit_log_exits_1(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        # No audit_log.jsonl on disk; --show cannot operate.
        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(_build_args(output_dir, show="fg-anything0000"), output_format="text")
        assert ei.value.code == 1

    def test_show_text_renders_timeline(self, tmp_path: Path, capsys) -> None:
        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-tt0000000000", decision="granted")

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit):
            _run_approvals_cmd(_build_args(output_dir, show="fg-tt0000000000"), output_format="text")
        out = capsys.readouterr().out
        assert "fg-tt0000000000" in out
        assert "human_approval.required" in out
        assert "human_approval.granted" in out
        assert "by alice" in out  # approver rendered


# ---------------------------------------------------------------------------
# Subcommand registration smoke
# ---------------------------------------------------------------------------


class TestApprovalsRegistration:
    def test_approvals_subcommand_registered(self) -> None:
        """``forgelm approvals --help`` must succeed (subparser exists)."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "forgelm.cli", "approvals", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        # Both modes are advertised in the help text.
        assert "--pending" in result.stdout
        assert "--show" in result.stdout
        assert "--output-dir" in result.stdout


# ---------------------------------------------------------------------------
# Robustness against malformed audit log lines
# ---------------------------------------------------------------------------


class TestApprovalsMalformedLines:
    def test_skipped_lines_do_not_hide_pending_runs(self, tmp_path: Path, capsys) -> None:
        # Simulate a corrupt audit log: a real `required` event followed by
        # a malformed line and a JSON list (non-dict root).  The pending
        # listing must still surface the legitimate run.
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        audit_path = output_dir / "audit_log.jsonl"
        _write_event(
            audit_path,
            "human_approval.required",
            "fg-real00000000",
            staging_path=str(output_dir / "final_model.staging"),
        )
        with open(audit_path, "a", encoding="utf-8") as fh:
            fh.write("not even json\n")
            fh.write('["array", "root"]\n')
        # Create the staging dir so staging_exists is True (defensive — not
        # required for the test, just realistic).
        (output_dir / "final_model.staging").mkdir()

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit):
            _run_approvals_cmd(_build_args(output_dir, pending=True), output_format="json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert payload["pending"][0]["run_id"] == "fg-real00000000"


# ---------------------------------------------------------------------------
# Defensive: dispatcher rejects neither-mode args
# ---------------------------------------------------------------------------


class TestApprovalsDispatcherDefensive:
    def test_neither_pending_nor_show_exits_1(self, tmp_path: Path) -> None:
        """argparse normally enforces the mutex; this exercises the
        defensive double-check inside the dispatcher in case a future
        refactor drops the parser-level guard."""
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        args = _build_args(output_dir, pending=False, show=None)

        from forgelm.cli import _run_approvals_cmd

        with pytest.raises(SystemExit) as ei:
            _run_approvals_cmd(args, output_format="text")
        assert ei.value.code == 1


# ---------------------------------------------------------------------------
# Patch-based test for monkeypatch resolution discipline
# ---------------------------------------------------------------------------


class TestApprovalsMonkeyPatchSurface:
    def test_helper_reachable_via_facade(self) -> None:
        """``forgelm.cli._collect_pending_runs`` must resolve so tests can
        ``patch("forgelm.cli._collect_pending_runs", ...)`` if they want."""
        from forgelm import cli as _cli_facade

        assert callable(_cli_facade._collect_pending_runs)
        assert callable(_cli_facade._collect_run_audit_chain)
        assert callable(_cli_facade._run_approvals_cmd)


@pytest.mark.usefixtures("caplog")
class TestApprovalsErrorMessages:
    def test_unknown_run_logs_actionable_error(self, tmp_path: Path, caplog) -> None:
        import logging

        output_dir = tmp_path / "run"
        _seed_run(output_dir, "fg-real00000000")

        from forgelm.cli import _run_approvals_cmd

        with caplog.at_level(logging.ERROR, logger="forgelm.cli"):
            with patch("forgelm.cli._collect_pending_runs"):  # ensure not called by --show
                with pytest.raises(SystemExit) as ei:
                    _run_approvals_cmd(_build_args(output_dir, show="fg-fake00000000"), output_format="text")
        assert ei.value.code == 1
        assert "fg-fake00000000" in caplog.text
