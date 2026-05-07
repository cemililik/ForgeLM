# `forgelm approvals` — Subcommand Reference

> **Audience:** ForgeLM operators discovering runs awaiting an Article 14 human-approval decision, plus auditors reading the audit chain for a single run end-to-end.
> **Mirror:** [approvals_subcommand-tr.md](approvals_subcommand-tr.md)

`forgelm approvals` is the **discovery counterpart** to [`forgelm approve` / `forgelm reject`](approve_subcommand.md) (Phase 37). It scans `audit_log.jsonl` under `--output-dir` and reports either every run pending a decision (`--pending`) or the full audit chain for one run (`--show RUN_ID`).

The subcommand is read-only: it never modifies the audit log, the staging directory, or any other on-disk artefact.

## Synopsis

```text
forgelm approvals --pending --output-dir DIR
                  [--output-format {text,json}]

forgelm approvals --show RUN_ID --output-dir DIR
                  [--output-format {text,json}]
```

`--pending` and `--show` are mutually exclusive (argparse enforces). Exactly one must be present.

| Argument / flag | Required | Description |
|---|---|---|
| `--pending` | one of | List every run whose audit log carries a `human_approval.required` event without a matching terminal decision (`granted` / `rejected`). |
| `--show RUN_ID` | one of | Print the full approval-gate audit chain (request → decision) plus the on-disk staging directory layout for one run. |
| `--output-dir DIR` | yes | Training output directory containing `audit_log.jsonl` and the per-run `final_model.staging.<run_id>/` payload (the trainer emits the run-id-suffixed form; an older run-id-less `final_model.staging/` layout is honoured as a backwards-compat fallback). |
| `--output-format {text,json}` | no (default `text`) | `json` prints exactly one structured object on stdout for CI consumers. |

## What `--pending` does

Implemented in `forgelm.cli.subcommands._approvals._run_approvals_list_pending`:

1. Verifies `audit_log.jsonl` exists and is readable (delegates to the same `_assert_audit_log_readable_or_exit` helper as `forgelm approve`).
2. Walks the chain looking for `human_approval.required` events.
3. For each such event, scans for a later terminal decision (`granted` / `rejected`) on the same `run_id`. Runs without a terminal decision are flagged as pending.
4. Prints a table with `RUN_ID`, `AGE` (relative to now), `REQUESTED_AT` (ISO-8601), `STAGING` (present / missing).

Sample text output:

```text
Pending approvals (2):

RUN_ID            AGE   REQUESTED_AT               STAGING
----------------  ----  -------------------------  -------
fg-abc123def456   3h    2026-04-30T11:33:10+00:00  present
fg-def456abc789   1d    2026-04-29T14:12:55+00:00  present
```

Sample JSON envelope (per-summary fields built by `_summarise_pending`):

```json
{
  "success": true,
  "pending": [
    {
      "run_id": "fg-abc123def456",
      "staging_path": "outputs/run42/final_model.staging.fg-abc123def456",
      "staging_exists": true,
      "requested_at": "2026-04-30T11:33:10+00:00",
      "age_seconds": 11340,
      "metrics": {"safety_score": 0.97, "judge_score": 8.4},
      "config_hash": null,
      "reason": "require_human_approval=true"
    }
  ],
  "count": 1
}
```

Field notes:
- `age_seconds` is an integer (clock skew defends — never negative; the text renderer formats it as `3h` / `1d` for the table).
- `staging_exists` is the boolean equivalent of the text `STAGING present|missing` cell.
- `config_hash` is read forward-compatibly off the `human_approval.required` event payload (with a `config_fingerprint` legacy-key fallback). **Current trainer emission does not yet populate either field**, so the renderer surfaces `null` in the `--json` output and an empty cell in the text table; the read path is wired so a future emitter can light it up without a doc change.

## What `--show RUN_ID` does

Implemented in `forgelm.cli.subcommands._approvals._run_approvals_show`:

