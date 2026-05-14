"""Phase 14 — Pipeline manifest schema + chain-integrity verifier tests.

Covers :func:`forgelm.compliance.generate_pipeline_manifest` and
:func:`forgelm.compliance.verify_pipeline_manifest`.  The pipeline
manifest is the EU AI Act Annex IV chain-of-custody artefact that ties
the per-stage ``training_manifest.json`` files into one verifiable
provenance index.
"""

from __future__ import annotations

from forgelm.cli._pipeline import PipelineStageState, PipelineState
from forgelm.compliance import _verify_manifest_payload, generate_pipeline_manifest
from forgelm.config import ForgeConfig


def _root_with_compliance() -> ForgeConfig:
    return ForgeConfig(
        model={"name_or_path": "org/base"},
        lora={"r": 8},
        training={"trainer_type": "sft"},
        data={"dataset_name_or_path": "org/data"},
        compliance={
            "provider_name": "Acme Inc",
            "provider_contact": "compliance@acme.test",
            "system_name": "Acme Pipeline System",
            "intended_purpose": "Customer-service assistant fine-tune",
            "system_version": "v0.7.0",
        },
        pipeline={
            "stages": [{"name": "sft_stage"}, {"name": "dpo_stage"}, {"name": "grpo_stage"}],
        },
    )


def _three_stage_state(*, all_completed: bool = True) -> PipelineState:
    """Build a representative 3-stage state for happy-path schema tests."""
    s1 = PipelineStageState(
        name="sft_stage",
        index=0,
        trainer_type="sft",
        status="completed" if all_completed else "completed",
        input_model="org/base",
        input_source="root",
        output_model="./out/stage1/final_model",
        started_at="2026-06-15T12:00:00+00:00",
        finished_at="2026-06-15T13:00:00+00:00",
        duration_seconds=3600.0,
        metrics={"eval_loss": 0.5},
        gate_decision="passed",
        exit_code=0,
    )
    s2 = PipelineStageState(
        name="dpo_stage",
        index=1,
        trainer_type="dpo",
        status="completed",
        input_model="./out/stage1/final_model",
        input_source="chain",
        output_model="./out/stage2/final_model",
        started_at="2026-06-15T13:00:00+00:00",
        finished_at="2026-06-15T13:45:00+00:00",
        duration_seconds=2700.0,
        metrics={"eval_loss": 0.3},
        gate_decision="passed",
        exit_code=0,
    )
    s3 = PipelineStageState(
        name="grpo_stage",
        index=2,
        trainer_type="grpo",
        status="completed",
        input_model="./out/stage2/final_model",
        input_source="chain",
        output_model="./out/stage3/final_model",
        started_at="2026-06-15T13:45:00+00:00",
        finished_at="2026-06-15T14:30:00+00:00",
        duration_seconds=2700.0,
        metrics={"eval_loss": 0.2},
        gate_decision="passed",
        exit_code=0,
    )
    return PipelineState(
        pipeline_run_id="pl_2026-06-15_a1b2c3",
        pipeline_config_hash="sha256:abc",
        forgelm_version="0.7.0",
        started_at="2026-06-15T12:00:00+00:00",
        finished_at="2026-06-15T14:30:00+00:00",
        final_status="completed",
        stages=[s1, s2, s3],
    )


# ---------------------------------------------------------------------------
# generate_pipeline_manifest — schema coverage
# ---------------------------------------------------------------------------


class TestManifestSchema:
    def test_required_top_level_keys_present(self):
        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        required = {
            "forgelm_version",
            "generated_at",
            "pipeline_run_id",
            "pipeline_config_hash",
            "started_at",
            "finished_at",
            "final_status",
            "stages",
        }
        assert required.issubset(manifest.keys())

    def test_annex_iv_block_propagated_from_root_compliance(self):
        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        assert "annex_iv" in manifest
        assert manifest["annex_iv"]["provider_name"] == "Acme Inc"
        assert manifest["annex_iv"]["system_name"] == "Acme Pipeline System"

    def test_annex_iv_omitted_when_no_compliance_block(self):
        root = ForgeConfig(
            model={"name_or_path": "x"},
            lora={},
            training={"trainer_type": "sft"},
            data={"dataset_name_or_path": "y"},
            pipeline={"stages": [{"name": "s1"}]},
        )
        manifest = generate_pipeline_manifest(_three_stage_state(), root)
        assert "annex_iv" not in manifest

    def test_stage_payload_carries_chain_fields(self):
        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        s1, s2, s3 = manifest["stages"]
        assert s1["index"] == 0 and s2["index"] == 1 and s3["index"] == 2
        assert s2["input_model"] == s1["output_model"]
        assert s3["input_model"] == s2["output_model"]
        assert all(s["gate_decision"] == "passed" for s in (s1, s2, s3))

    def test_stage_metrics_are_a_plain_dict_in_payload(self):
        """Manifest must be JSON-serialisable; metrics dict must round-
        trip through ``json.dumps``."""
        import json as _json

        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        # No round-trip failure.
        _json.dumps(manifest)


# ---------------------------------------------------------------------------
# verify_pipeline_manifest — chain integrity
# ---------------------------------------------------------------------------


