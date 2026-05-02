"""Unit tests for Phase 8: EU AI Act deep compliance features."""

import json
import os

import yaml

from forgelm.compliance import (
    AuditLogger,
    export_evidence_bundle,
    generate_deployer_instructions,
    generate_model_integrity,
    generate_training_manifest,
)
from forgelm.config import (
    ComplianceMetadataConfig,
    DataGovernanceConfig,
    ForgeConfig,
    RiskAssessmentConfig,
    load_config,
)

# --- Config Models ---


class TestComplianceMetadataConfig:
    def test_defaults(self):
        c = ComplianceMetadataConfig()
        assert c.provider_name == ""
        assert c.risk_classification == "minimal-risk"

    def test_full(self):
        c = ComplianceMetadataConfig(
            provider_name="Acme Corp",
            intended_purpose="Customer support chatbot",
            risk_classification="high-risk",
        )
        assert c.provider_name == "Acme Corp"
        assert c.risk_classification == "high-risk"


class TestRiskAssessmentConfig:
    def test_defaults(self):
        r = RiskAssessmentConfig()
        assert r.intended_use == ""
        assert r.risk_category == "minimal-risk"
        assert r.foreseeable_misuse == []

    def test_full(self):
        r = RiskAssessmentConfig(
            intended_use="Insurance claim processing",
            risk_category="high-risk",
            foreseeable_misuse=["Medical advice", "Legal advice"],
            mitigation_measures=["Human review required"],
            vulnerable_groups_considered=True,
        )
        assert r.risk_category == "high-risk"
        assert len(r.foreseeable_misuse) == 2


class TestDataGovernanceConfig:
    def test_defaults(self):
        d = DataGovernanceConfig()
        assert d.collection_method == ""
        assert d.personal_data_included is False

    def test_full(self):
        d = DataGovernanceConfig(
            collection_method="Manual curation",
            annotation_process="Two annotators, adjudication",
            known_biases="English-skewed",
            personal_data_included=True,
            dpia_completed=True,
        )
        assert d.personal_data_included is True


