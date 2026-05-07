# `forgelm approve` / `forgelm reject` — Subcommand Reference

> **Audience:** ForgeLM operators discharging the EU AI Act Article 14 human-oversight gate, plus auditors verifying the resulting `human_approval.granted` / `human_approval.rejected` audit row.
> **Mirror:** [approve_subcommand-tr.md](approve_subcommand-tr.md)

`forgelm approve` and `forgelm reject` are the **EU AI Act Article 14** human-oversight terminal-decision subcommands (Phase 9). When a training run exits with code 4 (`EXIT_AWAITING_APPROVAL`) it pauses with `final_model.staging/` on disk and a `human_approval.required` event in the chain; an authorised reviewer then runs `approve` (to promote) or `reject` (to discard).

For the listing counterpart, see [`approvals_subcommand.md`](approvals_subcommand.md). For the deployer-flow walkthrough (CI run exits 4 → reviewer paged → CLI invocation → audit), see [`../guides/human_approval_gate.md`](../guides/human_approval_gate.md).

## Synopsis

```text
forgelm approve  run_id --output-dir DIR [--comment TEXT]
                        [--output-format {text,json}]

forgelm reject   run_id --output-dir DIR [--comment TEXT]
                        [--output-format {text,json}]
```

Both subcommands take a **positional `run_id`** (NOT `--run-id`). This matches the CLI surface in `forgelm/cli/subcommands/_approve.py` and the `forgelm approve <run-id>` cookbook in [`../qms/access_control.md`](../qms/access_control.md) §6.

| Argument / flag | Required | Description |
|---|---|---|
| `run_id` (positional) | yes | Run id emitted with the `human_approval.required` event (e.g. `fg-abc123def456`). |
| `--output-dir DIR` | yes | Training output directory containing `audit_log.jsonl` and `final_model.staging/`. |
| `--comment TEXT` | no | Optional reviewer comment recorded on the granted / rejected event. Recommended on `reject` so the auditor sees the rationale. |
| `--output-format {text,json}` | no (default `text`) | `json` prints exactly one structured object on stdout for CI consumers. |

## What `approve` does

Implemented in `forgelm.cli.subcommands._approve._run_approve_cmd`:

1. Verifies `audit_log.jsonl` is readable.
2. Locates the matching `human_approval.required` event for `run_id` via `_find_human_approval_required_event`.
3. Refuses if a terminal decision (`granted` / `rejected`) already exists for the same `run_id` (`_find_human_approval_decision_event`) — re-approve is not allowed.
4. Validates `staging_path` from the event resolves **inside** `output_dir` (`_staging_path_inside_output_dir` defence-in-depth — without HMAC, a tampered audit log could otherwise plant an absolute or `..`-traversing path).
5. Constructs `AuditLogger(output_dir, run_id=run_id)` BEFORE the atomic rename so an `EXIT_CONFIG_ERROR` from operator-identity resolution does not leave a promoted model with no `granted` event (Article 12 record-keeping integrity).
6. Atomically renames `final_model.staging[.<run_id>]/` → `final_model/`.
7. Emits `human_approval.granted` carrying `gate="final_model"`, `run_id`, `approver` (resolved via `_resolve_approver_identity`), `comment`, `promote_strategy`.
8. Fires the `notify_success` webhook lifecycle event.

## What `reject` does

Implemented in `forgelm.cli.subcommands._approve._run_reject_cmd`:

1. Same audit-log / required-event / no-prior-decision validation as `approve`.
2. **Preserves the staging directory** so the rejected artefacts remain available for forensic review.
3. Emits `human_approval.rejected` carrying `gate="final_model"`, `run_id`, `approver`, `comment`, `staging_path`.
4. Fires the `notify_failure` webhook lifecycle event.

The staging directory is **not** deleted — operators clean it up explicitly via `forgelm purge --run-id <id> --kind staging` after the rejection record is in the chain.

## Operator identity (`FORGELM_OPERATOR`)

Both subcommands resolve the approver identity via `forgelm.cli.subcommands._approve._resolve_approver_identity`:

