"""Phase 14 — Pipeline orchestrator state-machine tests.

Covers the documented edge cases in ``docs/roadmap/phase-14-pipeline-chains.md``
Tasks 4 + 5:

- Happy-path 3-stage chain ⇒ all three trainers run, state file +
  pipeline manifest written, exit 0.
- Auto-revert at stage 2 ⇒ stage 3 enters ``skipped_due_to_prior_revert``,
  ``pipeline.stage_reverted`` audit event fires, exit 3.
- Human-approval gate at stage 1 ⇒ exit 4, downstream stages still
  ``pending``, state preserved for ``--resume-from``.
- ``--resume-from <name>`` skips already-completed stages whose output
  directory still exists; stale-state guard rejects a config-hash
  mismatch unless ``--force-resume`` is set.
- ``--stage <name>`` partial-run filters; missing-prev-output produces
  a clear config error.
- Dry-run validates every stage without touching a trainer.

The :class:`forgelm.trainer.ForgeTrainer` is replaced via lazy-import
monkeypatch — the orchestrator only reaches the heavy modules through
``from ..trainer import ForgeTrainer`` inside ``_run_single_stage``, so
patching ``sys.modules`` and the dataset / model helpers is enough.
"""

from __future__ import annotations

import json
import os
import types
from unittest.mock import MagicMock, patch

from forgelm.cli._exit_codes import (
    EXIT_AWAITING_APPROVAL,
    EXIT_CONFIG_ERROR,
    EXIT_EVAL_FAILURE,
    EXIT_SUCCESS,
)
from forgelm.cli._pipeline import (
    PipelineOrchestrator,
    PipelineStageState,
    PipelineState,
    _compute_pipeline_config_hash,
    _deserialise_state,
    _generate_run_id,
    _serialise_state,
)
from forgelm.config import ForgeConfig
from forgelm.results import TrainResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _three_stage_config(tmp_path) -> ForgeConfig:
    """Build a minimal valid 3-stage pipeline ForgeConfig."""
    return ForgeConfig(
        model={"name_or_path": "org/base"},
        lora={"r": 8},
        training={"trainer_type": "sft", "output_dir": str(tmp_path)},
        data={"dataset_name_or_path": "org/sft"},
        pipeline={
            "output_dir": str(tmp_path / "pipeline_run"),
            "stages": [
                {
                    "name": "sft_stage",
                    "training": {"trainer_type": "sft", "output_dir": str(tmp_path / "stage1")},
                    "data": {"dataset_name_or_path": "org/sft_data"},
                },
                {
                    "name": "dpo_stage",
                    "training": {"trainer_type": "dpo", "output_dir": str(tmp_path / "stage2")},
                    "data": {"dataset_name_or_path": "org/dpo_data"},
                },
                {
                    "name": "grpo_stage",
                    "training": {"trainer_type": "grpo", "output_dir": str(tmp_path / "stage3")},
                    "data": {"dataset_name_or_path": "org/math_data"},
                },
            ],
        },
    )


