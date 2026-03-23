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

Manual checks:
- [ ] Sample review: inspect 50+ random examples
- [ ] Check for duplicate entries
- [ ] Verify label correctness (for preference/KTO data)

## 6. Data Storage and Retention

- Training data stored in version-controlled or immutable storage
- SHA-256 fingerprint recorded in `data_provenance.json` for every training run
- Retain training data for minimum **5 years** alongside model artifacts
- Access restricted to authorized ML team members

## 7. Review

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [DATE] | [AUTHOR] | Initial version |
