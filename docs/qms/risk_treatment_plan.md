# QMS: Risk Treatment Plan (RTP)

> Quality Management System — [YOUR ORGANIZATION]
> ISO 27001:2022 references: A.5.7, A.5.8, A.5.9, A.5.31, A.6.8, A.8.8, A.8.30
> SOC 2 references: CC3.2, CC3.3, CC9.1, CC9.2

## 1. Purpose

Document the risks ForgeLM-introduced to the deployer's training
pipeline, the treatments ForgeLM ships out-of-the-box, and the
residual risk the deployer accepts or further mitigates.

This is a living document — update it on every quarterly risk review
and after any significant incident (`pipeline.failed`,
`data.erasure_failed`, `audit.classifier_load_failed`,
serious-incident report).

## 2. Methodology

Following ISO 27005 risk-management principles:

- **Likelihood** (L): how often the risk can materialise — `Low`
  (yearly), `Med` (quarterly), `High` (monthly+).
- **Impact** (I): blast radius if it does — `Low` (operator nuisance),
  `Med` (single run / single subject), `High` (regulator-reportable
  incident, model recall).
- **Inherent risk** = L × I before any treatment.
- **Residual risk** = L × I after the treatment ForgeLM ships +
  deployer-side controls.

A residual `High` requires explicit **risk acceptance** by the AI
Officer (see `roles_responsibilities.md`).

## 3. Risk register

Pre-populated with risks ForgeLM's own threat model identifies. The
deployer's compliance team adds organisation-specific rows below
section §4.

### 3.1 Training-pipeline risks

#### R-01 Training-data poisoning (adversarial corpus)

| Field | Value |
|---|---|
| Description | Adversarial actor injects malicious examples into the training corpus to bias model behaviour |
| L × I (inherent) | Med × High = HIGH |
| Treatment | `forgelm audit` PII / secrets / quality scan; `data_audit_report.json` flags severity tiers; deployer pre-flight review of flagged rows; `compute_dataset_fingerprint` SHA-256 stamps "what was trained on" into manifest |
| Residual L × I | Med × Low = MED |
| Owner | Data Steward |
| Review cadence | Per training run (pre-flight) |

#### R-02 Supply-chain compromise (compromised PyPI dependency)

| Field | Value |
|---|---|
| Description | Upstream package on PyPI gains a malicious release; ForgeLM consumes it via pip install |
| L × I (inherent) | Low × High = MED |
| Treatment | SBOM (CycloneDX 1.5) on every release tag; `pip-audit` nightly (Wave 4 / Faz 23); `forgelm doctor` pre-flight env check; pinned upper bounds in `pyproject.toml`; transitive-dep CVE feed |
| Residual L × I | Low × Med = LOW |
| Owner | ML Engineer + Compliance Officer |
| Review cadence | Continuous (nightly) + per-release (SBOM diff) |

#### R-03 Credential leak (HF token / webhook secret in config or audit log)

| Field | Value |
|---|---|
| Description | Operator commits a config with `HF_TOKEN: ghp_...` literal or a webhook URL with embedded credentials |
| L × I (inherent) | Med × Med = MED |
| Treatment | `safe_post` masks Authorization headers in error logs; `forgelm audit --secrets` regex scan flags credentials; `_sanitize_md_list` escapes operator-controlled strings in deployer instructions; `forgelm doctor` pre-flight HF-auth probe; webhook payload-format curation never carries config-derived secrets |
| Residual L × I | Low × Low = LOW |
| Owner | ML Engineer |
| Review cadence | Pre-merge config review |

#### R-04 Audit-log tampering

