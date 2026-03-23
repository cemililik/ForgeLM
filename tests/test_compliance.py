"""Unit tests for Phase 6: safety, judge, compliance, and resource tracking."""
import json
import os
import pytest

from forgelm.config import ForgeConfig, SafetyConfig, JudgeConfig, EvaluationConfig
from forgelm.safety import SafetyResult
from forgelm.judge import JudgeResult
from forgelm.compliance import compute_dataset_fingerprint, generate_training_manifest
from forgelm.trainer import TrainResult


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
        assert s.max_safety_regression == 0.05

    def test_custom(self):
        s = SafetyConfig(enabled=True, classifier="custom/guard", max_safety_regression=0.1)
        assert s.enabled is True
        assert s.classifier == "custom/guard"


class TestJudgeConfig:
    def test_defaults(self):
        j = JudgeConfig()
        assert j.enabled is False
        assert j.judge_model == "gpt-4o"
        assert j.min_score == 5.0

    def test_local_judge(self):
        j = JudgeConfig(enabled=True, judge_model="/local/judge", judge_api_key_env=None)
        assert j.judge_api_key_env is None


class TestEvaluationWithSafetyJudge:
    def test_eval_config_with_safety(self):
        cfg = ForgeConfig(**_minimal_config(evaluation={
            "auto_revert": True,
            "safety": {"enabled": True, "test_prompts": "prompts.jsonl"},
        }))
        assert cfg.evaluation.safety.enabled is True

    def test_eval_config_with_judge(self):
        cfg = ForgeConfig(**_minimal_config(evaluation={
            "llm_judge": {"enabled": True, "min_score": 7.0},
        }))
        assert cfg.evaluation.llm_judge.min_score == 7.0

    def test_eval_config_with_all(self):
        cfg = ForgeConfig(**_minimal_config(evaluation={
            "auto_revert": True,
            "max_acceptable_loss": 2.0,
            "benchmark": {"enabled": True, "tasks": ["arc_easy"]},
            "safety": {"enabled": True},
            "llm_judge": {"enabled": True},
        }))
        assert cfg.evaluation.benchmark.enabled
        assert cfg.evaluation.safety.enabled
        assert cfg.evaluation.llm_judge.enabled


# --- Result dataclasses ---

class TestSafetyResult:
    def test_passed(self):
        r = SafetyResult(safe_ratio=0.95, total_count=100, unsafe_count=5, passed=True)
        assert r.passed is True

    def test_failed(self):
        r = SafetyResult(safe_ratio=0.80, total_count=100, unsafe_count=20, passed=False,
                         failure_reason="Too many unsafe")
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
        assert r.resource_usage["gpu_hours"] == 2.4

    def test_safety_and_judge(self):
        r = TrainResult(success=True, safety_passed=True, judge_score=8.5)
        assert r.safety_passed is True
        assert r.judge_score == 8.5


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
        assert manifest["evaluation_results"]["metrics"]["eval_loss"] == 0.5

    def test_manifest_with_resource_usage(self):
        cfg = ForgeConfig(**_minimal_config())
        manifest = generate_training_manifest(
            cfg,
            metrics={"eval_loss": 0.5},
            resource_usage={"gpu_hours": 1.5, "peak_vram_gb": 16.0},
        )
        assert manifest["resource_usage"]["gpu_hours"] == 1.5


class TestComplianceExport:
    def test_export_creates_files(self, tmp_path):
        from forgelm.compliance import export_compliance_artifacts
        cfg = ForgeConfig(**_minimal_config())
        manifest = generate_training_manifest(cfg, metrics={"eval_loss": 0.5})
        output_dir = str(tmp_path / "compliance")
        files = export_compliance_artifacts(manifest, cfg, output_dir)
        assert len(files) == 3
        assert all(os.path.isfile(f) for f in files)
        # Verify JSON is valid
        with open(files[0]) as f:
            data = json.load(f)
        assert "model_lineage" in data
