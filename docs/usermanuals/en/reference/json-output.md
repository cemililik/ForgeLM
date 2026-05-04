---
title: JSON output schemas
description: The locked --output-format json envelope shape for every forgelm subcommand. CI consumers depend on these field names.
---

# JSON output schemas

Every `forgelm` subcommand that supports `--output-format json` produces a stable JSON envelope on stdout. Field names + nesting are part of the public CLI contract per [`docs/standards/release.md`](#/standards/release): renaming a key is a MAJOR-version break.

This page is the canonical reference. CI/CD pipelines that parse `forgelm` output should pin against the shapes documented here.

## Common conventions

- **stdout vs stderr.** The JSON envelope goes to **stdout**. Human-friendly logs (info / warning / error) go to **stderr**. Pipe `forgelm ... --output-format json | jq .` and read your operator-facing messages from `2>` separately.
- **Top-level wrapper.** Every envelope starts with `"success": true | false`. Consumers can branch on this single key before parsing the rest.
- **Error envelope.** When `success: false`, the envelope carries `"error": "<message>"` (string). Optional richer fields (`exit_code`, `error_type`, `details`) MAY be present per [`error-handling.md`](#/standards/error-handling). Consumers that need certainty on these fields should also check the process exit code via `$?`.
- **Exit codes.** See [Exit Codes](#/reference/exit-codes). The envelope is consistent with the exit code: `success: true` ⟺ exit `0`; `success: false` ⟺ non-zero exit.

## `forgelm doctor`

Environment check. See [Doctor command](#/getting-started/first-run).

**Success envelope** (`forgelm doctor [--offline] --output-format json`):

```json
{
  "success": true,
  "checks": [
    {
      "name": "python.version",
      "status": "pass",
      "detail": "Python 3.11.7 (CPython).",
      "extras": {"version": "3.11.7", "implementation": "CPython"}
    }
  ],
  "summary": {"pass": 8, "warn": 1, "fail": 0, "crashed": 0}
}
```

| Key | Type | Notes |
|---|---|---|
| `success` | bool | `true` when no probe `fail` AND no probe crash; `false` otherwise. |
| `checks` | list[object] | One entry per probe in execution order. Probe names are stable (e.g. `python.version`, `torch.cuda`, `gpu.inventory`, `extras.qlora`, `hf_hub.reachable`, `hf_hub.offline_cache`, `disk.workspace`, `operator.identity`). |
| `checks[].name` | str | Probe name. Stable across versions; new probes append rather than rename. |
| `checks[].status` | str | One of `pass`, `warn`, `fail`, `crashed`. |
| `checks[].detail` | str | Operator-facing one-line description of the result. |
| `checks[].extras` | object | Probe-specific structured data. Per-probe keys are documented in `_doctor.py` docstrings; consumers should treat unknown keys as forward-compatible. |
| `summary` | object | Counts of each status across `checks`. Sum equals `len(checks)`. |

**Exit code mapping:** `0` = all probes `pass` or `warn`; `1` = at least one `fail`; `2` = at least one `crashed` (probe raised; subsequent probes still ran).

## `forgelm approvals --pending`

Lists pending Article 14 approval requests, newest-first.

```json
{
  "success": true,
  "pending": [
    {
      "run_id": "fg-abc123def456",
      "staging_path": "/work/output/final_model.staging.fg-abc123def456",
      "staging_exists": true,
      "requested_at": "2026-05-04T12:34:56+00:00",
      "age_seconds": 3600.5,
      "metrics": {"safety_score": 0.91, "benchmark.hellaswag": 0.78},
      "config_hash": "sha256:...",
      "reason": "post-train safety eval below threshold"
    }
  ],
  "count": 1
}
```

| Key | Type | Notes |
|---|---|---|
| `success` | bool | `true` (always — empty list is success). |
| `pending` | list[object] | Newest-first; `count == len(pending)`. Empty list = no pending approvals. |
| `pending[].run_id` | str \| null | Run identifier from the audit event. |
| `pending[].staging_path` | str \| null | Resolved staging directory (`null` when audit event lacks `staging_path` and no canonical fallback exists). Path-traversal guarded — paths outside `--output-dir` are rejected at resolution time. |
| `pending[].staging_exists` | bool | `True` iff `staging_path` resolves to an existing directory. |
| `pending[].requested_at` | str \| null | ISO-8601 timestamp from the audit event. |
| `pending[].age_seconds` | number \| null | Seconds since `requested_at`; `null` when timestamp is unparseable. |
| `pending[].metrics` | object | Free-form per-run metrics from the audit event. |
| `pending[].config_hash` | str \| null | Config fingerprint, when known. |
| `pending[].reason` | str \| null | Operator-supplied reason from the audit event. |
| `count` | int | Pending count; equal to `len(pending)`. |

## `forgelm approvals --show RUN_ID`

Inspect the full approval-gate audit chain + staging contents for one run.

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "status": "pending",
  "chain": [
    {"event": "human_approval.required", "run_id": "fg-abc123def456", "timestamp": "2026-05-04T12:34:56+00:00", "...": "..."}
  ],
  "staging_contents": ["adapter_config.json", "adapter_model.safetensors", "tokenizer.json"]
}
```

| Key | Type | Notes |
|---|---|---|
| `success` | bool | `true` when the run was found; `false` (with `error`) when `RUN_ID` has no audit events. |
| `run_id` | str | Echoed input `RUN_ID`. |
| `status` | str | One of `pending`, `granted`, `rejected`, `unknown`. Latest-wins semantics: a re-staged run after a prior decision shows `pending`. |
| `chain` | list[object] | Every approval-gate audit event for `run_id`, in append order. |
| `staging_contents` | list[str] | Sorted file/directory names at `<output_dir>/final_model.staging.<run_id>` (or canonical fallback). Empty when staging missing or unreadable. |

## `forgelm audit`

Pre-train data audit. Full report; key fields shown.

```json
{
  "success": true,
  "report_path": "audit/data_audit_report.json",
  "splits": {"train": {"sample_count": 100, "...": "..."}, "...": {}},
  "pii_summary": {"total_findings": 0, "by_kind": {}},
  "secrets_summary": {"total_findings": 0, "by_kind": {}},
  "cross_split_overlap": {"pairs": {}},
  "leakage": {"...": "..."},
  "quality_filter": null,
  "near_duplicates": {"...": "..."},
  "languages_top3": [{"code": "en", "count": 87}],
  "generated_at": "2026-05-04T12:34:56+00:00",
  "warnings": []
}
```

The full schema is in [`docs/guides/data_audit.md`](#/data/audit). Pin against `report_path` (where the on-disk JSON lives) + `success` for CI gates.

## `forgelm verify-audit`

Audit-log chain integrity check.

```json
{
  "success": true,
  "valid": true,
  "entries_count": 87,
  "hmac_verified": true,
  "errors": []
}
```

| Key | Type | Notes |
|---|---|---|
| `success` | bool | `true` ⟺ `valid: true`. |
| `valid` | bool | `false` if any prev_hash mismatch / monotonicity break / seq gap. |
| `entries_count` | int | Number of well-formed audit lines. |
| `hmac_verified` | bool \| null | `true` when `--hmac-secret` matches every `hmac` field; `false` on mismatch; `null` when chain has no HMAC fields. |
| `errors` | list[str] | One human-readable line per detected problem. |

## `forgelm approve` / `forgelm reject`

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "approver": "alice@example.com@workstation-7",
  "final_model_path": "/work/output/final_model",
  "promote_strategy": "atomic_rename"
}
```

`approve` exits `0` on success; `reject` exits `0` after recording the rejection (the staging dir is preserved for forensics). `success: false` with `error` on unknown `run_id` / config error.

## Adding a new subcommand

A new subcommand that supports `--output-format json` MUST land with:

1. The envelope documented in this page (EN + TR mirror).
2. A test in `tests/test_json_envelope_contract.py` (or a per-subcommand test file) that pins the exact set of top-level keys.
3. The per-collection key follows the convention "results live under a key named after the subcommand's primary noun" (so `doctor` → `checks`, `approvals --pending` → `pending`, etc.).

Renaming a key after merge is a MAJOR-version bump per [`release.md`](#/standards/release).

## See also

- [Exit Codes](#/reference/exit-codes) — the contract `success: bool` aligns with.
- [`error-handling.md`](#/standards/error-handling) — the error envelope contract.
- [`release.md`](#/standards/release) — when JSON renames count as breaking.
