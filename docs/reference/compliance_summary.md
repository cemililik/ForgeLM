## Compliance Summary: EU AI Act (Article 17 + related requirements)

Purpose
- Provide a concise, machine‑friendly summary of how ForgeLM implements evidence, controls and artifacts that support compliance with the EU AI Act (not legal advice).

Scope
- This document maps repo components, evidence files, and operational gaps to common EU AI Act expectations for high‑risk systems (Article 17 QMS, provenance, audit trails, monitoring).

Quick conclusion
- ForgeLM already implements many technical controls relevant to Article 17: post‑training safety evaluation with auto‑revert, dataset and checkpoint SHA‑256 fingerprinting, and machine‑readable compliance artifacts. Additional organizational, signing, and immutable‑logging steps are recommended to harden auditability for formal QMS/third‑party review.

Required / relevant EU AI Act items (high level)
- Risk assessment and governance (who is responsible, risk classification).
- Quality Management System (QMS) processes and records (Article 17): documented procedures, versioning, roles, and training records.
- Data provenance and documentation: dataset source, preprocessing, schema, fingerprints, timestamps.
- Technical documentation & conformity evidence: model lineage, evaluation results, safety tests, validation reports.
- Monitoring & post‑market surveillance: runtime monitoring, incident logging, corrective actions.

