---
title: Annex IV
description: The EU AI Act Article 11 technical documentation, auto-populated from your training run.
---

# Annex IV

Annex IV of the EU AI Act (Regulation (EU) 2024/1689) defines the eight-section technical documentation required for high-risk AI systems. ForgeLM produces this artifact automatically — `artifacts/annex_iv.json` after every run with `compliance.annex_iv: true`.

## The eight sections

| § | Section | What ForgeLM auto-populates |
|---|---|---|
| 1 | General description | Model name, intended purpose, geographies, version. |
| 2 | Detailed system description | Base model, trainer (SFT/DPO/...), dataset summary. |
| 3 | Monitoring | Eval thresholds, auto-revert triggers, trend tracking config. |
| 4 | Risk management | Risk classification, mitigations applied, residual risks. |
| 5 | Lifecycle | Training timestamp, dataset versions, source references. |
| 6 | Harmonised standards | Listed compliance frameworks (EU AI Act, GDPR, ISO 27001). |
| 7 | EU declaration of conformity | Scaffold; signed by a human as final step. |
| 8 | Post-market monitoring plan | Reference to deployment surveillance config. |

## Configuration → Annex IV

Most of Annex IV is filled from your `compliance:` YAML block. Required fields:

```yaml
compliance:
  annex_iv: true                                  # master switch

  # Section 1: General description
  intended_purpose: "Multilingual customer-support assistant for telecom"
  deployment_geographies: ["TR", "EU"]
  responsible_party: "Acme Corp <compliance@acme.example>"
  version: "1.2.0"

  # Section 4: Risk classification
  risk_classification: "high-risk"                # or "minimal", "limited"
  risk_assessment:
    foreseeable_misuse:
      - "Customer impersonation in social engineering attacks"
      - "Generation of fraudulent invoices"
    mitigations:
      - "Llama Guard S5 (defamation) gate enforced"
      - "PII masked at ingest"
    residual_risks:
      - "Adversarial jailbreaks against system prompt"

  # Section 6: Standards
  standards: ["EU AI Act", "GDPR", "ISO 27001"]

  # Section 8: Post-market plan reference
  post_market_plan: "https://internal.acme.example/forgelm-monitoring"
```

The audit step ([Dataset Audit](#/data/audit)) provides Section 2's dataset summary and Section 5's data lineage automatically.

## Output structure

`annex_iv.json` follows the EU AI Act schema closely:

```json
{
  "schema_version": "annex_iv/1.0",
  "section_1_general_description": {
    "name": "Acme Customer Support v1.2.0",
    "intended_purpose": "...",
    "deployment_geographies": ["TR", "EU"],
    "responsible_party": "Acme Corp <compliance@acme.example>",
    "version": "1.2.0"
  },
  "section_2_detailed_system_description": {
    "base_model": "Qwen/Qwen2.5-7B-Instruct",
    "trainer": "dpo",
    "datasets": [{
      "path": "data/preferences.jsonl",
      "row_count": 12400,
      "audit_report": "audit/data_audit_report.json",
      "source_documents": "data/sources.json"
    }],
    "training_recipe": "configs/customer-support.yaml"
  },
  "section_3_monitoring": {
    "benchmark_floors": {"hellaswag": 0.55, "...": "..."},
    "safety_thresholds": {"S5": 0.30, "...": "..."},
    "trend_tracking": true
  },
  "section_4_risk_management": {
    "classification": "high-risk",
    "foreseeable_misuse": [...],
    "mitigations": [...],
    "residual_risks": [...]
  },
  "section_5_lifecycle": {
    "trained_at": "2026-04-29T14:01:32Z",
    "training_duration_seconds": 1892,
    "config_hash": "sha256:deadbeef...",
    "dataset_hashes": {...}
  },
  "section_6_harmonised_standards": ["EU AI Act", "GDPR", "ISO 27001"],
  "section_7_declaration_of_conformity": {
    "status": "scaffold",
    "signed_by": null,
    "signed_at": null,
    "notes": "Requires human review and signature before submission."
  },
  "section_8_post_market_plan": "https://internal.acme.example/forgelm-monitoring",
  "manifest_sha256": "..."
}
```

## Tamper-evidence

`annex_iv.json` is itself hashed in `manifest.json`, alongside every other artifact in the bundle. The manifest is the canonical pointer to the immutable bundle:

```json
{
  "schema": "manifest/1.0",
  "artifacts": {
    "annex_iv.json": "sha256:abc123...",
    "audit_log.jsonl": "sha256:def456...",
    "data_audit_report.json": "sha256:789abc...",
    "safety_report.json": "sha256:fedcba...",
    "benchmark_results.json": "sha256:111222..."
  },
  "generated_at": "2026-04-29T14:33:04Z"
}
```

For real tamper-evidence, ship `manifest.json` to a separate write-once store (S3 Object Lock, HSM-signed ledger, etc.). The toolkit produces the artefact; the operational chain-of-custody is your responsibility.

## Validating Annex IV

Before treating an Annex IV as "audit-ready", verify the schema:

```shell
$ forgelm verify-annex-iv checkpoints/run/artifacts/annex_iv.json
✓ schema valid
✓ all required fields present
✓ manifest checksums match
⚠ section_7 declaration unsigned (expected for new runs)
```

The `forgelm verify-annex-iv` command also re-computes manifest hashes and checks for tampering since generation.

## Common pitfalls

:::warn
**Skipping the human review step on Section 7.** The declaration of conformity is a legal document. The auto-generated scaffold is not signed and has no legal effect — a human must review and sign before submission.
:::

:::warn
**Treating ForgeLM's output as a certification.** ForgeLM produces evidence; certification is a notified-body activity. The terminology in our docs reflects this: "Annex-IV-style artifact", "scaffold", "evidence bundle" — never "certified".
:::

:::tip
For high-risk deployments, version the Annex IV artifact alongside model versions in your model registry. Auditors expect to see Annex IV per release, not per training run.
:::

## See also

- [Compliance Overview](#/compliance/overview) — context for the rest of the bundle.
- [Audit Log](#/compliance/audit-log) — append-only event log.
- [Human Oversight](#/compliance/human-oversight) — Article 14.