class TestForgeConfigCompliance:
    def test_compliance_in_config(self, minimal_config):
        cfg = ForgeConfig(
            **minimal_config(
                compliance={
                    "provider_name": "Test Corp",
                    "intended_purpose": "Testing",
                    "risk_classification": "high-risk",
                }
            )
        )
        assert cfg.compliance.provider_name == "Test Corp"

    def test_risk_assessment_in_config(self, minimal_config):
        cfg = ForgeConfig(
            **minimal_config(
                risk_assessment={
                    "intended_use": "Test use",
                    "risk_category": "limited-risk",
                }
            )
        )
        assert cfg.risk_assessment.risk_category == "limited-risk"

    def test_data_governance_in_config(self, minimal_config):
        cfg = ForgeConfig(
            **minimal_config(
                data={
                    "dataset_name_or_path": "org/dataset",
                    "governance": {"collection_method": "Web scraping"},
                }
            )
        )
        assert cfg.data.governance.collection_method == "Web scraping"

    def test_human_approval_in_eval(self, minimal_config):
        cfg = ForgeConfig(**minimal_config(evaluation={"require_human_approval": True}))
        assert cfg.evaluation.require_human_approval is True

    def test_high_risk_warnings(self, caplog, minimal_config):
        import logging

        with caplog.at_level(logging.WARNING, logger="forgelm.config"):
            ForgeConfig(
                **minimal_config(
                    risk_assessment={"risk_category": "high-risk"},
                )
            )
        assert "High-risk AI" in caplog.text

    def test_yaml_round_trip(self, tmp_path, minimal_config):
        data = minimal_config(
            compliance={"provider_name": "Acme", "intended_purpose": "Support"},
            risk_assessment={"intended_use": "Chat", "risk_category": "limited-risk"},
            data={
                "dataset_name_or_path": "org/ds",
                "governance": {"collection_method": "Manual"},
            },
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.compliance.provider_name == "Acme"
        assert cfg.risk_assessment.risk_category == "limited-risk"
        assert cfg.data.governance.collection_method == "Manual"


# --- Audit Logger ---


class TestAuditLogger:
    def test_creates_log_file(self, tmp_path):
        audit = AuditLogger(str(tmp_path))
        audit.log_event("test.event", detail="hello")

        log_path = os.path.join(str(tmp_path), "audit_log.jsonl")
        assert os.path.isfile(log_path)

        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert entry["event"] == "test.event"
        assert entry["detail"] == "hello"
        assert "run_id" in entry
        assert "timestamp" in entry

    def test_multiple_events(self, tmp_path):
        audit = AuditLogger(str(tmp_path))
        audit.log_event("event.one")
        audit.log_event("event.two")
        audit.log_event("event.three")

        with open(os.path.join(str(tmp_path), "audit_log.jsonl")) as f:
            lines = f.readlines()
        assert len(lines) == 3

    def test_consistent_run_id(self, tmp_path):
        audit = AuditLogger(str(tmp_path), run_id="test-run-123")
        audit.log_event("event.a")
        audit.log_event("event.b")

        with open(os.path.join(str(tmp_path), "audit_log.jsonl")) as f:
            entries = [json.loads(line) for line in f]
        assert all(e["run_id"] == "test-run-123" for e in entries)


# --- Model Integrity ---


class TestModelIntegrity:
    def test_generates_checksums(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "weights.bin").write_bytes(b"fake model weights")
        (model_dir / "config.json").write_text('{"key": "value"}')

        integrity = generate_model_integrity(str(model_dir))
        assert len(integrity["artifacts"]) == 2
        assert all("sha256" in a for a in integrity["artifacts"])
        assert all("size_bytes" in a for a in integrity["artifacts"])

    def test_empty_directory(self, tmp_path):
        model_dir = tmp_path / "empty_model"
        model_dir.mkdir()
        integrity = generate_model_integrity(str(model_dir))
        assert integrity["artifacts"] == []


# --- Deployer Instructions ---


class TestDeployerInstructions:
    def test_generates_document(self, tmp_path, minimal_config):
        config = ForgeConfig(
            **minimal_config(
                compliance={"provider_name": "TestCo", "intended_purpose": "Customer support"},
            )
        )
        final_path = str(tmp_path / "model")
        doc_path = generate_deployer_instructions(config, {"eval_loss": 0.5}, final_path)
        assert os.path.isfile(doc_path)

        content = open(doc_path).read()
        assert "TestCo" in content
        assert "Customer support" in content
        # Metric names go through _sanitize_md, which CommonMark-escapes the
        # underscore. Stripping backslashes recovers the human-readable form
        # for the test (renderers do the same when displaying the document).
        assert "eval_loss" in content.replace("\\", "")

    def test_without_compliance_config(self, tmp_path, minimal_config):
        config = ForgeConfig(**minimal_config())
        final_path = str(tmp_path / "model")
        doc_path = generate_deployer_instructions(config, {}, final_path)
        assert os.path.isfile(doc_path)


# --- Evidence Bundle ---


class TestEvidenceBundle:
    def test_creates_zip(self, tmp_path):
        compliance_dir = tmp_path / "compliance"
        compliance_dir.mkdir()
        (compliance_dir / "report.json").write_text('{"test": true}')
        (compliance_dir / "manifest.yaml").write_text("test: true")

        bundle_path = str(tmp_path / "bundle.zip")
        result = export_evidence_bundle(str(compliance_dir), bundle_path)
        assert os.path.isfile(result)

        import zipfile

        with zipfile.ZipFile(bundle_path) as zf:
            names = zf.namelist()
        assert len(names) == 2


# --- Training Manifest with Annex IV ---


class TestManifestAnnexIV:
    def test_includes_annex_iv(self, minimal_config):
        config = ForgeConfig(
            **minimal_config(
                compliance={"provider_name": "Corp", "system_name": "Bot", "risk_classification": "high-risk"},
            )
        )
        manifest = generate_training_manifest(config, {"eval_loss": 0.5})
        assert "annex_iv" in manifest
        assert manifest["annex_iv"]["provider_name"] == "Corp"
        assert manifest["annex_iv"]["risk_classification"] == "high-risk"

    def test_includes_risk_assessment(self, minimal_config):
        config = ForgeConfig(
            **minimal_config(
                risk_assessment={"intended_use": "Chat", "risk_category": "high-risk"},
            )
        )
        manifest = generate_training_manifest(config, {})
        assert "risk_assessment" in manifest
        assert manifest["risk_assessment"]["risk_category"] == "high-risk"

    def test_without_compliance(self, minimal_config):
        config = ForgeConfig(**minimal_config())
        manifest = generate_training_manifest(config, {})
        assert "annex_iv" not in manifest
        assert "risk_assessment" not in manifest