def _install_trainer_mocks(monkeypatch, train_results):
    """Inject mock trainer/model/data modules.

    ``train_results`` is a list of :class:`TrainResult` returned in order
    by successive ``ForgeTrainer.train()`` calls.  The mock also
    materialises the per-stage output dir on disk so the chain-integrity
    guard in the orchestrator does not trip when subsequent stages
    auto-chain from a "fresh" directory.
    """
    iterator = iter(train_results)
    instantiated_configs = []

    class _FakeForgeTrainer:
        def __init__(self, *, model, tokenizer, config, dataset):
            instantiated_configs.append(config)
            # Materialise final_model dir on disk so the next stage's
            # chain-integrity guard sees the path it auto-chains to.
            final_dir = os.path.join(config.training.output_dir, "final_model")
            os.makedirs(final_dir, exist_ok=True)
            self.config = config

        def train(self, resume_from_checkpoint=None):
            try:
                return next(iterator)
            except StopIteration:
                return TrainResult(success=True)

    fake_trainer_mod = types.ModuleType("forgelm.trainer")
    fake_trainer_mod.ForgeTrainer = _FakeForgeTrainer
    monkeypatch.setitem(__import__("sys").modules, "forgelm.trainer", fake_trainer_mod)

    fake_model_mod = types.ModuleType("forgelm.model")
    fake_model_mod.get_model_and_tokenizer = lambda config: (MagicMock(), MagicMock())
    monkeypatch.setitem(__import__("sys").modules, "forgelm.model", fake_model_mod)

    fake_data_mod = types.ModuleType("forgelm.data")
    fake_data_mod.prepare_dataset = lambda config, tokenizer: {"train": [{"text": "x"}]}
    monkeypatch.setitem(__import__("sys").modules, "forgelm.data", fake_data_mod)

    fake_utils_mod = types.ModuleType("forgelm.utils")
    fake_utils_mod.setup_authentication = lambda token: None
    monkeypatch.setitem(__import__("sys").modules, "forgelm.utils", fake_utils_mod)

    return instantiated_configs


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPipelineConfigHash:
    def test_deterministic(self):
        h1 = _compute_pipeline_config_hash(b"some yaml bytes")
        h2 = _compute_pipeline_config_hash(b"some yaml bytes")
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_inputs_different_hashes(self):
        assert _compute_pipeline_config_hash(b"v1") != _compute_pipeline_config_hash(b"v2")

    def test_whitespace_sensitive(self):
        """Hashing raw bytes — whitespace / key order / comments all matter.

        This is intentional: regulators audit the on-disk artefact, not
        the parsed semantic content.  An operator who edits the file
        between runs gets a new hash even if the YAML is semantically
        equivalent."""
        assert _compute_pipeline_config_hash(b"a: 1\nb: 2") != _compute_pipeline_config_hash(b"b: 2\na: 1")


class TestRunIdShape:
    def test_run_id_format(self):
        run_id = _generate_run_id()
        # ``pl_YYYY-MM-DD_<6-hex>``
        assert run_id.startswith("pl_")
        parts = run_id.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 10  # YYYY-MM-DD
        assert len(parts[2]) == 6  # 6-hex

    def test_run_id_unique(self):
        ids = {_generate_run_id() for _ in range(50)}
        assert len(ids) == 50, "run_id collisions in 50 samples — too narrow randomness?"


class TestStateRoundTrip:
    def test_serialise_deserialise(self):
        state = PipelineState(
            pipeline_run_id="pl_test",
            pipeline_config_hash="sha256:abc",
            forgelm_version="0.7.0-dev",
            started_at="2026-06-15T12:00:00+00:00",
            stages=[
                PipelineStageState(name="s1", index=0, trainer_type="sft", status="completed"),
                PipelineStageState(name="s2", index=1, trainer_type="dpo", status="pending"),
            ],
        )
        payload = _serialise_state(state)
        round = _deserialise_state(payload)
        assert round.pipeline_run_id == state.pipeline_run_id
        assert len(round.stages) == 2
        assert round.stages[0].name == "s1"
        assert round.stages[0].status == "completed"

    def test_deserialise_tolerates_unknown_keys(self):
        """Future-forward compatibility: a newer manifest schema with
        extra fields must not crash an older reader."""
        payload = {
            "pipeline_run_id": "pl_test",
            "pipeline_config_hash": "sha256:abc",
            "forgelm_version": "0.7.0",
            "started_at": "2026-06-15T12:00:00+00:00",
            "final_status": "completed",
            "stages": [
                {"name": "s1", "index": 0, "trainer_type": "sft", "status": "completed", "future_field": "ignore me"}
            ],
            "future_top_level": "also ignore",
        }
        state = _deserialise_state(payload)
        assert state.stages[0].name == "s1"