| Field | Value |
|---|---|
| Description | Adversary with write access to `audit_log.jsonl` rewrites entries to hide a deployment / approve a model that wasn't approved |
| L × I (inherent) | Low × High = MED |
| Treatment | Append-only `O_APPEND` + `flock` + `fsync` per line; HMAC chain (per-line `_hmac` field XOR'd with per-output-dir salt + env secret); SHA-256 prev-hash chain; genesis manifest sidecar (`_check_genesis_manifest` refuses truncate-and-resume); `forgelm verify-audit` validates end-to-end |
| Residual L × I | Low × Low = LOW |
| Owner | AI Officer |
| Review cadence | Continuous (`forgelm verify-audit` cron) |

#### R-05 Memorisation of removed PII (Article 17 erasure incomplete)

| Field | Value |
|---|---|
| Description | Operator runs `forgelm purge --row-id alice@example.com` against the corpus, but the model trained on the row weeks earlier may still reproduce it from learned weights |
| L × I (inherent) | High × Med = HIGH |
| Treatment | `data.erasure_warning_memorisation` audit event raised when the run that consumed the deleted row has a `final_model/` artefact; deployer notifies subject of the residual risk; for high-stakes deployments retrain from scratch |
| Residual L × I | Med × Med = MED |
| Owner | Data Protection Officer (DPO) |
| Review cadence | Per Article 17 request |

### 3.2 Safety + alignment risks

#### R-06 Safety-classifier load failure

| Field | Value |
|---|---|
| Description | Llama Guard / configured safety classifier fails to load (HF Hub down, OOM, version mismatch); ForgeLM proceeds without the gate fired |
| L × I (inherent) | Med × High = HIGH |
| Treatment | F-compliance-110 strict gate: `risk_classification` ∈ `{high-risk, unacceptable}` + `evaluation.safety.enabled: false` raises `ConfigError`; `audit.classifier_load_failed` event records the failure; deployer pipeline halts on non-zero exit |
| Residual L × I | Low × Low = LOW |
| Owner | ML Lead |
| Review cadence | Per training run |

#### R-07 Auto-revert false positive

| Field | Value |
|---|---|
| Description | `evaluation.auto_revert: true` triggers on a transient eval regression; the resulting `pipeline.reverted` looks like a safety failure to a downstream auditor |
| L × I (inherent) | Med × Low = LOW |
| Treatment | `pipeline.reverted` audit event carries the regression delta + threshold; `safety_trend.jsonl` provides cross-run context; deployer dashboard distinguishes "real" reverts from threshold-tuning issues |
| Residual L × I | Low × Low = LOW |
| Owner | ML Lead |
| Review cadence | Weekly trend review |

### 3.3 Webhook + outbound-comms risks

#### R-08 Webhook SSRF / data exfiltration

| Field | Value |
|---|---|
| Description | Adversary configures `webhook.url_env=http://internal-metadata-server/...` to exfiltrate AWS instance credentials |
| L × I (inherent) | Low × Med = LOW |
| Treatment | `safe_post` (Phase 7) — HTTPS-only, SSRF guard rejects RFC 1918 / 169.254.x / loopback / link-local, no redirect-following, masked auth headers in error logs; webhook URL must come from `url_env`, never inline |
| Residual L × I | Low × Low = LOW |
| Owner | Security |
| Review cadence | Per config review |

#### R-09 Webhook target compromised

| Field | Value |
|---|---|
| Description | Operator's Slack / Teams workspace is compromised; attacker reads notify_started payloads and learns model-deployment cadence |
| L × I (inherent) | Low × Low = LOW |
| Treatment | Webhook payload curation never carries raw training data or unredacted PII; `FORGELM_AUDIT_SECRET`-signed payloads detect splicing; deployer rotates webhook secret on incident |
| Residual L × I | Low × Low = LOW |
| Owner | Security + ML Lead |
| Review cadence | Per webhook-target incident |

### 3.4 ReDoS + ingestion risks

#### R-10 ReDoS via `--type custom` regex (reverse-pii)

| Field | Value |
|---|---|
| Description | Operator-supplied regex on `forgelm reverse-pii --type custom --query "(a+)+$"` triggers catastrophic backtracking |
| L × I (inherent) | Low × Low = LOW |
| Treatment | POSIX SIGALRM 30s per-file budget in `_scan_file_with_alarm` (Faz 38 / Wave 3 followup F-W3FU-T-01); thread-safety guard skips non-main thread; outer alarm preserved |
| Residual L × I | Low × Low = LOW |
| Owner | Security |
| Review cadence | Wave 3 closed; no further action |

#### R-11 Cross-tool digest mismatch (purge ↔ reverse-pii)

| Field | Value |
|---|---|
| Description | `forgelm purge` runs with one salt; `forgelm reverse-pii` for the same identifier runs with another (e.g. `FORGELM_AUDIT_SECRET` change between runs) — digest doesn't match, audit chain looks inconsistent |
| L × I (inherent) | Low × Med = LOW |
| Treatment | `salt_source` recorded in every audit event (Wave 3 followup F-W3-PS-07); explicit `--salt-source per_dir` honoured even when env secret set; cross-tool correlation test (`test_purge_target_id_matches_reverse_pii_query_hash_on_same_output_dir`) pinned in CI |
| Residual L × I | Low × Low = LOW |
| Owner | DPO |
| Review cadence | Per Article 15/17 request |

### 3.5 Deployment risks

#### R-12 Unauthorised model deployment

| Field | Value |
|---|---|
| Description | Operator skips human approval; high-risk model reaches production without ML Lead / AI Officer sign-off |
| L × I (inherent) | Med × High = HIGH |
| Treatment | `evaluation.require_human_approval: true` for `risk_classification` ∈ `{high-risk, unacceptable}`; staging directory holds the model until `forgelm approve`; F-compliance-110 raises ConfigError if not configured; `human_approval.required/granted/rejected` chain forensically records every decision |
| Residual L × I | Low × Med = LOW |
| Owner | ML Lead + AI Officer |
| Review cadence | Per training run for high-risk |

## 4. Deployer-specific rows

[Add rows here for organisation-specific risks not anticipated by
ForgeLM's own threat model — e.g. industry-specific regulator
requirements, third-party legal commitments, integration-specific
risks. Use the same field structure as §3.]

## 5. Risk acceptance log

When a residual risk is `Med` or `High`, the AI Officer must sign
acceptance:

| Risk ID | Inherent | Residual | Accepted by | Date | Justification |
|---|---|---|---|---|---|
| R-05 | HIGH | MED | [AI Officer] | [DATE] | Memorisation residual risk acknowledged; deployer policy: notify subject + retrain from scratch for high-stakes deployments |
| ... | ... | ... | ... | ... | ... |

## 6. Review

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [DATE] | [AUTHOR] | Initial version (Wave 4 / Faz 23) — 12 ForgeLM-identified risks |

Quarterly review cadence:

- Re-score each row's L × I against the past quarter's incident
  frequency.
- Add new rows for deployer-specific risks identified in retro.
- Confirm residual-risk acceptance log is current.
