# `forgelm purge` — Subcommand Reference

> **Audience:** ForgeLM operators honouring GDPR Article 17 erasure requests against training corpora and run-scoped artefacts, plus auditors verifying the resulting `data.erasure_*` audit chain.
> **Mirror:** [purge_subcommand-tr.md](purge_subcommand-tr.md)

`forgelm purge` is the operator-facing implementation of the **GDPR Article 17 right-to-erasure** for ForgeLM training corpora and run artefacts (Phase 21). It atomically deletes a row, a run's staging directory, or a run's compliance bundle, and records every step in the tamper-evident `audit_log.jsonl` chain.

For the deployer-flow walkthrough (DSAR ticket → CLI invocation → verification), see [`../guides/gdpr_erasure.md`](../guides/gdpr_erasure.md). This page is the per-flag, per-event reference.

## Synopsis

```text
forgelm purge --row-id ID --corpus PATH [--row-matches {one,all}]
              [--output-dir DIR] [--justification TEXT] [--dry-run]
              [--output-format {text,json}]

forgelm purge --run-id RUN_ID --kind {staging,artefacts}
              --output-dir DIR [--justification TEXT] [--dry-run]
              [--output-format {text,json}]

forgelm purge --check-policy --config PATH [--output-dir DIR]
              [--output-format {text,json}]
```

The three modes are mutually exclusive (`argparse` enforces a single mode group).

## Modes

### Corpus-row erasure (`--row-id`)

Erases a single row identified by its `id` (or `row_id`) field from a JSONL training corpus. Implemented in `forgelm.cli.subcommands._purge._run_row_erasure`.

| Flag | Required | Description |
|---|---|---|
| `--row-id ID` | yes | Identifier to erase. Hashed before audit emission via `forgelm.cli.subcommands._purge._hash_target_id`. |
| `--corpus PATH` | yes | Single JSONL file. Directory mode is rejected — operators loop in their own script. |
| `--row-matches {one,all}` | no (default `one`) | `one` refuses on >=2 matches; `all` deletes every match (operator confirms intent). |
| `--output-dir DIR` | no | Defaults to the parent of `--corpus`. The per-output-dir salt at `<output_dir>/.forgelm_audit_salt` is read here for `target_id` hashing. |
| `--justification TEXT` | no | Operator-supplied reason recorded on every erasure event. Reference your internal ticket id; do not paste subject identifiers. |
| `--dry-run` | no | Preview the deletion + emit the audit chain (with `dry_run=true`) without modifying disk. |

**Atomic write contract.** The corpus is rewritten via a sibling temp file + `os.replace`, so an interrupted purge leaves either the full pre-erasure file or the full post-erasure file — never a partial state.

**Line-number fallback is rejected** (design §4.2). Operators with id-less corpora must pre-populate ids via `forgelm audit --add-row-ids`.

### Run-scoped artefact erasure (`--run-id` + `--kind`)

| Kind | Target |
|---|---|
| `staging` | `<output_dir>/final_model.staging.<run_id>/` (and the legacy `final_model.staging/` if present). |
| `artefacts` | `<output_dir>/compliance/*.json` files whose name embeds `<run_id>`. |

`--kind logs` is **intentionally absent**: audit logs are append-only Article 17(3)(b) records and are not deleted by the tool.

### Retention-policy report (`--check-policy`)

Read-only scan. Walks `<output_dir>`, compares each artefact's age (canonical: audit-log genesis `timestamp`; fallback: filesystem `mtime` with `age_source=mtime`) against the loaded config's `retention:` horizons, and emits a structured violation list.

**Successful policy reports always exit 0** (report-not-gate semantic per design §10 Q5). Config-load failures exit `EXIT_CONFIG_ERROR` (1) — an explicit `--config` that is missing, unreadable, or fails Pydantic validation surfaces as a non-zero so the operator does not mistake "loader failed" for "no violations". Operators wiring a CI gate use `--output-format json` and pipe to `jq '.violations | length'` themselves.

## Salt resolution

The per-output-dir salt at `<output_dir>/.forgelm_audit_salt` is created on first use (mode `0600`, atomic O_EXCL write) by `forgelm.cli.subcommands._purge._read_persistent_salt`. `forgelm.cli.subcommands._purge._resolve_salt` returns `(salt_bytes, salt_source)`:

- `salt_source = "per_dir"` — `FORGELM_AUDIT_SECRET` is unset; the persistent salt is used verbatim.
- `salt_source = "env_var"` — `FORGELM_AUDIT_SECRET` is set; the first 16 bytes are XOR'd with the persistent salt.

