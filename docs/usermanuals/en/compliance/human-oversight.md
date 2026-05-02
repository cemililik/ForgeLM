---
title: Human Oversight
description: Block model promotion until a human reviews and signs off — Article 14 gate.
---

# Human Oversight

EU AI Act Article 14 requires high-risk AI systems to provide for human oversight. ForgeLM implements this as an optional config gate: when `compliance.human_approval: true`, model promotion blocks until a human signs an approval.

## How the gate works

```mermaid
sequenceDiagram
    participant Train as forgelm
    participant Eval as Eval pipeline
    participant Approver as Human approver
    participant Audit as Audit log
    participant Output as Output dir

    Train->>Eval: Training complete, run eval
    Eval->>Eval: Benchmarks + safety pass
    Eval->>Audit: Append "human_approval_request"
    Eval->>Approver: Webhook + structured request
    Approver-->>Eval: Sign approval (CLI / webhook callback)
    Eval->>Audit: Append "human_approval_granted" with signature
    Eval->>Output: Promote checkpoint
```

Without the human signature, the checkpoint stays in a "pending" state and the run exits with code 4 (waiting). It's *not* a failure — it's a controlled hold for review.

## Configuration

```yaml
compliance:
  human_approval: true
  approval:
    request_webhook: "${SLACK_WEBHOOK}"      # optional notification
    signature_method: "cli"                   # cli | webhook | api
    timeout_hours: 48                         # auto-fail after this
    require_role: "ml-compliance-lead"        # who can approve
    quorum: 1                                 # required approvers
```

## Signature methods

### CLI (default)

The trainer halts after eval and prints:

```text
[2026-04-29 14:33:10] Human approval required.
  Run ID: abc123
  Bundle: checkpoints/run/artifacts/

  To approve: forgelm approve abc123 --output-dir checkpoints/run --comment "..."
  To reject:  forgelm reject  abc123 --output-dir checkpoints/run --comment "..."
```

The reviewer runs the approval command from any machine with access to the artifacts directory. ForgeLM verifies their identity via SSH key signing or env-set token, signs the audit log, and resumes promotion.

### Webhook callback

For integration with internal approval systems:

```yaml
approval:
  signature_method: "webhook"
  webhook_url: "https://internal.example/approvals/{run_id}/decide"
```

The trainer halts and posts the artifact bundle to your webhook. Your system handles the human review and POSTs back to ForgeLM's resume endpoint with a signed JWT.

### API

For self-service automation (e.g. a "promote this run" button in your dashboard):

```yaml
approval:
  signature_method: "api"
  resume_token: "${FORGELM_RESUME_TOKEN}"
```

Your dashboard calls ForgeLM's resume endpoint directly with the run ID and reviewer identity. Signatures are recorded in the audit log.

## What's in an approval signature

Every approval (or rejection) appends to `audit_log.jsonl`:

```json
{
  "ts": "2026-04-29T15:18:42Z",
  "seq": 87,
  "event": "human_approval_granted",
  "run_id": "abc123",
  "reviewer": "Cemil Ilik <cemil@example>",
  "role": "ml-compliance-lead",
  "method": "cli",
  "signature": "ed25519:...",
  "comment": "Reviewed safety report; S5 max 0.04 acceptable for this deployment.",
  "artifact_hash": "sha256:..."
}
```

The `signature` is over the artifact bundle's `manifest.json` hash — it certifies the reviewer saw *exactly* what was produced.

## Quorum (multi-reviewer)

For high-risk deployments, require multiple approvers:

```yaml
approval:
  quorum: 2
  require_role: "ml-compliance-lead"
```

Each approver runs the CLI command independently. Promotion happens after the quorum signs (or one of them rejects).

## Timeouts

After `timeout_hours`, an unsigned run auto-fails with exit code 4 + a structured event:

```json
{"event": "human_approval_timeout", "expired_at": "2026-04-30T14:33:10Z"}
```

Default is 48 hours. Set to 0 for "no timeout — wait forever" (not recommended in CI).

## Inspecting pending runs

```shell
$ forgelm approvals --pending
RUN_ID    REQUESTED_AT          ARTIFACTS                                EXPIRES
abc123    2026-04-29T14:33Z     checkpoints/run/artifacts/                in 47h
def456    2026-04-29T09:12Z     checkpoints/sft-only/artifacts/           in 42h
```

```shell
$ forgelm approvals --show abc123
... full artifact summary including audit, benchmarks, safety, model card ...
```

## Common pitfalls

:::warn
**Auto-approving in CI to "unblock the pipeline".** Defeats the purpose of human oversight. If the gate is in your way, you're either over-using it (turn it off for non-high-risk runs) or under-staffing reviewers.
:::

:::warn
**Reviewer rubber-stamping.** A signature must be informed. Display the full artifact summary in the approval flow so the reviewer actually sees what they're signing for.
:::

:::warn
**No quorum for shipping decisions.** For high-risk production deployments, single-reviewer approval is insufficient. Always require quorum >= 2.
:::

:::tip
**Make the approval CLI accessible.** Reviewers shouldn't need to SSH into the training host to approve. Set up the artifacts directory on shared storage so reviewers can run `forgelm approve` from their own machines.
:::

## See also

- [Audit Log](#/compliance/audit-log) — where signatures are recorded.
- [Annex IV](#/compliance/annex-iv) — Section 7 declaration is signed by humans, not the toolkit.
- [Webhooks](#/operations/webhooks) — approval requests can fire Slack/Teams alerts.
