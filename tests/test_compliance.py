"""Unit tests for Phase 6: safety, judge, compliance, and resource tracking."""

import json
import os

import pytest

from forgelm.compliance import (
    _sanitize_md,
    compute_dataset_fingerprint,
    generate_training_manifest,
)
from forgelm.config import ForgeConfig, JudgeConfig, SafetyConfig
from forgelm.judge import JudgeResult
from forgelm.results import TrainResult
from forgelm.safety import SafetyResult


def _minimal_config(**overrides):
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


# --- Config models ---


class TestSafetyConfig:
    def test_defaults(self):
        s = SafetyConfig()
        assert s.enabled is False
        assert s.max_safety_regression == pytest.approx(0.05)

    def test_custom(self):
        s = SafetyConfig(enabled=True, classifier="custom/guard", max_safety_regression=0.1)
        assert s.enabled is True
        assert s.classifier == "custom/guard"


class TestJudgeConfig:
    def test_defaults(self):
        j = JudgeConfig()
        assert j.enabled is False
        assert j.judge_model == "gpt-4o"
        assert j.min_score == pytest.approx(5.0)

    def test_local_judge(self):
        j = JudgeConfig(enabled=True, judge_model="/local/judge", judge_api_key_env=None)
        assert j.judge_api_key_env is None


class TestEvaluationWithSafetyJudge:
    def test_eval_config_with_safety(self):
        cfg = ForgeConfig(
            **_minimal_config(
                evaluation={
                    "auto_revert": True,
                    "safety": {"enabled": True, "test_prompts": "prompts.jsonl"},
                }
            )
        )
        assert cfg.evaluation.safety.enabled is True

    def test_eval_config_with_judge(self):
        cfg = ForgeConfig(
            **_minimal_config(
                evaluation={
                    "llm_judge": {"enabled": True, "min_score": 7.0},
                }
            )
        )
        assert cfg.evaluation.llm_judge.min_score == pytest.approx(7.0)

    def test_eval_config_with_all(self):
        cfg = ForgeConfig(
            **_minimal_config(
                evaluation={
                    "auto_revert": True,
                    "max_acceptable_loss": 2.0,
                    "benchmark": {"enabled": True, "tasks": ["arc_easy"]},
                    "safety": {"enabled": True},
                    "llm_judge": {"enabled": True},
                }
            )
        )
        assert cfg.evaluation.benchmark.enabled
        assert cfg.evaluation.safety.enabled
        assert cfg.evaluation.llm_judge.enabled


# --- Result dataclasses ---


class TestSafetyResult:
    def test_passed(self):
        r = SafetyResult(safe_ratio=0.95, total_count=100, unsafe_count=5, passed=True)
        assert r.passed is True

    def test_failed(self):
        r = SafetyResult(
            safe_ratio=0.80, total_count=100, unsafe_count=20, passed=False, failure_reason="Too many unsafe"
        )
        assert r.passed is False


class TestJudgeResult:
    def test_passed(self):
        r = JudgeResult(average_score=7.5, passed=True)
        assert r.passed is True

    def test_failed(self):
        r = JudgeResult(average_score=3.0, passed=False, failure_reason="Below threshold")
        assert r.passed is False


class TestTrainResultPhase6:
    def test_resource_usage(self):
        r = TrainResult(success=True, resource_usage={"gpu_hours": 2.4, "peak_vram_gb": 22.1})
        assert r.resource_usage["gpu_hours"] == pytest.approx(2.4)

    def test_safety_and_judge(self):
        r = TrainResult(success=True, safety_passed=True, judge_score=8.5)
        assert r.safety_passed is True
        assert r.judge_score == pytest.approx(8.5)


# --- Compliance ---


class TestDatasetFingerprint:
    def test_local_file(self, tmp_path):
        test_file = tmp_path / "data.jsonl"
        test_file.write_text('{"prompt": "hello"}\n')
        fp = compute_dataset_fingerprint(str(test_file))
        assert "sha256" in fp
        assert fp["size_bytes"] > 0

    def test_hub_dataset(self):
        fp = compute_dataset_fingerprint("HuggingFaceH4/ultrachat_200k")
        assert fp["source"] == "huggingface_hub"
        assert fp["dataset_id"] == "HuggingFaceH4/ultrachat_200k"


