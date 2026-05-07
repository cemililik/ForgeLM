---
title: Audit Log
description: Append-only event log over training, evaluation, and revert decisions — Article 12.
---

# Audit Log

EU AI Act Article 12 requires high-risk AI systems to maintain logs of operationally relevant events. ForgeLM's `audit_log.jsonl` is an append-only, SHA-256-anchored sequence of events covering training start, evaluation gates, auto-revert decisions, and model export.

## Format

One JSON object per line:

```jsonl
{"ts":"2026-04-29T14:01:32Z","seq":1,"event":"run_start","run_id":"abc123","config_hash":"sha256:dead..."}
{"ts":"2026-04-29T14:01:35Z","seq":2,"event":"data_audit_complete","verdict":"clean","..."}
{"ts":"2026-04-29T14:18:55Z","seq":3,"event":"training_epoch_complete","epoch":1,"loss":1.42}
{"ts":"2026-04-29T14:33:04Z","seq":4,"event":"benchmark_complete","verdict":"pass"}
{"ts":"2026-04-29T14:33:08Z","seq":5,"event":"safety_eval_complete","verdict":"pass"}
{"ts":"2026-04-29T14:33:10Z","seq":6,"event":"run_complete","exit_code":0,"prev_hash":"sha256:beef..."}
```

Every entry has:
- **`ts`** — ISO-8601 UTC timestamp.
- **`seq`** — monotonic sequence number within the run (resets per-run).
- **`event`** — event type (see below).
- **`prev_hash`** — SHA-256 of the previous entry (chained for tamper-evidence).
- Event-specific fields.

## Event types

| Event | When emitted |
|---|---|
| `run_start` | At the start of every `forgelm` invocation. |
| `training.started` | Trainer enters fine-tuning. |
| `pipeline.completed` | End-to-end CLI run returned exit code 0. |
| `pipeline.failed` | Pipeline aborted with an error. |
| `model.reverted` | Auto-revert restored a previous checkpoint after a quality regression. |
| `human_approval.required` | `evaluation.require_human_approval=true` paused the run for an operator decision. |
| `human_approval.granted` | Operator approved a paused gate via `forgelm approve`. |
| `human_approval.rejected` | Operator rejected a paused gate via `forgelm reject`. |
| `audit.classifier_load_failed` | Safety classifier (e.g. Llama Guard) failed to load. |
| `compliance.governance_exported` | EU AI Act Article 10 governance report written. |
| `compliance.artifacts_exported` | Annex IV bundle (manifest + model card + audit zip) written. |
| `data.erasure_*` | Six-event family covering `forgelm purge` lifecycle (Article 17). |
| `data.access_request_query` | `forgelm reverse-pii` invocation (GDPR Article 15). |
| `cli.legacy_flag_invoked` | A deprecated CLI flag was used. |

The full event catalog (with payload schema and emitting site) lives in
[`docs/reference/audit_event_catalog.md`](#/reference/audit-event-catalog).

## Append-only by design

ForgeLM never rewrites prior log entries. New events go at the end. The chained `prev_hash` makes any modification detectable: if you change entry N, every entry from N+1 onwards has wrong `prev_hash` references.

:::warn
**Convention, not enforcement.** The toolkit writes append-only and hashes the chain, but the file lives on your filesystem — anyone with write access can edit it. For real tamper-evidence, ship the log to a separate write-once store (S3 Object Lock, ledger DB, HSM). This is your operational responsibility.
:::

## Verifying integrity

```shell
$ forgelm verify-audit checkpoints/run/artifacts/audit_log.jsonl
✓ 87 entries, all timestamps monotonic
✓ all prev_hash chains valid
✓ no gaps in seq numbers
```

If `verify-audit` reports a chain break, the log was modified after generation. Investigate before treating it as evidence.

## Per-run vs per-project

Each training run produces its own `audit_log.jsonl` in that run's `artifacts/` directory. For per-project history, ForgeLM also maintains `.forgelm/global-audit-log.jsonl` at the project root (gitignored by default — opt in to commit).

The global log records *cross-run* events:

- `run_start` and `run_complete` for every run in the project.
- Manual model promotions and rollbacks.
- Configuration changes (when `forgelm` detects new YAML versions).

## Configuration

```yaml
compliance:
  audit_log:
    enabled: true
    path: "${output.dir}/artifacts/audit_log.jsonl"
    step_milestone_interval: 1000             # log step events every N steps
    include_config_dump: true                  # emit full config in run_start event
    redact_secrets: true                       # mask api keys in dumped config
```

## Forwarding to external stores

For tamper-evidence in production, forward log entries to a separate write-once or append-only store:

```yaml
compliance:
  audit_log:
    forward_to:
      - type: "s3"
        bucket: "compliance-audit-logs"
        prefix: "forgelm/{run_id}/"
        object_lock: true
      - type: "syslog"
        host: "audit.internal:514"
        protocol: "tcp"
```

ForgeLM mirrors every emitted event to the configured destinations. If the external store is unreachable, the run fails (don't silently drop audit events).

## Reading the log

For human review:

```shell
$ jq -r '.event + "\t" + .ts' checkpoints/run/artifacts/audit_log.jsonl
run_start                  2026-04-29T14:01:32Z
config_validated           2026-04-29T14:01:33Z
data_audit_complete        2026-04-29T14:01:35Z
training_epoch_complete    2026-04-29T14:18:55Z
...
run_complete               2026-04-29T14:33:10Z
```

For dashboards, the JSONL flows naturally into Loki, OpenSearch, or any log-aggregation tool.

## Common pitfalls

:::warn
**Editing the log "to fix a typo".** Don't. Even cosmetic edits break the chain hash and undermine the audit value. If you genuinely need to amend information, append a new event of type `correction` with a `corrects_seq` reference.
:::

:::warn
**Storing the log only on training-host disks.** A failed disk = lost audit evidence. Always forward to durable storage (S3 with versioning + Object Lock, ledger DB).
:::

:::tip
**Chain logs across runs in production.** When promoting a checkpoint to production, append a `model_promoted` event referencing the previous version. Auditors love a continuous chain of custody from training to deployment.
:::

## See also

- [Annex IV](#/compliance/annex-iv) — the technical doc that points at the audit log.
- [Auto-Revert](#/evaluation/auto-revert) — produces the `auto_revert` events.
- [Human Oversight](#/compliance/human-oversight) — produces the approval events.