1. Same audit-log readability gate as `--pending`.
2. Replays every event for the supplied `run_id` (`human_approval.required`, `human_approval.granted`, `human_approval.rejected`).
3. Lists the staging directory contents (when present).

A `--show` against an unknown `run_id` exits 1 with a clear error.

Sample text output:

```text
Run: fg-abc123def456
Status: pending

Audit chain (oldest first):
  [2026-04-30T11:33:10+00:00] human_approval.required — require_human_approval=true

Staging contents (4 entries):
  - adapter_config.json
  - adapter_model.safetensors
  - tokenizer.json
  - tokenizer_config.json
```

Sample JSON envelope (top-level keys built by `_emit_show_json`):

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "status": "pending",
  "chain": [
    {
      "event": "human_approval.required",
      "timestamp": "2026-04-30T11:33:10+00:00",
      "operator": "gha:Acme/pipelines:training:run-42"
    }
  ],
  "staging_contents": [
    "adapter_config.json",
    "adapter_model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json"
  ]
}
```

Field notes:
- `chain` is the ordered list of `human_approval.*` events for the run (`required` → optional `granted` / `rejected`).
- `staging_contents` is a flat list of file/directory names under the staging path (or empty when the staging directory is absent — e.g., already promoted or purged).
- `status` ∈ `{pending, granted, rejected}` reflecting the latest terminal decision (or `pending` when none).

## Audit events emitted

**None.** `forgelm approvals` is a strict read-only inspector and does not emit audit events. The only events you will see in the chain are those produced by the trainer (`human_approval.required`) and by `forgelm approve` / `forgelm reject` (`human_approval.granted` / `.rejected`).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | `EXIT_SUCCESS` — listing or `--show` succeeded. `--pending` returns 0 when the queue is empty (no pending decisions is a valid answer). |
| 1 | `EXIT_CONFIG_ERROR` — `audit_log.jsonl` is **present but unreadable or corrupted**, neither `--pending` nor `--show` supplied (argparse normally catches this), or unknown `run_id` on `--show`. |
| 2 | `EXIT_TRAINING_ERROR` — runtime I/O failure mid-stream (NFS flap, partial-read OSError) while iterating the chain. |

Codes 3 (`EXIT_EVAL_FAILURE`) and 4 (`EXIT_AWAITING_APPROVAL`) are not part of this subcommand's surface.

> **Asymmetric missing-log behaviour.**
> - `--pending` against a missing `audit_log.jsonl` returns **0** with an empty pending list — a freshly-bootstrapped output directory legitimately has neither (`_run_approvals_list_pending`).
> - `--show` against a missing `audit_log.jsonl` returns **1** — there is no run to show, and the operator's request was specific (`_run_approvals_show`).
>
> Permission-denied (vs missing) is treated identically by both: exit 1 with an explicit error rather than silently presenting an empty result.

## CI usage pattern

The JSON envelope is the supported CI surface:

```bash
# Block the deploy job until every staged model has a decision.
pending=$(forgelm approvals --pending --output-dir ./outputs --output-format json | jq '.count')
if [ "$pending" -gt 0 ]; then
    echo "::warning::$pending approval(s) still pending"
    exit 1
fi
```

Operators wiring a richer policy (e.g. "block deploy if any pending decision is older than N hours") parse the `age` field. Treat the text output as advisory only — the JSON envelope is the stable contract.

## See also

- [`approve_subcommand.md`](approve_subcommand.md) — terminal-decision counterpart (`approve` / `reject`).
- [`../guides/human_approval_gate.md`](../guides/human_approval_gate.md) — deployer flow walkthrough.
- [`audit_event_catalog.md`](audit_event_catalog.md) — full event vocabulary (the `human_approval.*` rows are read by this subcommand).
- [`../qms/access_control.md`](../qms/access_control.md) §6 — segregation-of-duties cookbook (uses `human_approval.granted` rows that `--show` projects).
