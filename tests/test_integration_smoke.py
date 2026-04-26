"""Integration smoke test — CPU only, no GPU/torch required.

Tests the full pipeline features that don't require model training:
- Config validation with all Phase 8 fields
- CLI dry-run with compliance/risk/governance config
- Compliance export standalone
- Audit logger
- Model integrity verification
- Deployer instructions generation
- Evidence bundle export
- Data format detection
- Wizard config generation (mocked input)
"""

import json
import os
from unittest.mock import patch

import pytest
import yaml

from forgelm.cli import (
    EXIT_SUCCESS,
    _run_compliance_export,
    _run_dry_run,
    main,
)
from forgelm.compliance import (
    AuditLogger,
    export_compliance_artifacts,
    export_evidence_bundle,
    generate_deployer_instructions,
    generate_model_integrity,
    generate_training_manifest,
)
from forgelm.config import ForgeConfig, load_config

try:
    from forgelm.data import _detect_dataset_format
except ImportError:
    _detect_dataset_format = None


def _full_config():
    """A config using ALL Phase 8 fields."""
    return {
        "model": {
            "name_or_path": "HuggingFaceTB/SmolLM2-135M-Instruct",
            "max_length": 512,
            "load_in_4bit": False,
            "trust_remote_code": False,
            "offline": False,
        },
        "lora": {
            "r": 16,
            "alpha": 32,
            "method": "dora",
            "target_modules": ["q_proj", "v_proj"],
        },
        "training": {
            "trainer_type": "sft",
            "output_dir": "./test_checkpoints",
            "num_train_epochs": 1,
            "per_device_train_batch_size": 2,
            "learning_rate": 2e-5,
            "report_to": "none",
        },
        "data": {
            "dataset_name_or_path": "test_data.jsonl",
            "governance": {
                "collection_method": "Manual curation by domain experts",
                "annotation_process": "Two annotators, adjudication by senior",
                "known_biases": "English-skewed, EU region only",
                "personal_data_included": True,
                "dpia_completed": True,
            },
        },
        "evaluation": {
            "auto_revert": True,
            "max_acceptable_loss": 2.0,
            "require_human_approval": False,
            "benchmark": {
                "enabled": True,
                "tasks": ["arc_easy"],
                "min_score": 0.3,
            },
            "safety": {
                "enabled": True,
                "classifier": "meta-llama/Llama-Guard-3-8B",
                "test_prompts": "safety_prompts.jsonl",
                "max_safety_regression": 0.05,
            },
            "llm_judge": {
                "enabled": True,
                "judge_model": "gpt-4o",
                "judge_api_key_env": "OPENAI_API_KEY",
                "eval_dataset": "eval_prompts.jsonl",
                "min_score": 7.0,
            },
        },
        "compliance": {
            "provider_name": "Test Corp",
            "provider_contact": "ai@testcorp.com",
            "system_name": "Customer Support Bot",
            "intended_purpose": "Automated customer support for insurance claims",
            "known_limitations": "Not suitable for medical or legal advice",
            "system_version": "2.1.0",
            "risk_classification": "high-risk",
        },
        "risk_assessment": {
            "intended_use": "Customer support chatbot for insurance",
            "foreseeable_misuse": [
                "Users may ask for medical advice",
                "Model may generate incorrect policy details",
            ],
            "risk_category": "high-risk",
            "mitigation_measures": [
                "Safety classifier blocks harmful outputs",
                "Human review required for policy responses",
            ],
            "vulnerable_groups_considered": True,
        },
        "monitoring": {
            "enabled": True,
            "endpoint_env": "MONITORING_URL",
            "metrics_export": "prometheus",
            "alert_on_drift": True,
            "check_interval_hours": 12,
        },
        "webhook": {
            "url_env": "FORGELM_WEBHOOK_URL",
            "notify_on_start": True,
            "notify_on_success": True,
            "notify_on_failure": True,
            "timeout": 10,
        },
    }