# ---------------------------------------------------------------------------
# Orchestrator behaviour — dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_validates_every_stage_without_running_trainer(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        configs_seen = _install_trainer_mocks(monkeypatch, [])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.dry_run()
        assert code == EXIT_SUCCESS
        # Trainer must not have been instantiated.
        assert configs_seen == []

    def test_dry_run_does_not_write_state_or_manifest(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        orch.dry_run()
        assert not os.path.exists(orch.paths["state_file"])
        assert not os.path.exists(orch.paths["manifest_file"])


# ---------------------------------------------------------------------------
# Orchestrator behaviour — happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_three_stage_chain_runs_all_stages(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [
            TrainResult(
                success=True, metrics={"eval_loss": 0.5}, final_model_path=str(tmp_path / "stage1" / "final_model")
            ),
            TrainResult(
                success=True, metrics={"eval_loss": 0.3}, final_model_path=str(tmp_path / "stage2" / "final_model")
            ),
            TrainResult(
                success=True, metrics={"eval_loss": 0.2}, final_model_path=str(tmp_path / "stage3" / "final_model")
            ),
        ]
        configs_seen = _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run()
        assert code == EXIT_SUCCESS
        assert len(configs_seen) == 3
        # Stage 2's input model must be stage 1's output (auto-chain).
        assert configs_seen[1].model.name_or_path == str(tmp_path / "stage1" / "final_model")
        assert configs_seen[2].model.name_or_path == str(tmp_path / "stage2" / "final_model")

    def test_state_file_written_with_final_status_completed(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [TrainResult(success=True), TrainResult(success=True), TrainResult(success=True)]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        orch.run()
        assert os.path.exists(orch.paths["state_file"])
        with open(orch.paths["state_file"]) as f:
            payload = json.load(f)
        assert payload["final_status"] == "completed"
        assert payload["stopped_at"] is None
        assert all(s["status"] == "completed" for s in payload["stages"])

    def test_manifest_written_with_chain_intact(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [TrainResult(success=True), TrainResult(success=True), TrainResult(success=True)]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        orch.run()
        assert os.path.exists(orch.paths["manifest_file"])
        with open(orch.paths["manifest_file"]) as f:
            manifest = json.load(f)
        assert manifest["pipeline_run_id"].startswith("pl_")
        assert manifest["final_status"] == "completed"
        # Chain integrity in the manifest payload.
        s1, s2, s3 = manifest["stages"]
        assert s2["input_model"] == s1["output_model"]
        assert s3["input_model"] == s2["output_model"]


# ---------------------------------------------------------------------------
# Orchestrator behaviour — auto-revert + gate failures
# ---------------------------------------------------------------------------


class TestAutoRevert:
    def test_stage_2_auto_revert_stops_pipeline(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [
            TrainResult(success=True),
            TrainResult(success=False, reverted=True, error="loss regression"),
        ]
        configs_seen = _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run()
        assert code == EXIT_EVAL_FAILURE
        # Stage 3 must NOT have been instantiated.
        assert len(configs_seen) == 2
        # State file records the stop-at + skipped status.
        with open(orch.paths["state_file"]) as f:
            payload = json.load(f)
        assert payload["final_status"] == "stopped_at_stage"
        assert payload["stopped_at"] == "dpo_stage"
        statuses = [s["status"] for s in payload["stages"]]
        assert statuses == ["completed", "failed", "skipped_due_to_prior_revert"]

    def test_gate_failure_without_revert_also_stops_pipeline(self, tmp_path, monkeypatch):
        """A stage that returns ``success=False`` but ``reverted=False``
        (e.g., a benchmark min-score failure that didn't auto-revert)
        still halts the chain — downstream stages would be operating
        on an explicitly-failed checkpoint."""
        cfg = _three_stage_config(tmp_path)
        results = [TrainResult(success=False, reverted=False, error="benchmark below min")]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run()
        assert code == EXIT_EVAL_FAILURE
        with open(orch.paths["state_file"]) as f:
            payload = json.load(f)
        assert payload["stages"][0]["status"] == "failed"


# ---------------------------------------------------------------------------
# Orchestrator behaviour — human-approval gate
# ---------------------------------------------------------------------------


class TestHumanApprovalGate:
    def test_gated_stage_exits_with_awaiting_approval(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        staging = str(tmp_path / "stage1" / "final_model.staging")
        os.makedirs(staging, exist_ok=True)
        results = [TrainResult(success=True, staging_path=staging)]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run()
        assert code == EXIT_AWAITING_APPROVAL

    def test_gated_pending_approval_preserves_downstream_pending(self, tmp_path, monkeypatch):
        """After a gated stage, downstream stages must stay ``pending``
        (not ``skipped_due_to_prior_revert``) so a subsequent
        ``--resume-from`` picks them up post-approval."""
        cfg = _three_stage_config(tmp_path)
        staging = str(tmp_path / "stage1" / "final_model.staging")
        os.makedirs(staging, exist_ok=True)
        results = [TrainResult(success=True, staging_path=staging)]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        orch.run()
        with open(orch.paths["state_file"]) as f:
            payload = json.load(f)
        assert payload["final_status"] == "gated_pending_approval"
        assert payload["stages"][0]["status"] == "gated_pending_approval"
        assert payload["stages"][1]["status"] == "pending"
        assert payload["stages"][2]["status"] == "pending"

    def test_gated_stage_emits_dedicated_stage_gated_audit_event(self, tmp_path, monkeypatch):
        """Phase 14 review F-N-1 regression: a stage exiting
        ``EXIT_AWAITING_APPROVAL`` must emit a dedicated
        ``pipeline.stage_gated`` audit event (not
        ``pipeline.stage_completed`` with a sub-field).  This lets
        dashboard / SIEM filters distinguish the gate flow on the event
        name alone."""
        cfg = _three_stage_config(tmp_path)
        staging = str(tmp_path / "stage1" / "final_model.staging")
        os.makedirs(staging, exist_ok=True)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=True, staging_path=staging)])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        orch.run()
        audit_path = os.path.join(orch.paths["root_output_dir"], "audit_log.jsonl")
        with open(audit_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        gated_events = [e for e in events if e.get("event") == "pipeline.stage_gated"]
        assert len(gated_events) == 1, (
            f"Expected exactly one pipeline.stage_gated event, got {[e.get('event') for e in events]!r}"
        )
        evt = gated_events[0]
        assert evt["stage_name"] == "sft_stage"
        assert evt["gate_decision"] == "approval_pending"
        assert evt["staging_path"] == staging
        # Counter-assert: the legacy stage_completed event must NOT have
        # fired for this stage (preventing a future regression where both
        # events are emitted in parallel and the dashboard double-counts).
        completed_for_sft = [
            e for e in events if e.get("event") == "pipeline.stage_completed" and e.get("stage_name") == "sft_stage"
        ]
        assert completed_for_sft == []


# ---------------------------------------------------------------------------
# Orchestrator behaviour — --stage filter
# ---------------------------------------------------------------------------


class TestStageFilter:
    def test_unknown_stage_name_rejected(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run(stage_filter="nonexistent_stage")
        assert code == EXIT_CONFIG_ERROR

    def test_filter_to_first_stage_runs_only_it(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [TrainResult(success=True)]
        configs_seen = _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run(stage_filter="sft_stage")
        assert code == EXIT_SUCCESS
        assert len(configs_seen) == 1
        with open(orch.paths["state_file"]) as f:
            payload = json.load(f)
        statuses = [s["status"] for s in payload["stages"]]
        assert statuses == ["completed", "skipped_by_filter", "skipped_by_filter"]

    def test_filter_to_middle_stage_without_prev_output_fails_cleanly(self, tmp_path, monkeypatch):
        """``--stage dpo_stage`` without sft_stage's output on disk must
        fail with a clear EXIT_CONFIG_ERROR — not silently fall back to
        the root ``model.name_or_path``."""
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=True)])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        # Make sure the prev output dir does NOT exist.
        assert not os.path.exists(tmp_path / "stage1" / "final_model")
        code = orch.run(stage_filter="dpo_stage")
        assert code == EXIT_CONFIG_ERROR

    def test_filter_with_input_model_override_succeeds(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        configs_seen = _install_trainer_mocks(monkeypatch, [TrainResult(success=True)])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        override_path = str(tmp_path / "manual_input")
        os.makedirs(override_path, exist_ok=True)
        code = orch.run(stage_filter="dpo_stage", input_model_override=override_path)
        assert code == EXIT_SUCCESS
        assert len(configs_seen) == 1
        assert configs_seen[0].model.name_or_path == override_path


# ---------------------------------------------------------------------------
# Orchestrator behaviour — --resume-from
# ---------------------------------------------------------------------------


class TestResumeFrom:
    def test_resume_without_state_file_fails(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [])
        orch = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch.run(resume_from="dpo_stage")
        assert code == EXIT_CONFIG_ERROR

    def test_resume_skips_completed_stages(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        # First run: stage 1 completes, stage 2 fails (training crash).
        results_run1 = [
            TrainResult(success=True),
            TrainResult(success=False, error="oom"),
        ]
        _install_trainer_mocks(monkeypatch, results_run1)
        orch1 = PipelineOrchestrator(cfg, b"yaml bytes")
        orch1.run()
        # Second run: resume from dpo_stage.  Stage 1 already completed
        # AND its output_model dir exists (mock created it) — must skip.
        results_run2 = [TrainResult(success=True), TrainResult(success=True)]
        configs_seen2 = _install_trainer_mocks(monkeypatch, results_run2)
        orch2 = PipelineOrchestrator(cfg, b"yaml bytes")
        code = orch2.run(resume_from="dpo_stage")
        assert code == EXIT_SUCCESS
        # Only stage 2 + stage 3 ran — stage 1 was skipped.
        assert len(configs_seen2) == 2

    def test_stale_config_hash_rejects_resume(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=False, error="x")])
        orch1 = PipelineOrchestrator(cfg, b"original yaml")
        orch1.run()
        # Operator edited the YAML; resume against a different hash.
        # Post-Phase-14-review: refusal flows back through ``run()`` as a
        # plain return value (not ``sys.exit`` mid-method) so the audit-
        # log + summary path runs uniformly on every refusal.
        orch2 = PipelineOrchestrator(cfg, b"edited yaml")
        code = orch2.run(resume_from="dpo_stage")
        assert code == EXIT_CONFIG_ERROR

    def test_force_resume_accepts_stale_hash_with_warning(self, tmp_path, monkeypatch, caplog):
        import logging

        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=False, error="x")])
        orch1 = PipelineOrchestrator(cfg, b"original yaml")
        orch1.run()
        _install_trainer_mocks(monkeypatch, [TrainResult(success=True), TrainResult(success=True)])
        orch2 = PipelineOrchestrator(cfg, b"edited yaml")
        with caplog.at_level(logging.WARNING, logger="forgelm.pipeline"):
            code = orch2.run(resume_from="dpo_stage", force_resume=True)
        assert code == EXIT_SUCCESS

    def test_force_resume_emits_audit_event_with_both_hashes(self, tmp_path, monkeypatch):
        """Phase 14 review F-B-2 regression: ``--force-resume`` must
        emit a ``pipeline.force_resume`` audit event carrying both the
        old and new ``pipeline_config_hash`` so a compliance reviewer
        can distinguish an operator-approved override from a normal
        resume.  Pre-fix, only a WARNING log line was emitted — invisible
        in the append-only audit-log JSONL stream."""
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=False, error="x")])
        orch1 = PipelineOrchestrator(cfg, b"yaml v1")
        orch1.run()

        _install_trainer_mocks(monkeypatch, [TrainResult(success=True), TrainResult(success=True)])
        orch2 = PipelineOrchestrator(cfg, b"yaml v2 (operator edited)")
        orch2.run(resume_from="dpo_stage", force_resume=True)

        audit_path = os.path.join(orch2.paths["root_output_dir"], "audit_log.jsonl")
        assert os.path.exists(audit_path)
        with open(audit_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        force_resume_events = [e for e in events if e.get("event") == "pipeline.force_resume"]
        assert len(force_resume_events) == 1, (
            f"Expected exactly one pipeline.force_resume audit event, got "
            f"{len(force_resume_events)}: {[e.get('event') for e in events]!r}"
        )
        evt = force_resume_events[0]
        assert "old_config_hash" in evt
        assert "new_config_hash" in evt
        assert evt["old_config_hash"] != evt["new_config_hash"]
        assert "yaml v1" not in str(evt) and "yaml v2" not in str(evt), (
            "Audit event must record hashes, not raw YAML bytes."
        )

    def test_resume_with_unknown_stage_name_fails(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=False, error="x")])
        orch1 = PipelineOrchestrator(cfg, b"yaml")
        orch1.run()
        orch2 = PipelineOrchestrator(cfg, b"yaml")
        code = orch2.run(resume_from="nonexistent")
        assert code == EXIT_CONFIG_ERROR