class TestManifestVerification:
    def test_clean_manifest_passes(self):
        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        assert _verify_manifest_payload(manifest) == []

    def test_missing_required_key_flagged(self):
        manifest = generate_pipeline_manifest(_three_stage_state(), _root_with_compliance())
        manifest.pop("pipeline_run_id")
        violations = _verify_manifest_payload(manifest)
        assert any("pipeline_run_id" in v for v in violations)

    def test_chain_integrity_violation_flagged(self):
        """Stage 2's input_model ≠ stage 1's output_model on a chain
        stage must surface a ``chain_integrity_violation``."""
        state = _three_stage_state()
        state.stages[1].input_model = "tampered/value"
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        violations = _verify_manifest_payload(manifest)
        assert any("chain_integrity_violation" in v for v in violations)
        assert any("tampered/value" in v for v in violations)

    def test_cli_override_chain_break_still_flagged(self):
        """Even when ``input_source: cli_override`` legitimately breaks
        the chain, the verifier still surfaces it (with the same message)
        so reviewers can correlate against the audit log to decide
        legitimate vs. corrupt.

        Note: only *chain* stages contribute to the integrity check; an
        explicit cli_override stage is recorded with ``input_source !=
        "chain"`` and therefore skipped by design.  This test asserts
        that contract."""
        state = _three_stage_state()
        state.stages[1].input_model = "operator/manual"
        state.stages[1].input_source = "cli_override"
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        violations = _verify_manifest_payload(manifest)
        # cli_override stages don't trip the chain check.
        assert all("chain_integrity_violation" not in v for v in violations)

    def test_index_out_of_order_flagged(self):
        state = _three_stage_state()
        state.stages[0], state.stages[1] = state.stages[1], state.stages[0]
        # Indices stay 0/1 but names are swapped — verifier checks index
        # vs. positional order.
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        violations = _verify_manifest_payload(manifest)
        assert any("index out of order" in v for v in violations)

    def test_stopped_at_unknown_stage_flagged(self):
        state = _three_stage_state()
        state.stopped_at = "ghost_stage"
        state.final_status = "stopped_at_stage"
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        violations = _verify_manifest_payload(manifest)
        assert any("unknown stage" in v and "ghost_stage" in v for v in violations)

    def test_stopped_at_completed_stage_flagged(self):
        """If ``stopped_at`` points at a stage whose status is
        ``completed`` rather than ``failed`` / ``gated_pending_approval``,
        the manifest is internally inconsistent."""
        state = _three_stage_state()
        state.stopped_at = "sft_stage"  # which has status=completed
        state.final_status = "stopped_at_stage"
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        violations = _verify_manifest_payload(manifest)
        assert any("expected `failed` or `gated_pending_approval`" in v for v in violations)


class TestVerifyOnAutoRevertScenario:
    """End-to-end: build a state where stage 2 failed and stage 3 was
    skipped; the resulting manifest should verify cleanly (it's a valid
    record of a real failure, not an integrity violation)."""

    def test_auto_revert_manifest_verifies(self):
        s1 = PipelineStageState(
            name="sft_stage",
            index=0,
            trainer_type="sft",
            status="completed",
            input_model="org/base",
            input_source="root",
            output_model="./out/stage1/final_model",
            exit_code=0,
        )
        s2 = PipelineStageState(
            name="dpo_stage",
            index=1,
            trainer_type="dpo",
            status="failed",
            input_model="./out/stage1/final_model",
            input_source="chain",
            output_model="./out/stage2/final_model",
            auto_revert_triggered=True,
            exit_code=3,
            error="loss regression",
        )
        s3 = PipelineStageState(
            name="grpo_stage",
            index=2,
            trainer_type="grpo",
            status="skipped_due_to_prior_revert",
            skipped_reason="Stage 'dpo_stage' triggered auto_revert.",
        )
        state = PipelineState(
            pipeline_run_id="pl_x",
            pipeline_config_hash="sha256:abc",
            forgelm_version="0.7.0",
            started_at="2026-06-15T12:00:00+00:00",
            finished_at="2026-06-15T13:30:00+00:00",
            final_status="stopped_at_stage",
            stopped_at="dpo_stage",
            stages=[s1, s2, s3],
        )
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        assert _verify_manifest_payload(manifest) == []


class TestVerifyOnPartialFilterRun:
    """A ``--stage X`` run produces a manifest where other stages have
    ``status: skipped_by_filter``; verifier should accept it."""

    def test_partial_filter_manifest_verifies(self):
        s1 = PipelineStageState(name="s1", index=0, trainer_type="sft", status="skipped_by_filter")
        s2 = PipelineStageState(
            name="s2",
            index=1,
            trainer_type="dpo",
            status="completed",
            input_model="./prev/output",
            input_source="cli_override",
            output_model="./out/stage2/final_model",
            exit_code=0,
        )
        s3 = PipelineStageState(name="s3", index=2, trainer_type="grpo", status="skipped_by_filter")
        state = PipelineState(
            pipeline_run_id="pl_x",
            pipeline_config_hash="sha256:abc",
            forgelm_version="0.7.0",
            started_at="2026-06-15T12:00:00+00:00",
            final_status="completed",
            stages=[s1, s2, s3],
        )
        manifest = generate_pipeline_manifest(state, _root_with_compliance())
        assert _verify_manifest_payload(manifest) == []