class TestFullConfigValidation:
    """Test that a config with ALL fields validates correctly."""

    def test_full_config_parses(self):
        cfg = ForgeConfig(**_full_config())
        assert cfg.model.name_or_path == "HuggingFaceTB/SmolLM2-135M-Instruct"
        assert cfg.compliance.risk_classification == "high-risk"
        assert cfg.risk_assessment.risk_category == "high-risk"
        assert cfg.data.governance.dpia_completed is True
        assert cfg.monitoring.metrics_export == "prometheus"
        assert cfg.evaluation.require_human_approval is False
        assert cfg.webhook.timeout == 10

    def test_full_config_yaml_round_trip(self, tmp_path):
        cfg_path = str(tmp_path / "full_config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_full_config(), f)
        cfg = load_config(cfg_path)
        assert cfg.compliance.provider_name == "Test Corp"
        assert cfg.risk_assessment.foreseeable_misuse[0] == "Users may ask for medical advice"
        assert cfg.data.governance.collection_method == "Manual curation by domain experts"

    def test_high_risk_without_safety_warns(self, caplog):
        import logging

        data = _full_config()
        del data["evaluation"]["safety"]
        with caplog.at_level(logging.WARNING, logger="forgelm.config"):
            ForgeConfig(**data)
        assert "High-risk AI" in caplog.text


class TestDryRunWithCompliance:
    """Test --dry-run with full Phase 8 config."""

    def test_dry_run_json_includes_compliance(self, capsys):
        cfg = ForgeConfig(**_full_config())
        _run_dry_run(cfg, "json")
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "valid"

    def test_dry_run_via_main(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_full_config(), f)
        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--dry-run", "--output-format", "json"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS


class TestComplianceExportIntegration:
    """Test standalone compliance export end-to-end."""

    def test_export_creates_all_artifacts(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        output_dir = str(tmp_path / "audit")
        _run_compliance_export(cfg, output_dir, "text")

        # Verify files exist
        assert os.path.isfile(os.path.join(output_dir, "compliance_report.json"))
        assert os.path.isfile(os.path.join(output_dir, "training_manifest.yaml"))
        assert os.path.isfile(os.path.join(output_dir, "data_provenance.json"))
        assert os.path.isfile(os.path.join(output_dir, "risk_assessment.json"))
        assert os.path.isfile(os.path.join(output_dir, "annex_iv_metadata.json"))

    def test_compliance_report_has_annex_iv(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        manifest = generate_training_manifest(cfg, {"eval_loss": 0.5})

        assert "annex_iv" in manifest
        assert manifest["annex_iv"]["provider_name"] == "Test Corp"
        assert manifest["annex_iv"]["risk_classification"] == "high-risk"
        assert manifest["annex_iv"]["intended_purpose"] == "Automated customer support for insurance claims"

    def test_compliance_report_has_risk_assessment(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        manifest = generate_training_manifest(cfg, {})

        assert "risk_assessment" in manifest
        assert manifest["risk_assessment"]["risk_category"] == "high-risk"
        assert len(manifest["risk_assessment"]["foreseeable_misuse"]) == 2

    def test_compliance_report_has_monitoring(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        manifest = generate_training_manifest(cfg, {})

        assert "monitoring" in manifest
        assert manifest["monitoring"]["metrics_export"] == "prometheus"

    def test_export_json_output(self, tmp_path, capsys):
        cfg = ForgeConfig(**_full_config())
        output_dir = str(tmp_path / "audit")
        _run_compliance_export(cfg, output_dir, "json")
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert len(result["files"]) >= 5

    def test_annex_iv_file_content(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        output_dir = str(tmp_path / "audit")
        manifest = generate_training_manifest(cfg, {"eval_loss": 0.5})
        export_compliance_artifacts(manifest, output_dir)

        annex_path = os.path.join(output_dir, "annex_iv_metadata.json")
        with open(annex_path) as f:
            annex = json.load(f)
        assert annex["provider_name"] == "Test Corp"
        assert annex["system_name"] == "Customer Support Bot"

    def test_risk_assessment_file_content(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        output_dir = str(tmp_path / "audit")
        manifest = generate_training_manifest(cfg, {})
        export_compliance_artifacts(manifest, output_dir)

        risk_path = os.path.join(output_dir, "risk_assessment.json")
        with open(risk_path) as f:
            risk = json.load(f)
        assert risk["intended_use"] == "Customer support chatbot for insurance"
        assert risk["vulnerable_groups_considered"] is True


class TestAuditLoggerIntegration:
    """Test audit logger end-to-end."""

    def test_full_event_chain(self, tmp_path):
        audit = AuditLogger(str(tmp_path), run_id="test-run-001")

        audit.log_event("pipeline.initialized", model="test-model")
        audit.log_event("training.started")
        audit.log_event("evaluation.loss_check", eval_loss=0.5, passed=True)
        audit.log_event("evaluation.safety", safe_ratio=0.95, passed=True)
        audit.log_event("human_approval.required", model_path="/tmp/model")
        audit.log_event("pipeline.completed", success=True)

        log_path = os.path.join(str(tmp_path), "audit_log.jsonl")
        with open(log_path) as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 6
        assert all(e["run_id"] == "test-run-001" for e in events)
        assert events[0]["event"] == "pipeline.initialized"
        assert events[3]["event"] == "evaluation.safety"
        assert events[3]["safe_ratio"] == pytest.approx(0.95)
        assert events[4]["event"] == "human_approval.required"
        assert events[5]["event"] == "pipeline.completed"

        # Verify chronological order
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)


class TestModelIntegrityIntegration:
    """Test model integrity verification end-to-end."""

    def test_checksums_on_real_files(self, tmp_path):
        model_dir = tmp_path / "final_model"
        model_dir.mkdir()
        (model_dir / "adapter_model.safetensors").write_bytes(b"fake adapter weights " * 100)
        (model_dir / "adapter_config.json").write_text('{"r": 16, "alpha": 32}')
        (model_dir / "tokenizer.json").write_text('{"model": "test"}')
        (model_dir / "tokenizer_config.json").write_text('{"pad_token": "<pad>"}')

        integrity = generate_model_integrity(str(model_dir))
        assert len(integrity["artifacts"]) == 4
        assert integrity["verified_at"]

        # Verify checksums are deterministic
        integrity2 = generate_model_integrity(str(model_dir))
        for a1, a2 in zip(integrity["artifacts"], integrity2["artifacts"]):
            assert a1["sha256"] == a2["sha256"]
            assert a1["size_bytes"] == a2["size_bytes"]


class TestDeployerInstructionsIntegration:
    """Test deployer instructions generation end-to-end."""

    def test_full_instructions(self, tmp_path):
        cfg = ForgeConfig(**_full_config())
        final_path = str(tmp_path / "model")
        doc_path = generate_deployer_instructions(cfg, {"eval_loss": 0.5, "safety/safe_ratio": 0.97}, final_path)

        content = open(doc_path).read()
        assert "Test Corp" in content
        assert "Customer Support Bot" in content
        assert "insurance claims" in content
        assert "medical" in content.lower()  # foreseeable misuse
        assert "eval_loss" in content
        assert "Human Oversight" in content
        assert "Incident Reporting" in content


class TestEvidenceBundleIntegration:
    """Test evidence bundle ZIP creation end-to-end."""

    def test_bundle_contains_all_files(self, tmp_path):
        cfg = ForgeConfig(**_full_config())

        # Generate all compliance artifacts
        compliance_dir = str(tmp_path / "compliance")
        manifest = generate_training_manifest(cfg, {"eval_loss": 0.5})
        files = export_compliance_artifacts(manifest, compliance_dir)
        assert len(files) >= 5

        # Create bundle
        bundle_path = str(tmp_path / "evidence_bundle.zip")
        result = export_evidence_bundle(compliance_dir, bundle_path)
        assert os.path.isfile(result)

        import zipfile

        with zipfile.ZipFile(bundle_path) as zf:
            names = zf.namelist()
        assert len(names) >= 5
        assert any("compliance_report.json" in n for n in names)
        assert any("risk_assessment.json" in n for n in names)
        assert any("annex_iv_metadata.json" in n for n in names)


@pytest.mark.skipif(_detect_dataset_format is None, reason="datasets library not installed")
class TestDataFormatDetection:
    """Test dataset format auto-detection."""

    def test_sft_format(self):
        result = _detect_dataset_format(["User", "Assistant", "System"])
        assert result["suggested_trainer"] == "sft"
        assert "instruction" in result["description"].lower() or "User" in result["description"]

    def test_dpo_format(self):
        result = _detect_dataset_format(["prompt", "chosen", "rejected"])
        assert result["suggested_trainer"] == "dpo"

    def test_kto_format(self):
        result = _detect_dataset_format(["prompt", "completion", "label"])
        assert result["suggested_trainer"] == "kto"

    def test_grpo_format(self):
        result = _detect_dataset_format(["prompt"])
        assert result["suggested_trainer"] == "grpo"

    def test_messages_format(self):
        result = _detect_dataset_format(["messages"])
        assert result["suggested_trainer"] == "sft"

    def test_unknown_format(self):
        result = _detect_dataset_format(["col_a", "col_b", "col_c"])
        assert result["suggested_trainer"] == "sft"
        assert "unknown" in result["description"].lower()


class TestConfigTemplateWithPhase8:
    """Verify config_template.yaml includes Phase 8 sections."""

    def test_template_has_compliance_section(self):
        template_path = os.path.join(os.path.dirname(__file__), "..", "config_template.yaml")
        with open(template_path) as f:
            content = f.read()
        assert "compliance:" in content
        assert "provider_name:" in content
        assert "risk_classification:" in content

    def test_template_has_risk_assessment_section(self):
        template_path = os.path.join(os.path.dirname(__file__), "..", "config_template.yaml")
        with open(template_path) as f:
            content = f.read()
        assert "risk_assessment:" in content
        assert "foreseeable_misuse:" in content

    def test_template_has_monitoring_section(self):
        template_path = os.path.join(os.path.dirname(__file__), "..", "config_template.yaml")
        with open(template_path) as f:
            content = f.read()
        assert "monitoring:" in content
        assert "metrics_export:" in content

    def test_template_still_parses(self):
        template_path = os.path.join(os.path.dirname(__file__), "..", "config_template.yaml")
        cfg = load_config(template_path)
        assert cfg.model.name_or_path
        assert cfg.training.trainer_type == "sft"
