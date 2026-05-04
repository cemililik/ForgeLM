"""Phase 21 — GDPR Article 17 erasure (`forgelm purge`).

Mirrors the design spec at
``docs/analysis/code_reviews/gdpr-erasure-design-202605021414.md`` §7
which enumerates the 11 tests Phase 21 must ship.  Tests run torch-free
and use synthetic JSONL fixtures so every CI matrix combo exercises the
full surface.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_corpus(corpus_path: Path, rows: list[dict]) -> None:
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with open(corpus_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _read_audit_events(audit_log_path: Path) -> list[dict]:
    """Parse audit_log.jsonl events; skip blank lines."""
    events: list[dict] = []
    with open(audit_log_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _build_args(
    *,
    row_id: str | None = None,
    corpus: str | None = None,
    run_id: str | None = None,
    kind: str | None = None,
    check_policy: bool = False,
    output_dir: str | None = None,
    config: str | None = None,
    justification: str | None = None,
    dry_run: bool = False,
    row_matches: str = "one",
) -> SimpleNamespace:
    """Strict argparse-shaped namespace; misspelled attrs raise."""
    return SimpleNamespace(
        row_id=row_id,
        corpus=corpus,
        run_id=run_id,
        kind=kind,
        check_policy=check_policy,
        output_dir=output_dir,
        config=config,
        justification=justification,
        dry_run=dry_run,
        row_matches=row_matches,
    )


@pytest.fixture(autouse=True)
def _set_operator_env(monkeypatch):
    """Every test runs with a deterministic FORGELM_OPERATOR so AuditLogger
    does not refuse to start on shared CI runners."""
    monkeypatch.setenv("FORGELM_OPERATOR", "test-operator@gdpr-test")
    monkeypatch.delenv("FORGELM_AUDIT_SECRET", raising=False)


# ---------------------------------------------------------------------------
# §7 Test 1 — Row erasure: JSONL row removed + audit events emitted in order
# ---------------------------------------------------------------------------


class TestRowErasure:
    def test_row_erasure_removes_matching_row_only(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "row-A", "text": "Alice's data"},
                {"id": "row-B", "text": "Bob's data"},
                {"id": "row-C", "text": "Carol's data"},
            ],
        )

        args = _build_args(row_id="row-B", corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0

        # Corpus now has only A + C in original order.
        with open(corpus, "r", encoding="utf-8") as fh:
            remaining = [json.loads(line) for line in fh if line.strip()]
        assert [r["id"] for r in remaining] == ["row-A", "row-C"]

    def test_row_erasure_emits_request_then_completed_in_order(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-X", "text": "to erase"}])

        args = _build_args(row_id="row-X", corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        names = [e["event"] for e in events]
        assert "data.erasure_requested" in names
        assert "data.erasure_completed" in names
        # Order: request must come BEFORE completed (design §4.4).
        assert names.index("data.erasure_requested") < names.index("data.erasure_completed")

    def test_row_erasure_target_id_is_hashed_not_cleartext(self, tmp_path: Path) -> None:
        """Design §5.4: target_id in row mode is SHA-256(salt + value);
        the raw row id must NEVER appear in the audit chain."""
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        raw_id = "ali@example.com"  # PII-shaped row id
        _seed_corpus(corpus, [{"id": raw_id, "text": "subject data"}])

        args = _build_args(row_id=raw_id, corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        request_evt = next(e for e in events if e["event"] == "data.erasure_requested")
        assert request_evt["target_id"] != raw_id, "raw row id leaked into audit chain"
        assert len(request_evt["target_id"]) == 64, "target_id should be hex SHA-256 (64 chars)"
        # And the raw email must not appear ANYWHERE in the chain.
        full_log_text = (tmp_path / "audit_log.jsonl").read_text()
        assert raw_id not in full_log_text


# ---------------------------------------------------------------------------
# §7 Test 2 — Salt persistence + salt_source
# ---------------------------------------------------------------------------


class TestSaltPersistence:
    def test_salt_file_created_on_first_use_with_mode_0600(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _resolve_salt

        salt, source = _resolve_salt(str(tmp_path))
        salt_path = tmp_path / ".forgelm_audit_salt"
        assert salt_path.is_file()
        assert len(salt) == 16
        assert source == "per_dir"
        # Mode 0600 — owner read/write only.
        mode = stat.S_IMODE(salt_path.stat().st_mode)
        assert mode == 0o600, f"salt file mode should be 0o600, got {oct(mode)}"

    def test_salt_persistent_across_invocations(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _resolve_salt

        salt1, _ = _resolve_salt(str(tmp_path))
        salt2, _ = _resolve_salt(str(tmp_path))
        assert salt1 == salt2, "per-output-dir salt must be stable across calls"

    def test_salt_source_env_var_when_secret_set(self, tmp_path: Path, monkeypatch) -> None:
        from forgelm.cli.subcommands._purge import _resolve_salt

        monkeypatch.setenv("FORGELM_AUDIT_SECRET", "supersecret-prod-key-2026-05")
        salt, source = _resolve_salt(str(tmp_path))
        assert source == "env_var"
        assert len(salt) == 16

    def test_salt_changes_with_env_var_toggle(self, tmp_path: Path, monkeypatch) -> None:
        """Phase 20 design F-R5-05: env-var toggle IS a hash discontinuity;
        the salt_source field on every event makes that visible."""
        from forgelm.cli.subcommands._purge import _resolve_salt

        salt_no_env, source_no_env = _resolve_salt(str(tmp_path))
        monkeypatch.setenv("FORGELM_AUDIT_SECRET", "abc123")
        salt_env, source_env = _resolve_salt(str(tmp_path))
        assert source_no_env == "per_dir"
        assert source_env == "env_var"
        assert salt_no_env != salt_env, "env var must alter the resolved salt"


# ---------------------------------------------------------------------------
# §7 Test 3 — Run-scoped staging deletion
# ---------------------------------------------------------------------------


class TestStagingDeletion:
    def test_staging_kind_removes_staging_directory(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        run_id = "fg-stagingrun01"
        staging = tmp_path / f"final_model.staging.{run_id}"
        staging.mkdir(parents=True)
        (staging / "adapter_config.json").write_text('{"r": 8}')
        (staging / "weights.bin").write_bytes(b"x" * 1024)

        args = _build_args(run_id=run_id, kind="staging", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0
        assert not staging.exists()


# ---------------------------------------------------------------------------
# §7 Test 4 — Run-scoped artefact deletion
# ---------------------------------------------------------------------------


class TestArtefactDeletion:
    def test_artefacts_kind_removes_compliance_bundle_for_run(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        run_id = "fg-artefactsrun"
        compliance_dir = tmp_path / "compliance"
        compliance_dir.mkdir(parents=True)
        (compliance_dir / f"compliance_{run_id}.json").write_text("{}")
        (compliance_dir / f"annex_iv_{run_id}.json").write_text("{}")
        (compliance_dir / "compliance_other-run.json").write_text("{}")  # different run

        args = _build_args(run_id=run_id, kind="artefacts", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0
        assert not (compliance_dir / f"compliance_{run_id}.json").exists()
        assert not (compliance_dir / f"annex_iv_{run_id}.json").exists()
        # Other run's bundle is untouched.
        assert (compliance_dir / "compliance_other-run.json").exists()


# ---------------------------------------------------------------------------
# §7 Test 5 — Audit chain post-erasure still verifies
# ---------------------------------------------------------------------------


class TestAuditChainIntegrity:
    def test_chain_verifies_post_erasure(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        # Pre-seed the chain with a non-erasure event so the genesis +
        # erasure events both have to chain correctly.
        from forgelm.compliance import AuditLogger, verify_audit_log

        AuditLogger(str(tmp_path)).log_event("training.started", run_label="pre-erasure")

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-1", "text": "subject"}])
        args = _build_args(row_id="row-1", corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        result = verify_audit_log(str(tmp_path / "audit_log.jsonl"))
        assert result.valid, f"chain must verify post-erasure; got: {result}"


# ---------------------------------------------------------------------------
# §7 Test 6 — `--check-policy` reports violations correctly
# ---------------------------------------------------------------------------


class TestCheckPolicy:
    def test_check_policy_with_no_retention_block_returns_zero_with_note(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        # Create a minimal config WITHOUT retention block.
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
"""
        )
        args = _build_args(check_policy=True, config=str(config_path), output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["violations"] == []

    def test_check_policy_reports_overstayed_artefact(self, tmp_path: Path, capsys, monkeypatch) -> None:
        from forgelm.cli.subcommands._purge import _scan_retention_violations
        from forgelm.config import RetentionConfig

        # Synthetic overstayed artefact: ephemeral horizon = 30 days,
        # data audit report mtime = 60 days ago → 1 violation.
        report = tmp_path / "data_audit_report.json"
        report.write_text("{}")
        sixty_days_ago = report.stat().st_mtime - 60 * 86400
        os.utime(report, (sixty_days_ago, sixty_days_ago))

        retention = RetentionConfig(ephemeral_artefact_retention_days=30)
        violations = _scan_retention_violations(retention, str(tmp_path))
        kinds = [v["artefact_kind"] for v in violations]
        assert "data_audit_report" in kinds
        # Age source = mtime fallback (no audit log present).
        rep_violation = next(v for v in violations if v["artefact_kind"] == "data_audit_report")
        assert rep_violation["age_source"] == "mtime"
        assert rep_violation["age_days"] >= 30

    def test_check_policy_always_exits_zero(self, tmp_path: Path) -> None:
        """Design §10 Q5: `--check-policy` is a report, not a gate.
        Exit code is always 0 regardless of violation count."""
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
retention:
  ephemeral_artefact_retention_days: 1
"""
        )
        # Plant an overstayed artefact.
        report = tmp_path / "data_audit_report.json"
        report.write_text("{}")
        ago = report.stat().st_mtime - 30 * 86400
        os.utime(report, (ago, ago))

        args = _build_args(check_policy=True, config=str(config_path), output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0, "check-policy must exit 0 even with violations (report-not-gate)"


# ---------------------------------------------------------------------------
# §7 Test 7 — Atomic concurrency
# ---------------------------------------------------------------------------


class TestAtomicity:
    def test_atomic_rewrite_leaves_no_partial_file_on_io_failure(self, tmp_path: Path, monkeypatch) -> None:
        from forgelm.cli.subcommands import _purge

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "row-1", "text": "keep"},
                {"id": "row-2", "text": "keep"},
                {"id": "row-3", "text": "drop"},
            ],
        )
        original_content = corpus.read_text()

        # Inject an OSError mid-rewrite via os.replace patching.
        original_replace = os.replace

        def _failing_replace(src, dst):
            if str(dst) == str(corpus):
                raise OSError("simulated atomic-rename failure")
            return original_replace(src, dst)

        monkeypatch.setattr(os, "replace", _failing_replace)

        with pytest.raises(OSError, match="simulated atomic-rename failure"):
            _purge._atomic_rewrite_dropping_lines(str(corpus), [3])

        # Corpus must be UNCHANGED (atomic = all-or-nothing).
        assert corpus.read_text() == original_content


# ---------------------------------------------------------------------------
# §7 Test 8 — Unknown row-id / run-id → clear error message
# ---------------------------------------------------------------------------


class TestUnknownTargetErrors:
    def test_unknown_row_id_emits_failed_event_then_exits_one(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-A"}, {"id": "row-B"}])
        args = _build_args(row_id="row-NOPE", corpus=str(corpus), output_dir=str(tmp_path))

        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "row-NOPE" in payload["error"]

        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        names = [e["event"] for e in events]
        assert "data.erasure_requested" in names
        assert "data.erasure_failed" in names
        # NOT data.erasure_completed.
        assert "data.erasure_completed" not in names

    def test_unknown_run_id_artefacts_emits_failed_event(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        # Empty output dir; no compliance bundle for this run.
        args = _build_args(run_id="fg-nonexistent", kind="artefacts", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1


# ---------------------------------------------------------------------------
# §7 Test 9 — Multi-row policy: --row-matches
# ---------------------------------------------------------------------------


class TestMultiRowPolicy:
    def test_multi_match_one_mode_refuses(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "shared-id", "text": "first"},
                {"id": "shared-id", "text": "second"},
            ],
        )
        args = _build_args(
            row_id="shared-id",
            corpus=str(corpus),
            output_dir=str(tmp_path),
            row_matches="one",
        )
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1
        payload = json.loads(capsys.readouterr().out)
        assert "matched" in payload["error"].lower()

    def test_multi_match_all_mode_deletes_every_match(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "shared-id", "text": "first"},
                {"id": "keep-me"},
                {"id": "shared-id", "text": "second"},
            ],
        )
        args = _build_args(
            row_id="shared-id",
            corpus=str(corpus),
            output_dir=str(tmp_path),
            row_matches="all",
        )
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 0
        with open(corpus, "r", encoding="utf-8") as fh:
            remaining = [json.loads(line) for line in fh if line.strip()]
        assert remaining == [{"id": "keep-me"}]


# ---------------------------------------------------------------------------
# §7 Test 10 — --dry-run preserves disk; emits chain
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_modify_corpus(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-X", "text": "subject"}])
        original = corpus.read_text()

        args = _build_args(row_id="row-X", corpus=str(corpus), output_dir=str(tmp_path), dry_run=True)
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        assert corpus.read_text() == original

        # But the chain still records intent.
        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        names = [e["event"] for e in events]
        assert "data.erasure_requested" in names
        assert "data.erasure_completed" in names  # marked dry_run=True
        completed = next(e for e in events if e["event"] == "data.erasure_completed")
        assert completed.get("dry_run") is True


# ---------------------------------------------------------------------------
# §7 Test 11 — Warning events fire alongside completed
# ---------------------------------------------------------------------------


class TestWarningEvents:
    def test_memorisation_warning_fires_when_final_model_exists(self, tmp_path: Path) -> None:
        """Plant a `final_model.staging.<run_id>` directory; row erasure
        should emit data.erasure_warning_memorisation."""
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        # Plant a final_model dir AND a staging dir with a discoverable
        # run id so the warning includes affected_run_ids.
        final = tmp_path / "final_model"
        final.mkdir()
        staging = tmp_path / "final_model.staging.fg-pastrun"
        staging.mkdir()

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-Y", "text": "memorised"}])
        args = _build_args(row_id="row-Y", corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        names = [e["event"] for e in events]
        assert "data.erasure_warning_memorisation" in names
        warn_evt = next(e for e in events if e["event"] == "data.erasure_warning_memorisation")
        assert warn_evt.get("affected_run_ids") == ["fg-pastrun"]

    def test_synthetic_data_warning_fires_when_synthetic_files_exist(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        (tmp_path / "synthetic_data.jsonl").write_text("{}\n")

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-Z"}])
        args = _build_args(row_id="row-Z", corpus=str(corpus), output_dir=str(tmp_path))
        with pytest.raises(SystemExit):
            _run_purge_cmd(args, output_format="json")

        events = _read_audit_events(tmp_path / "audit_log.jsonl")
        assert "data.erasure_warning_synthetic_data_present" in [e["event"] for e in events]


# ---------------------------------------------------------------------------
# Defensive: dispatcher rejects mutually-exclusive flag combinations
# ---------------------------------------------------------------------------


class TestDispatcherDefensive:
    def test_check_policy_with_row_id_is_rejected(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        args = _build_args(check_policy=True, row_id="x", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_row_id_and_run_id_together_rejected(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        args = _build_args(row_id="x", run_id="y", output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_no_mode_at_all_rejected(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._purge import _run_purge_cmd

        args = _build_args(output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_purge_cmd(args, output_format="json")
        assert ei.value.code == 1


# ---------------------------------------------------------------------------
# Deprecation: evaluation.staging_ttl_days alias-forward
# ---------------------------------------------------------------------------


class TestStagingTtlDeprecation:
    def test_legacy_only_non_default_alias_forwards_with_warning(self, tmp_path: Path) -> None:
        """Phase 20 design §3.1: legacy field with non-default value
        forwards to retention.staging_ttl_days + emits DeprecationWarning."""
        from forgelm.config import load_config

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
evaluation:
  staging_ttl_days: 14
"""
        )
        with pytest.warns(DeprecationWarning, match="staging_ttl_days"):
            cfg = load_config(str(config_path))
        assert cfg.retention is not None
        assert cfg.retention.staging_ttl_days == 14

    def test_both_set_with_different_values_raises_config_error(self, tmp_path: Path) -> None:
        from forgelm.config import ConfigError, load_config

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
evaluation:
  staging_ttl_days: 14