**This XOR feeds identifier hashing only.** The audit-chain HMAC key is derived independently as `SHA-256(FORGELM_AUDIT_SECRET ‖ run_id)` inside `forgelm.compliance.AuditLogger.__init__`. The two primitives are intentionally separate; rotating `FORGELM_AUDIT_SECRET` therefore rotates both, but inspecting either does not reveal the other.

## Cross-tool digest correlation with `forgelm reverse-pii`

When `forgelm purge --row-id <value>` and `forgelm reverse-pii --query <value> --salt-source per_dir` run against the **same** `<output_dir>` (i.e. consume the same `.forgelm_audit_salt`), the `target_id` field on `data.erasure_*` events and the `query_hash` field on `data.access_request_query` events are byte-identical. A compliance reviewer can therefore correlate Article 17 erasures and Article 15 access requests for the same data subject without ever seeing the cleartext identifier. Pinned by `tests/test_reverse_pii.py::test_purge_target_id_matches_reverse_pii_query_hash_on_same_output_dir`.

## Audit events emitted

All six events ride the common envelope from [`audit_event_catalog.md`](audit_event_catalog.md). The catalog rows are reproduced here for convenience.

| Event | When emitted | Key payload |
|---|---|---|
| `data.erasure_requested` | First step of any `--row-id` / `--run-id` invocation, BEFORE any deletion. `--check-policy` is read-only and emits no events. | `target_kind` ∈ `{row, staging, artefacts}`, `target_id` (hashed in row mode), `salt_source` (row mode), `corpus_path` (row), `output_dir` (run), `justification`, `dry_run` |
| `data.erasure_completed` | Successful deletion finished. | All `requested` fields + `bytes_freed`, `files_modified`, `pre_erasure_line_number` (row mode), `match_count` (row mode) |
| `data.erasure_failed` | Disk operation raised, OR no matching row/run, OR multi-row policy refused on ambiguity. | All `requested` fields + `error_class`, `error_message` |
| `data.erasure_warning_memorisation` | Row erasure × `final_model/` exists for any run that consumed this corpus. | All `completed` fields + `affected_run_ids` |
| `data.erasure_warning_synthetic_data_present` | Row erasure × `synthetic_data*.jsonl` exists in `output_dir`. | All `completed` fields + `synthetic_files` |
| `data.erasure_warning_external_copies` | Loaded config has a non-empty `webhook` block; downstream consumers may have received notices. | All `completed` fields + `webhook_targets` (redacted URLs) |

`forgelm verify-audit <output_dir>/audit_log.jsonl` continues to validate the chain after any number of erasure events — the tool appends new events, never rewrites old ones.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, or a successful `--check-policy` report (report-not-gate semantic). |
| 1 | Config error: unknown `--row-id`, missing `--corpus`, mutually-exclusive flag combination, conflicting `staging_ttl_days` values, or `--check-policy --config <path>` that is missing / unreadable / fails Pydantic validation. |
| 2 | Runtime error: I/O failure, permission denied, atomic-rename failure. |

`--check-policy` never returns code 3 or 4. Codes 3 (`EXIT_EVAL_FAILURE`) and 4 (`EXIT_AWAITING_APPROVAL`) are reserved for the training pipeline and are not part of this subcommand's surface.

## JSON output envelope

With `--output-format json` every invocation prints exactly one JSON object on stdout. The envelope mirrors the rest of the compliance subcommand family:

```json
{"success": true, "deleted": "row", "files_modified": ["data/train.jsonl"], "bytes_freed": 482, "match_count": 1}
```

Failure envelopes:

```json
{"success": false, "error": "Row id 'ali@example.com' not found in 'data/train.jsonl'."}
```

The structured shape is the same for `--check-policy`:

```json
{"success": true, "violations": [{"path": "outputs/run42/", "kind": "ephemeral_artefact", "age_days": 121, "age_source": "audit_genesis", "horizon_days": 90}]}
```

## See also

- [`../guides/gdpr_erasure.md`](../guides/gdpr_erasure.md) — deployer-flow walkthrough (DSAR ticket → CLI → verify chain).
- [`reverse_pii_subcommand.md`](reverse_pii_subcommand.md) — sibling Article 15 right-of-access tool.
- [`audit_event_catalog.md`](audit_event_catalog.md) — full event vocabulary with envelope spec.
- [`../qms/access_control.md`](../qms/access_control.md) §3.4 — operator identity contract (the `FORGELM_OPERATOR` recorded on every erasure event).