Where ForgeLM meets these (technical evidence)
- Safety evaluation & auto‑revert
  - Implementation: core logic in `forgelm/trainer.py` (auto‑revert triggers and `_revert_model`). See [forgelm/trainer.py](forgelm/trainer.py#L37) and `_revert_model` at [forgelm/trainer.py](forgelm/trainer.py#L278).
  - Behavior: configurable `max_safety_regression` and `auto_revert` flags; safety checks executed post‑training.

- Safety classifier and thresholds
  - Implementation: `forgelm/safety.py` performs classification on adversarial prompts and enforces thresholds. See [forgelm/safety.py](forgelm/safety.py#L33) and threshold logic at [forgelm/safety.py](forgelm/safety.py#L129).

- Data provenance (SHA‑256) and compliance export
  - Implementation: `forgelm/compliance.py` computes SHA‑256 fingerprints, writes `data_provenance.json`, and exports compliance artifacts. See [forgelm/compliance.py](forgelm/compliance.py#L1) and hash calculation at [forgelm/compliance.py](forgelm/compliance.py#L33) and file output at [forgelm/compliance.py](forgelm/compliance.py#L167).

- Documentation & examples
  - Usage and safety compliance guidance: [docs/guides/safety_compliance.md](docs/guides/safety_compliance.md#L23).
  - Template config shows `auto_revert` and safety settings: [config_template.yaml](config_template.yaml#L101).
  - Marketing/README highlight features: [README.md](README.md#L21).

- Tests
  - Unit tests validate provenance and revert logic: `tests/test_compliance.py` and `tests/test_trainer.py`. Example: `sha256` checks in [tests/test_compliance.py](tests/test_compliance.py#L134).

Gaps, residual risks and operational considerations
- Organizational QMS (Article 17) — gap
  - Code and generated artifacts exist, but formal QMS documents (SOPs, roles, training records, approvals) live outside repo. Recommendation: create `docs/qms/` with SOP templates, roles and review signoffs.

- Immutable evidence & signing — risk
  - SHA‑256 fingerprints are good, but unauthenticated files can be tampered with. Recommendation: add timestamping and digital signatures (GPG/PKI) for `data_provenance.json` and `compliance_report.json`, or integrate with an append‑only log (e.g., remote ledger, WORM storage).

- Revert safety & retention — operational risk
  - Current `_revert_model` deletes artifacts. For audits and incident analysis, prefer archiving reverted artifacts to a secure, read‑only archive before deletion and keep an audit entry. Add configurable retention / require human approval for production revert.

- Access controls & secrets — risk
  - Ensure provenance and model artifacts are protected by RBAC and encrypted at rest. Document expected IAM roles for auditors vs engineers.

- Post‑market monitoring — gap
  - Add runtime safety telemetry and incident reporting hooks (webhooks/metrics) to track deployed model behavior and feed into QMS corrective actions.

Firms' opportunities
- Competitive advantage: highlight existing technical controls (auto‑revert + SHA‑256) and market as “EU AI Act–ready” packages.
- Productization: compliance export + audit‑bundle, GitHub Actions workflows, and audit checklist templates.
- Enterprise add‑ons: QMS integration, signed/timestamped provenance, RBAC, and admin dashboard.

Recommended additions (prioritized)
1. Compliance summary document (this file) + `docs/qms/` skeleton with SOP templates and roles (low effort).
2. Evidence bundle export: implement `forge compliance bundle` to produce `compliance_bundle.zip` (model card, `data_provenance.json`, `compliance_report.json`, evaluation logs).
3. Signed provenance: timestamp + GPG or PKI signing of provenance file; optionally publish signatures to a public bulletin (or store in S3 with immutable versioning).
4. CI workflow example: add `.github/workflows/auto_revert.yml` demonstrating post‑training safety checks, revert flow, and notification (Slack/Issue).
5. Revert safe‑guards: archive reverted artifacts and add a configurable human approval window for production pipelines.
6. Runtime monitoring & incident reporting hooks for post‑market surveillance.

Implementation notes and quick examples
- Evidence bundle command (example):

```bash
# Export compliance artifacts from a completed training run
forgelm --config job.yaml --compliance-export ./compliance_output/

# Package all artifacts into a single auditor-ready ZIP
# (export_evidence_bundle() in forgelm/compliance.py)
```

- CI workflow skeleton (concept): create `.github/workflows/auto_revert.yml` that runs train → evaluate → safety checks → if fail: archive artifacts, create issue, optionally revert. Add Slack or webhook notifications.

- Signing provenance (concept):

```bash
gpg --armor --detach-sign data_provenance.json
sha256sum data_provenance.json > data_provenance.sha256
```

Evidence locations (quick links)
- Auto‑revert logic: [forgelm/trainer.py](forgelm/trainer.py) — `_revert_model`
- Safety evaluation: [forgelm/safety.py](forgelm/safety.py)
- Provenance + AuditLogger + hash chain: [forgelm/compliance.py](forgelm/compliance.py)
- Config template: [config_template.yaml](config_template.yaml)
- Safety guidance: [docs/guides/safety_compliance.md](docs/guides/safety_compliance.md)
- Tests: [tests/test_compliance.py](tests/test_compliance.py), [tests/test_trainer.py](tests/test_trainer.py)

Phase 8 implemented features (all complete)
- ComplianceMetadataConfig: provider_name, intended_purpose, risk_classification, system_name (Annex IV)
- RiskAssessmentConfig: intended_use, foreseeable_misuse, risk_category, mitigation_measures (Art. 9)
- DataGovernanceConfig: collection_method, annotation_process, known_biases, DPIA tracking (Art. 10)
- AuditLogger: append-only JSON Lines event log with run_id, operator, timestamps, SHA-256 hash chain, per-line HMAC, flock concurrent-write guard, genesis manifest sidecar (Art. 12)
- generate_deployer_instructions(): auto-generated markdown for non-ML deployers (Art. 13)
- require_human_approval: pipeline pauses for review, exit code 4 (Art. 14)
- generate_model_integrity(): SHA-256 checksums on all output artifacts (Art. 15)
- MonitoringConfig: post-market monitoring hooks — Prometheus/Datadog (Art. 17)
- export_evidence_bundle(): ZIP archive of all compliance artifacts
- QMS templates: 5 SOP documents in `docs/qms/` (training, data, incident, change, roles)
- `--compliance-export` CLI flag: standalone compliance artifact generation without GPU

Phase 9 implemented features (advanced safety scoring)
- Confidence score extraction: captures classifier probability per response
- Confidence-weighted safety score: `scoring: "confidence_weighted"`, `min_safety_score` threshold
- Low-confidence alerts: flags responses where classifier confidence < `min_classifier_confidence`
- Llama Guard S1-S14 harm category parsing: 14 categories mapped to severity levels
- Severity levels: critical/high/medium/low with per-severity threshold enforcement
- Cross-run trend tracking: `safety_trend.jsonl` (append-only, longitudinal analysis)
- Built-in adversarial prompt library: `configs/safety_prompts/` (50 prompts in 3 categories)
- 3-layer safety gate: binary ratio → confidence score → severity thresholds

Remaining considerations
- Signed/timestamped provenance (GPG/PKI) for tamper-proof artifacts
- Append-only evidence store integration (WORM storage, remote ledger)
- Revert artifact archival (archive before deletion for audit trail)
- RBAC documentation for auditor vs engineer access