retention:
  staging_ttl_days: 30
"""
        )
        with pytest.raises(ConfigError, match="staging_ttl_days"):
            load_config(str(config_path))

    def test_canonical_only_no_warning(self, tmp_path: Path, recwarn) -> None:
        from forgelm.config import load_config

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
retention:
  staging_ttl_days: 14
"""
        )
        cfg = load_config(str(config_path))
        assert cfg.retention is not None
        assert cfg.retention.staging_ttl_days == 14
        # No DeprecationWarning under the canonical path.
        deprecation_warnings = [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]
        assert not deprecation_warnings, (
            f"unexpected deprecation warnings: {[str(w.message) for w in deprecation_warnings]}"
        )


# ---------------------------------------------------------------------------
# Facade re-exports (test that public surface resolves)
# ---------------------------------------------------------------------------


class TestFacadeReExports:
    def test_purge_helpers_reachable_via_cli_facade(self) -> None:
        from forgelm import cli as _cli_facade

        for name in (
            "_run_purge_cmd",
            "_run_purge_row_id",
            "_run_purge_run_id",
            "_run_purge_check_policy",
            "_resolve_salt",
            "_hash_target_id",
            "_find_matching_rows",
            "_atomic_rewrite_dropping_lines",
            "_scan_retention_violations",
        ):
            assert hasattr(_cli_facade, name), f"forgelm.cli must re-export {name!r}"
