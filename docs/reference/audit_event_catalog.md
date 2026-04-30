# Audit Event Catalog

> **Audience:** ForgeLM operators, regulators, and downstream verifiers reviewing the EU AI Act Article 12 record-keeping artefacts.
> **Mirror:** [audit_event_catalog-tr.md](audit_event_catalog-tr.md)

This catalog enumerates every event ForgeLM may append to `audit_log.jsonl`, the append-only, hash-chained record-keeping artefact mandated by EU AI Act Article 12. Every entry shares a common envelope; the `event` field selects one of the rows below.

## Common envelope

Each line is a single JSON object with at least the following fields:

| Field         | Type    | Description                                                                                               |
|---------------|---------|-----------------------------------------------------------------------------------------------------------|
| `timestamp`   | string  | ISO-8601 UTC timestamp (`datetime.now(timezone.utc).isoformat()`).                                        |
| `run_id`      | string  | Stable per-training-run identifier (`fg-<uuid12>`).                                                       |
| `operator`    | string  | Human-attributable identity. From `$FORGELM_OPERATOR`, else `<getpass.getuser()>@<hostname>`.             |
| `event`       | string  | Dotted event name from this catalog.                                                                      |
| `prev_hash`   | string  | SHA-256 of the previous line (`"genesis"` for the first entry). Forms the tamper-evident hash chain.      |
| `_hmac`       | string? | Present only when `FORGELM_AUDIT_SECRET` is set. HMAC-SHA-256 of the line without `_hmac`.                |
| _payload_     | varies  | Event-specific keys, listed per row below.                                                                |

The hash chain advances after the line lands on disk (`flush` + `fsync`), so an unclean shutdown leaves the chain intact for resume.

## Event vocabulary

### Pipeline lifecycle

| Event                      | When emitted                                                              | Payload (in addition to envelope)                                                        | Article |
|----------------------------|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------|---------|
| `training.started`         | Trainer begins a fine-tuning run.                                         | `trainer_type`, `model`, `dataset`, `config_path`                                        | 12      |
| `training.completed`       | Fine-tuning finishes successfully (post evaluation gates).                | `eval_loss`, `safety_passed`, `judge_score`                                              | 12      |
| `training.failed`          | Trainer aborted with an error before completion.                          | `failure_reason`, `stage`                                                                | 12      |
| `pipeline.completed`       | End-to-end CLI run (training + evaluation + export) returned exit code 0. | `exit_code`, `duration_seconds`                                                          | 12      |

### Article 14 — Human Oversight

| Event                        | When emitted                                                                                            | Payload                                              | Article |
|------------------------------|---------------------------------------------------------------------------------------------------------|------------------------------------------------------|---------|
| `human_approval.required`    | A gate marked `requires_human_approval: true` paused the pipeline awaiting an operator decision.        | `gate`, `reason`, `metrics`                          | 14      |
| `human_approval.granted`     | Operator approved the paused gate. _(Faz 9 — placeholder; not yet emitted.)_                            | `gate`, `approver`, `comment`                        | 14      |
| `human_approval.rejected`    | Operator rejected the paused gate. _(Faz 9 — placeholder; not yet emitted.)_                            | `gate`, `approver`, `comment`                        | 14      |

### Article 15 — Model Integrity (auto-revert + safety)

| Event                          | When emitted                                                                                              | Payload                                                       | Article |
|--------------------------------|-----------------------------------------------------------------------------------------------------------|---------------------------------------------------------------|---------|
| `model.reverted`               | Auto-revert restored a previous checkpoint after a quality regression. _(Faz 8 — webhook-coupled.)_       | `from_checkpoint`, `to_checkpoint`, `reason`, `metrics_delta` | 15      |
| `audit.classifier_load_failed` | Safety classifier (e.g., Llama Guard) failed to load. The run still records `passed=False`.              | `classifier`, `reason`                                        | 15      |

### Article 11 + Annex IV — Compliance artefacts

| Event                            | When emitted                                                                | Payload                                          | Article    |
|----------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------|------------|
| `compliance.governance_exported` | Article 10 data governance report written to disk.                          | `output_path`, `dataset_count`                   | 10         |
| `compliance.governance_failed`   | Governance report generation aborted (e.g., schema mismatch).               | `failure_reason`                                 | 10         |
| `compliance.artifacts_exported`  | Annex IV technical documentation bundle (manifest, model card, audit zip). | `output_dir`, `files`                            | 11, Annex IV |

### CLI / migration

| Event                       | When emitted                                                                                       | Payload                          | Article |
|-----------------------------|----------------------------------------------------------------------------------------------------|----------------------------------|---------|
| `cli.legacy_flag_invoked`   | A deprecated CLI flag was used. _(Faz 13 — placeholder; not yet emitted.)_                         | `flag`, `replacement`, `version` | 12      |

### Audit-system events (meta)

| Event                          | When emitted                                                                                      | Payload                              | Article |
|--------------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------|---------|
| `audit.classifier_load_failed` | _(See Article 15 row above.)_                                                                     | `classifier`, `reason`               | 15      |
| `audit.cross_run_continuity`   | First write of a second-or-later AuditLogger instance pointing at an existing log directory.      | `previous_chain_head`                | 12      |

## Webhook events

Webhook payloads (Slack / Teams) are a separate vocabulary scoped to operator notifications, not the regulatory record. They are _extended in Faz 8_ — see [logging-observability.md](../standards/logging-observability.md) for the canonical list. Webhook events are **not** appended to `audit_log.jsonl`; they ride the side-channel notification bus.