1. `FORGELM_OPERATOR` env var (highest priority — explicit operator identification).
2. `getpass.getuser()` (the OS-reported username).
3. `"anonymous"` if both fail.

**Article 14 segregation of duties.** The approver's `FORGELM_OPERATOR` MUST differ from the trainer's (ISO 27001:2022 A.5.3, SOC 2 CC1.5). ForgeLM does not enforce the difference — that is a deployer-side IdP control — but the audit chain records both, so an auditor can detect violations with the `jq -rs` cookbook in [`../qms/access_control.md`](../qms/access_control.md) §6:

```bash
jq -rs '
    (map(select(.event == "training.started"))) as $trainers |
    map(select(.event == "human_approval.granted"))[] |
    . as $a |
    $trainers[] |
    select(.run_id == $a.run_id and .operator == $a.operator) |
    [.run_id, .operator] | @tsv
' ./outputs/audit_log.jsonl
```

Any rows printed are segregation-of-duties violations.

## Audit events emitted

Both events ride the common envelope from [`audit_event_catalog.md`](audit_event_catalog.md). The catalog rows are reproduced here for convenience.

| Event | When emitted | Key payload |
|---|---|---|
| `human_approval.granted` | Operator approved the paused gate via `forgelm approve`. | `gate`, `approver`, `comment`, `run_id`, `promote_strategy` |
| `human_approval.rejected` | Operator rejected the paused gate via `forgelm reject`. | `gate`, `approver`, `comment`, `run_id`, `staging_path` |

The matching `human_approval.required` event is emitted by the trainer when the gate first opens (carries `gate`, `reason`, `metrics`, `staging_path`, `run_id`).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Decision recorded; on `approve` the staging directory was promoted to `final_model/`. |
| 1 | Config error: `audit_log.jsonl` unreadable or corrupted, no matching `human_approval.required` event for `run_id`, prior terminal decision already present (re-approve / re-reject blocked), `staging_path` escapes `output_dir`, `final_model/` already exists (cannot promote), staging directory missing, `FORGELM_OPERATOR` cannot be resolved (`ConfigError` from `AuditLogger`). |
| 2 | Runtime error: atomic-rename failure (`OSError` during `os.replace`). |

Codes 3 (`EXIT_EVAL_FAILURE`) and 4 (`EXIT_AWAITING_APPROVAL`) are not part of this subcommand's surface — code 4 is the input signal that brings the operator here in the first place.

## JSON output envelope

`approve` (success) — emitted by `_approve.py:468-477`:

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "approver": "alice@acme.example",
  "final_model_path": "outputs/run42/final_model",
  "promote_strategy": "rename"
}
```

`reject` (success) — emitted by `_approve.py:542-551`:

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "approver": "alice@acme.example",
  "staging_path": "outputs/run42/final_model.staging.fg-abc123def456",
  "comment": "Threshold drift in S5; re-train with stricter regression tolerance."
}
```

Failure (both, emitted by `_output_error_and_exit`):

```json
{
  "success": false,
  "error": "Run 'fg-abc123def456' already has a terminal decision ('human_approval.granted'). Refusing to record another decision — re-approve is not allowed."
}
```

> **Field-level notes.** `approve` does **not** echo `comment` in the JSON envelope (the comment is recorded on the `human_approval.granted` audit event payload, not on stdout). `reject` echoes the empty string when `--comment` is omitted. `promote_strategy` is `"rename"` on a same-device promotion and `"move"` on a cross-device fallback (`shutil.move`); the audit event payload mirrors this value.

## See also

- [`approvals_subcommand.md`](approvals_subcommand.md) — discovery counterpart (`--pending` / `--show RUN_ID`).
- [`../guides/human_approval_gate.md`](../guides/human_approval_gate.md) — deployer flow walkthrough.
- [`audit_event_catalog.md`](audit_event_catalog.md) — full event vocabulary and envelope spec.
- [`../qms/access_control.md`](../qms/access_control.md) §6 — segregation-of-duties cookbook.
- [`../usermanuals/en/compliance/human-oversight.md`](../usermanuals/en/compliance/human-oversight.md) — operator-facing user-manual page.
