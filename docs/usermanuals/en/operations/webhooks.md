---
title: Webhooks
description: Slack and Teams notifications on training events — start, success, failure, auto-revert.
---

# Webhooks

ForgeLM fires structured webhooks on training milestones. Wire them into Slack, Teams, or any incident tool that accepts JSON payloads — get the right context to the right humans without anyone watching a log.

## Quick example

```yaml
output:
  webhook:
    url: "${SLACK_WEBHOOK}"
    events: ["run_start", "auto_revert", "run_complete", "run_failed"]
    template: "slack"                      # or teams, generic
```

ForgeLM picks up `${SLACK_WEBHOOK}` from environment variables. Common pattern:

```shell
$ export SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../..."
$ forgelm --config configs/run.yaml
```

## Events you can subscribe to

| Event | When fired |
|---|---|
| `run_start` | Training kicks off. |
| `data_audit_complete` | After `forgelm audit`. |
| `training_epoch_complete` | After each epoch. (verbose; usually skipped) |
| `benchmark_complete` | After eval suite. |
| `safety_eval_complete` | After Llama Guard scoring. |
| `auto_revert` | When auto-revert triggers. |
| `human_approval_request` | When `compliance.human_approval` blocks. |
| `human_approval_granted` | When approval is signed. |
| `model_exported` | After `forgelm export`. |
| `run_complete` | Successful exit. |
| `run_failed` | Non-zero exit. |

Subscribe selectively — too-frequent webhooks become spam.

## Payload shape

Generic format (the `slack` and `teams` templates wrap this in their respective formats):

```json
{
  "event": "auto_revert",
  "ts": "2026-04-29T14:33:04Z",
  "run_id": "abc123",
  "config_path": "configs/customer-support.yaml",
  "trigger": "safety_regression",
  "regressed_categories": ["S5"],
  "details": {...},
  "artifacts_url": "https://compliance-store.example/abc123/"
}
```

## Slack template

```yaml
output:
  webhook:
    url: "${SLACK_WEBHOOK}"
    template: "slack"
    events: ["run_complete", "run_failed", "auto_revert"]
    channel: "#ml-training"                 # optional override
    mention_on_failure: "@ml-oncall"
```

Produces:

```text
🔥 ForgeLM auto-revert triggered

Run: customer-support v1.2.0 (abc123)
Trigger: safety_regression in S5
Restored from: checkpoints/sft-base
Audit log: artifacts/audit_log.jsonl

@ml-oncall please investigate.
```

## Microsoft Teams template

```yaml
output:
  webhook:
    url: "${TEAMS_WEBHOOK}"
    template: "teams"
    events: ["auto_revert", "human_approval_request"]
```

Produces a Teams MessageCard with the same data formatted as a card with action buttons.

## Generic template (custom integrations)

For your own dashboard, incident system, or pipeline:

```yaml
output:
  webhook:
    url: "https://internal.example/forgelm-events"
    template: "generic"
    events: ["run_start", "run_complete", "run_failed", "auto_revert"]
    headers:
      Authorization: "Bearer ${INCIDENT_API_TOKEN}"
    timeout_seconds: 5
    retries: 3
```

The endpoint receives the raw structured payload above. ForgeLM POSTs JSON, expects 2xx, retries on transient failures.

## Multiple destinations

To send different events to different places:

```yaml
output:
  webhooks:
    - url: "${SLACK_WEBHOOK}"
      template: "slack"
      events: ["run_complete", "run_failed"]
    - url: "${PAGERDUTY_WEBHOOK}"
      template: "generic"
      events: ["auto_revert"]                # critical only
    - url: "${INTERNAL_DASHBOARD_URL}"
      template: "generic"
      events: ["*"]                          # everything for the dashboard
```

## Security considerations

- **TLS only.** ForgeLM rejects HTTP webhook URLs in production builds.
- **Sensitive data redaction.** API keys, full configs, and PII in payloads are redacted by default. Override with `webhook.redact: false` only if you control both endpoints.
- **Server-Side Request Forgery (SSRF) guard.** ForgeLM blocks webhook URLs pointing at internal IPs (RFC 1918, link-local) unless you explicitly allow them with `webhook.allow_private: true`. This prevents misconfigured runs from probing your internal network.

## Common pitfalls

:::warn
**Webhook silently failing.** A 4xx response from the webhook endpoint shouldn't fail the training run, but ForgeLM also shouldn't silently swallow the error. Check `audit_log.jsonl` for `webhook_failed` events; investigate why your endpoint rejected.
:::

:::warn
**Subscribing to `training_epoch_complete`.** For a 50-epoch training run, that's 50 messages — Slack will rate-limit you. Use `run_start` and `run_complete` for the bookends.
:::

:::tip
**Test webhooks with `--webhook-test`.** Before going live, run `forgelm --config X.yaml --webhook-test` — it fires a synthetic payload to your webhook so you can verify the formatting. No actual training happens.
:::

## See also

- [CI/CD Pipelines](#/operations/cicd) — the natural home of webhooks.
- [Auto-Revert](#/evaluation/auto-revert) — produces the most actionable webhook.
- [Human Oversight](#/compliance/human-oversight) — webhook-driven approval flow.
