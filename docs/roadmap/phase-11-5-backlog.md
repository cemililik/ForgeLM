# Phase 11.5 — Ingestion / Audit Polish

> **Status:** ✅ Landed for the `v0.5.1` cycle. All 12 follow-ups carved
> out of Phase 11's review backlog have shipped. Modules touched:
> [`forgelm/data_audit.py`](../../forgelm/data_audit.py),
> [`forgelm/ingestion.py`](../../forgelm/ingestion.py),
> [`forgelm/cli.py`](../../forgelm/cli.py),
> [`forgelm/wizard.py`](../../forgelm/wizard.py); CLI:
> `forgelm audit <path>` (new subcommand, with `--data-audit` preserved
> as deprecation alias) + token-aware `forgelm ingest` flags; tests:
> [`tests/test_data_audit.py`](../../tests/test_data_audit.py),
> [`tests/test_ingestion.py`](../../tests/test_ingestion.py),
> [`tests/test_cli_subcommands.py`](../../tests/test_cli_subcommands.py),
> [`tests/test_wizard_byod.py`](../../tests/test_wizard_byod.py).

**Goal:** Operational polish on top of `v0.5.0`'s ingestion + audit
surface — no new training capabilities, but materially better handling
for large corpora and a cleaner CLI shape.

## What landed

| # | Item | Where it lives | One-line takeaway |
|---|---|---|---|
| **1** | LSH banding for near-duplicate detection | `find_near_duplicates`, `_count_leaked_rows` in [`data_audit.py`](../../forgelm/data_audit.py) | Pigeonhole-banded LSH (default `bands = threshold + 1`). Drops within-split + cross-split scans from `O(n²)` to ~`O(n × k)`; brute-force fallback when bands shrink below 4 bits. |
| **2** | Streaming `_read_jsonl_split` | [`data_audit.py`](../../forgelm/data_audit.py) | Reader is now a generator yielding `(row, parse_err, decode_err)`; `_audit_split` consumes it row-by-row via a `_StreamingAggregator` so RAM stays bounded on multi-million-row splits. |
| **3** | Token-aware `--chunk-tokens` | [`ingestion.py`](../../forgelm/ingestion.py), [`cli.py`](../../forgelm/cli.py) | New `--chunk-tokens N` + `--tokenizer MODEL` flags on `forgelm ingest`. Chunks are sized via `AutoTokenizer.encode` instead of raw character counts so they line up with `model.max_length` exactly. |
| **4** | PDF page-level header / footer dedup | `_strip_repeating_page_lines` in [`ingestion.py`](../../forgelm/ingestion.py) | Lines that recur as the first or last non-empty line on ≥ 70 % of a PDF's pages are stripped. Reduces audit near-duplicate noise on long policy / book PDFs. |
| **5** | Token-level `lru_cache` memo | `_token_digest` in [`data_audit.py`](../../forgelm/data_audit.py) | Per-token digest is cached at module scope (`maxsize=10_000`). Distinct tokens follow Zipf, so ~10 K cache slots cover most corpus traffic. |
| **6** | xxhash backend for simhash | `_token_digest` in [`data_audit.py`](../../forgelm/data_audit.py) | Optional `xxhash` import (added to the `[ingestion]` extra) drives the digest path when present; BLAKE2b is preserved as the fallback. |
| **7** | `forgelm audit` proper subcommand | [`cli.py`](../../forgelm/cli.py) | New `forgelm audit PATH` (with `--verbose`, `--near-dup-threshold`, `--output`). The legacy `--data-audit FLAG` keeps working as a deprecation alias (logs a one-line notice). |
| **8** | PII severity tiers | `PII_SEVERITY`, `_build_pii_severity` in [`data_audit.py`](../../forgelm/data_audit.py) | Audit JSON now carries `pii_severity` with `worst_tier`, `by_tier`, and `by_type`. Notes line lead with the worst tier (e.g. `WORST tier: CRITICAL`). |
| **9** | `summarize_report` truncation policy | [`data_audit.py`](../../forgelm/data_audit.py) | Default `verbose=False` folds zero-finding splits into a single tail line. CLI exposes `--verbose` on the new `audit` subcommand for full output. |
| **10** | Structured ingestion notes | `IngestionResult.notes_structured` in [`ingestion.py`](../../forgelm/ingestion.py) | Free-text `extra_notes` stays for humans; new `notes_structured` carries machine-readable `{key: value}` for CI/CD consumers. JSON output already exposes both. |
| **11** | Wizard "ingest first" entry point | `_offer_ingest_for_directory` + `_prompt_dataset_path_with_ingest_offer` in [`wizard.py`](../../forgelm/wizard.py) | Both BYOD quickstart and the full 8-step wizard now offer to run `ingest` inline when the typed path is a directory of raw documents. |
| **12** | Atomic audit-report write | `_atomic_write_json` in [`data_audit.py`](../../forgelm/data_audit.py) | Writes via `tempfile.NamedTemporaryFile` + `os.replace` so a crashed audit can never leave a half-written `data_audit_report.json` on disk. |

## Behavioural deltas worth highlighting

- **Default near-duplicate detection is now LSH-banded.** Behaviour at
  the default `threshold=3` is identical to the old quadratic scan
  (pigeonhole gives exact recall), but the cost on a 100 K row corpus
  drops from "tens of seconds, gigabytes of comparisons" to ~seconds.
- **Audit output JSON adds `pii_severity`.** Existing consumers that
  read only `pii_summary` keep working — the new field is additive.
  Pipelines that want a one-glance verdict should read
  `pii_severity.worst_tier` and gate on `critical` / `high`.
- **`forgelm audit PATH` is the recommended invocation.** The
  `--data-audit` top-level flag continues to work but logs a one-line
  deprecation notice. Plan to remove it no earlier than `v0.7.0`.
- **`--chunk-tokens` requires `--tokenizer`.** Token-aware chunking
  needs to know which vocab to count against; we refuse to default to a
  hidden tokenizer because the chunk count would silently differ
  per-model. Set both or neither.
- **PDF dedup is opt-out by being short-doc-tolerant.** Documents
  with fewer than 3 pages skip the dedup step entirely; the statistical
  signal is too weak to distinguish "header" from "actual repetition"
  on small docs.

## What's next

`v0.5.2` (Phase 14) picks up multi-stage pipeline chains. The audit and
ingestion surface is considered stable for the foreseeable future; any
additional ergonomics live as small follow-ups, not as their own phase.