## Adding a new event

1. Pick a dotted name following the existing namespaces (`training.*`, `compliance.*`, `audit.*`, `human_approval.*`, `model.*`, `cli.*`).
2. Add a row to the table above, including the payload keys and the Article it supports.
3. Mirror the row to [audit_event_catalog-tr.md](audit_event_catalog-tr.md).
4. Emit via `AuditLogger.log_event(event, **payload)`. Never call `json.dump` directly into `audit_log.jsonl`; the hash chain depends on the canonical writer.

## Tamper-evidence summary

| Mechanism                | Defends against                                                       | Always on?                                           |
|--------------------------|-----------------------------------------------------------------------|------------------------------------------------------|
| SHA-256 hash chain       | Single-line edits, deletions, reorderings.                            | Yes.                                                 |
| Genesis manifest sidecar | Whole-log truncation back to "genesis".                               | Yes (written once on first event).                   |
| `flock(LOCK_EX)`         | Interleaved writes from concurrent trainers sharing the directory.    | Yes (Unix); no-op on Windows.                        |
| `flush` + `fsync`        | Power-cut / kernel-panic loss between buffer write and chain advance. | Yes.                                                 |
| HMAC-SHA-256 per line    | Forged re-signing after log rewrite.                                  | Only when `FORGELM_AUDIT_SECRET` is set.             |

## Webhook events

These five lifecycle events are the **only** events that webhook
receivers (Slack, Teams, generic HTTP) should expect from
`WebhookNotifier`. Each one mirrors a corresponding audit-log event so
a downstream operator can correlate webhook ping → audit entry by
`run_name` + timestamp. Implementation: `forgelm/webhook.py`.

| Webhook `event` | Audit-log mirror | Trigger | Gated by | Required payload fields |
|---|---|---|---|---|
| `training.start` | `training.started` | `train()` entered, before model load. | `webhook.notify_on_start` | `run_name`, `status="started"` |
| `training.success` | `pipeline.completed` | All gates passed, no human-approval requirement. | `webhook.notify_on_success` | `run_name`, `status="succeeded"`, `metrics` |
| `training.failure` | `pipeline.failed` | Training itself raised (OOM, dataset error, unhandled exception). | `webhook.notify_on_failure` | `run_name`, `status="failed"`, `reason` (masked, ≤2048 chars) |
| `training.reverted` | `model.reverted` | A post-training gate (evaluation, safety, judge, benchmark) rejected the run and `_revert_model` deleted the adapters. | `webhook.notify_on_failure` | `run_name`, `status="reverted"`, `reason` (masked, ≤2048 chars) |
| `approval.required` | `human_approval.required` | Run succeeded, `evaluation.require_human_approval=true`, model staged for review (EU AI Act Art. 14). | `webhook.notify_on_success` | `run_name`, `status="awaiting_approval"`, `model_path` |

### Why two of these split lifecycle states

- **`training.failure` vs `training.reverted`** — dashboards need to tell
  "the trainer crashed" apart from "the trainer succeeded, but the
  quality / safety / judge gate said no". Both are operationally
  actionable, but they require different runbooks. Faz 8 introduced
  `notify_reverted` precisely so a Slack channel can colour-code the two
  cases differently (`#ff0000` vs `#ff9900`).
- **`approval.required`** — fires *after* the run succeeded but *before*
  the operator has approved deploy. It is not a failure; it is a pause.
  Receivers that auto-page on `training.failure` should **not** page on
  `approval.required`.

### Payload schema

Every webhook event ships the same envelope:

```json
{
  "event": "training.start | training.success | training.failure | training.reverted | approval.required",
  "run_name": "<string>",
  "status": "started | succeeded | failed | reverted | awaiting_approval",
  "metrics": {"<name>": <number>, ...},
  "reason": "<masked string or null>",
  "model_path": "<filesystem path or null>",
  "attachments": [{"title": "...", "text": "...", "color": "..."}]
}
```

`metrics`, `reason`, and `model_path` are always present in the schema;
only populated for the events that need them. `attachments` is the
Slack-compatible block — other receivers may ignore it.

### Security guarantees

1. **Reasons are masked.** Every `reason` field passes through
   `forgelm.data_audit.mask_secrets` before transport, so AWS / GitHub /
   Slack / OpenAI / Google / JWT / private-key blocks / Azure storage
   strings do not leave the process. If `data_audit` cannot be imported,
   the field is replaced with `"[REDACTED — secrets masker unavailable]"`
   rather than the raw string.
2. **Reasons are truncated to 2048 chars.** Stack traces longer than
   that are clipped with `"… (truncated)"`.
3. **No model weights.** `approval.required` carries the staging
   filesystem path only. Weights stay on disk; the operator already
   controls that directory.
4. **No webhook URL leakage.** URLs are masked in logs (`scheme://host/<first-segment>/...`)
   and the response body is suppressed on non-2xx.
5. **SSRF guard.** Private / loopback / link-local destinations are
   refused unless `webhook.allow_private_destinations=true`.

### Retention guidance

Webhook payloads are **transient**. They are not the audit record.
Receivers that need long-term history should snapshot the audit JSONL
(`<output_dir>/compliance/audit.jsonl`) rather than archiving webhook
traffic, because the audit log is the append-only hash-chained record
and the webhook stream is best-effort.