class TestTrainingManifest:
    def test_generate_manifest(self):
        cfg = ForgeConfig(**_minimal_config())
        manifest = generate_training_manifest(cfg, metrics={"eval_loss": 0.5})
        assert manifest["model_lineage"]["base_model"] == "org/model"
        assert manifest["training_parameters"]["trainer_type"] == "sft"
        assert manifest["data_provenance"]["primary_dataset"] == "org/dataset"
        assert manifest["evaluation_results"]["metrics"]["eval_loss"] == pytest.approx(0.5)

    def test_manifest_with_resource_usage(self):
        cfg = ForgeConfig(**_minimal_config())
        manifest = generate_training_manifest(
            cfg,
            metrics={"eval_loss": 0.5},
            resource_usage={"gpu_hours": 1.5, "peak_vram_gb": 16.0},
        )
        assert manifest["resource_usage"]["gpu_hours"] == pytest.approx(1.5)


class TestComplianceExport:
    def test_export_creates_files(self, tmp_path):
        from forgelm.compliance import export_compliance_artifacts

        cfg = ForgeConfig(**_minimal_config())
        manifest = generate_training_manifest(cfg, metrics={"eval_loss": 0.5})
        output_dir = str(tmp_path / "compliance")
        files = export_compliance_artifacts(manifest, output_dir)
        assert len(files) == 3
        assert all(os.path.isfile(f) for f in files)
        # Verify JSON is valid
        with open(files[0]) as f:
            data = json.load(f)
        assert "model_lineage" in data


# --- AuditLogger hash chain ---


class TestAuditLoggerHashChain:
    def test_restores_hash_chain_on_second_instance(self, tmp_path):
        """A second AuditLogger pointing at the same directory must continue
        the hash chain from the last entry, not reset to 'genesis'."""
        from forgelm.compliance import AuditLogger

        log1 = AuditLogger(str(tmp_path))
        log1.log_event("test.event", key="value")
        hash_after_first_event = log1._prev_hash

        log2 = AuditLogger(str(tmp_path))
        # Must NOT reset to "genesis" — should read from the existing file
        assert log2._prev_hash != "genesis", "Second AuditLogger instance must not reset the hash chain to 'genesis'"
        # The second instance's starting hash is the hash of the last written line,
        # which matches what log1 computed after writing.
        assert log2._prev_hash == hash_after_first_event

    def test_genesis_hash_on_fresh_dir(self, tmp_path):
        """First-ever AuditLogger on a fresh directory starts at 'genesis'."""
        from forgelm.compliance import AuditLogger

        log = AuditLogger(str(tmp_path / "newdir"))
        assert log._prev_hash == "genesis"

    def test_hash_advances_after_each_event(self, tmp_path):
        """Each new log event must advance _prev_hash to a new value."""
        from forgelm.compliance import AuditLogger

        log = AuditLogger(str(tmp_path))
        h0 = log._prev_hash
        log.log_event("event.one")
        h1 = log._prev_hash
        log.log_event("event.two")
        h2 = log._prev_hash

        assert h0 != h1
        assert h1 != h2


# --- _sanitize_md ---


class TestSanitizeMd:
    def test_escapes_pipe(self):
        result = _sanitize_md("hello | world")
        assert "\\|" in result

    def test_strips_newlines(self):
        result = _sanitize_md("line1\nline2")
        assert "\n" not in result

    def test_strips_carriage_returns(self):
        result = _sanitize_md("line1\r\nline2")
        assert "\r" not in result

    def test_empty_string_returns_not_specified(self):
        result = _sanitize_md("")
        assert result == "Not specified"

    def test_none_returns_not_specified(self):
        result = _sanitize_md(None)
        assert result == "Not specified"

    def test_normal_text_unchanged(self):
        result = _sanitize_md("Hello world")
        assert result == "Hello world"

    def test_multiple_pipes_all_escaped(self):
        result = _sanitize_md("a | b | c")
        assert result.count("\\|") == 2
