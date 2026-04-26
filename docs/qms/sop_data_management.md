# SOP: Data Management and Governance

> Standard Operating Procedure — [YOUR ORGANIZATION]
> EU AI Act Reference: Article 17(1)(f), Article 10

## 1. Purpose

Define standards for collecting, annotating, storing, and governing training data for LLM fine-tuning.

## 2. Scope

All datasets used for model training, validation, and evaluation.

## 3. Roles

| Role | Responsibility |
|------|---------------|
| **Data Steward** | Data quality oversight, governance compliance |
| **ML Engineer** | Data preparation, preprocessing, format validation |
| **DPO (Data Protection Officer)** | Personal data assessment, DPIA review |

## 4. Data Collection

### 4.1 Requirements

- [ ] Document data source and collection method in config:
  ```yaml
  data:
    governance:
      collection_method: "Manual curation from internal knowledge base"
  ```
- [ ] Assess representativeness: does the data reflect the intended deployment context?
- [ ] Check for geographical, demographic, and contextual balance
- [ ] Document known biases in config:
  ```yaml
  data:
    governance:
      known_biases: "Dataset skewed toward English-speaking customers in EU region"
  ```

### 4.2 Personal Data

- [ ] Determine if dataset contains personal data
- [ ] If yes: complete Data Protection Impact Assessment (DPIA)
- [ ] Document in config:
  ```yaml
  data:
    governance:
      personal_data_included: true
      dpia_completed: true
  ```
- [ ] Ensure data minimization — only include necessary personal data
- [ ] Apply anonymization/pseudonymization where possible

## 5. Data Preparation

### 5.1 Annotation

- [ ] Document annotation process:
  ```yaml
  data:
    governance:
      annotation_process: "Two annotators per sample, adjudication by senior annotator"
  ```
- [ ] Maintain inter-annotator agreement records
- [ ] Version control annotation guidelines

### 5.2 Quality Checks

ForgeLM automated checks:
- Dataset fingerprinting (SHA-256 hash, size, timestamp)
- Format validation per trainer type (SFT, DPO, KTO, GRPO)
- Text cleaning (`clean_text: true`)
- **Audit pipeline (`forgelm --data-audit <jsonl>`, v0.5.0+)** — produces
  `data_audit_report.json` with per-split sample counts, length distribution,
  top-3 language detection, simhash near-duplicate rate, cross-split
  leakage check, and PII flag counts (email / phone / Luhn-validated credit
  card / IBAN / TR–DE–FR–US national IDs). The report is auto-inlined into
  the EU AI Act Article 10 governance artifact when present in the trainer's
  `output_dir` — operators must run the audit **before** training to keep
  the bundle self-contained.
- **Ingestion pipeline (`forgelm ingest`, v0.5.0+)** — turns raw PDF / DOCX /
  EPUB / TXT / Markdown into SFT-ready JSONL with optional `--pii-mask` to
  redact detected PII spans before chunks reach storage.

Manual checks:
- [ ] Run `forgelm --data-audit` and review `data_audit_report.json` for:
  cross-split leakage > 0%, near-duplicate rate, unexpected language mix,
  PII flag counts.
- [ ] Sample review: inspect 50+ random examples.
- [ ] Verify label correctness (for preference/KTO data).

## 6. Data Storage and Retention

- Training data stored in version-controlled or immutable storage
- SHA-256 fingerprint recorded in `data_provenance.json` for every training run
- Retain training data for minimum **5 years** alongside model artifacts
- Access restricted to authorized ML team members

## 7. Review

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [DATE] | [AUTHOR] | Initial version |