# ---------------------------------------------------------------------------
# Orchestrator behaviour — audit + webhook (best-effort emission, no crash)
# ---------------------------------------------------------------------------


class TestAuditAndWebhook:
    def test_audit_events_emitted_on_happy_path(self, tmp_path, monkeypatch):
        cfg = _three_stage_config(tmp_path)
        results = [TrainResult(success=True), TrainResult(success=True), TrainResult(success=True)]
        _install_trainer_mocks(monkeypatch, results)
        orch = PipelineOrchestrator(cfg, b"yaml")
        orch.run()
        # Audit log file lives under the root output dir.
        audit_path = os.path.join(orch.paths["root_output_dir"], "audit_log.jsonl")
        assert os.path.exists(audit_path)
        with open(audit_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        event_names = [e["event"] for e in events]
        assert "pipeline.started" in event_names
        assert event_names.count("pipeline.stage_started") == 3
        assert event_names.count("pipeline.stage_completed") == 3
        assert "pipeline.completed" in event_names

    def test_webhook_failures_do_not_abort_pipeline(self, tmp_path, monkeypatch):
        """A crashing webhook notifier must not derail the pipeline.

        Mirrors the existing per-stage webhook discipline — best-effort
        telemetry never blocks the operator's actual work."""
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(
            monkeypatch, [TrainResult(success=True), TrainResult(success=True), TrainResult(success=True)]
        )
        with patch("forgelm.webhook.WebhookNotifier", side_effect=RuntimeError("notifier down")):
            orch = PipelineOrchestrator(cfg, b"yaml")
            code = orch.run()
        assert code == EXIT_SUCCESS

    def test_audit_event_failures_do_not_abort_pipeline(self, tmp_path, monkeypatch):
        """Phase 14 review F-N-5 regression: ``_audit_event``'s
        documented ``except Exception`` swallow path must be reached and
        the pipeline must continue.  An audit-write failure (read-only
        filesystem, disk full, malformed audit logger config) is
        documented as best-effort — the orchestrator emits a WARNING and
        carries on; the test patches ``AuditLogger.log_event`` to raise
        and asserts the run completes with the expected exit code."""
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=True)] * 3)

        from forgelm.compliance import AuditLogger as _RealAuditLogger

        original_log_event = _RealAuditLogger.log_event

        def _raising_log_event(self, event, **fields):
            if event.startswith("pipeline."):
                raise OSError("Disk full / read-only audit log")
            return original_log_event(self, event, **fields)

        monkeypatch.setattr(_RealAuditLogger, "log_event", _raising_log_event)
        orch = PipelineOrchestrator(cfg, b"yaml")
        code = orch.run()
        assert code == EXIT_SUCCESS

    def test_emit_summary_json_output_is_round_trippable(self, tmp_path, monkeypatch, capsys):
        """Phase 14 review F-N-7 regression: the ``output_format='json'``
        branch of ``_emit_summary`` is the dispatcher contract for
        ``forgelm --config pipeline.yaml --output-format json`` — it
        must print a single JSON object that round-trips through
        ``json.loads`` and carries the per-stage payload reviewers
        consume programmatically."""
        cfg = _three_stage_config(tmp_path)
        _install_trainer_mocks(monkeypatch, [TrainResult(success=True)] * 3)
        orch = PipelineOrchestrator(cfg, b"yaml", output_format="json")
        code = orch.run()
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        # The JSON object is the only thing on stdout; logger goes to stderr.
        payload = json.loads(out)
        assert payload["final_status"] == "completed"
        assert len(payload["stages"]) == 3
        assert all(s["status"] == "completed" for s in payload["stages"])
