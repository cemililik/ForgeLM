# Phase 11.5 — Ingestion / Audit Polish

> **Note (post-consolidation):** Originally targeted `v0.5.1`, now ships
> as part of the consolidated `v0.5.0` release alongside Phases 11, 12,
> and 12.5 — see [releases.md](releases.md#v050-document-ingestion-data-curation-pipeline).
> Version-label references below preserve the historical planning trail.
>
> **Status:** ✅ Landed for the (originally) `v0.5.1` cycle. All 12 follow-ups carved
> out of Phase 11's review backlog have shipped. Modules touched:
> [`forgelm/data_audit/`](../../forgelm/data_audit/),
> [`forgelm/ingestion.py`](../../forgelm/ingestion.py),
> [`forgelm/cli/`](../../forgelm/cli/),
> [`forgelm/wizard/`](../../forgelm/wizard/); CLI:
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
| **1** | LSH banding for near-duplicate detection | `find_near_duplicates`, `_count_leaked_rows` in [`data_audit.py`](../../forgelm/data_audit/) | Pigeonhole-banded LSH (default `bands = threshold + 1`). Drops within-split + cross-split scans from `O(n²)` to ~`O(n × k)`; brute-force fallback when bands shrink below 4 bits. |
| **2** | Streaming `_read_jsonl_split` | [`data_audit.py`](../../forgelm/data_audit/) | Reader is now a generator yielding `(row, parse_err, decode_err)`; `_audit_split` consumes it row-by-row via a `_StreamingAggregator` so RAM stays bounded on multi-million-row splits. |
| **3** | Token-aware `--chunk-tokens` | [`ingestion.py`](../../forgelm/ingestion.py), [`cli.py`](../../forgelm/cli/) | New `--chunk-tokens N` + `--tokenizer MODEL` flags on `forgelm ingest`. Chunks are sized via `AutoTokenizer.encode` instead of raw character counts so they line up with `model.max_length` exactly. |
| **4** | PDF page-level header / footer dedup | `_strip_repeating_page_lines` in [`ingestion.py`](../../forgelm/ingestion.py) | Lines that recur as the first or last non-empty line on ≥ 70 % of a PDF's pages are stripped. Reduces audit near-duplicate noise on long policy / book PDFs. |
| **5** | Token-level `lru_cache` memo | `_token_digest` in [`data_audit.py`](../../forgelm/data_audit/) | Per-token digest is cached at module scope (`maxsize=10_000`). Distinct tokens follow Zipf, so ~10 K cache slots cover most corpus traffic. |
| **6** | xxhash backend for simhash | `_token_digest` in [`data_audit.py`](../../forgelm/data_audit/) | Optional `xxhash` import (added to the `[ingestion]` extra) drives the digest path when present; BLAKE2b is preserved as the fallback. |
| **7** | `forgelm audit` proper subcommand | [`cli.py`](../../forgelm/cli/) | New `forgelm audit PATH` (with `--verbose`, `--near-dup-threshold`, `--output`). The legacy `--data-audit FLAG` keeps working as a deprecation alias (logs a one-line notice). |
| **8** | PII severity tiers | `PII_SEVERITY`, `_build_pii_severity` in [`data_audit.py`](../../forgelm/data_audit/) | Audit JSON now carries `pii_severity` with `worst_tier`, `by_tier`, and `by_type`. Notes line lead with the worst tier (e.g. `WORST tier: CRITICAL`). |
| **9** | `summarize_report` truncation policy | [`data_audit.py`](../../forgelm/data_audit/) | Default `verbose=False` folds zero-finding splits into a single tail line. CLI exposes `--verbose` on the new `audit` subcommand for full output. |
| **10** | Structured ingestion notes | `IngestionResult.notes_structured` in [`ingestion.py`](../../forgelm/ingestion.py) | Free-text `extra_notes` stays for humans; new `notes_structured` carries machine-readable `{key: value}` for CI/CD consumers. JSON output already exposes both. |
| **11** | Wizard "ingest first" entry point | `_offer_ingest_for_directory` + `_prompt_dataset_path_with_ingest_offer` in [`forgelm/wizard/_byod.py`](../../forgelm/wizard/_byod.py) | Both BYOD quickstart and the full 9-step wizard now offer to run `ingest` inline when the typed path is a directory of raw documents. |
| **12** | Atomic audit-report write | `_atomic_write_json` in [`data_audit.py`](../../forgelm/data_audit/) | Writes via `tempfile.NamedTemporaryFile` + `os.replace` so a crashed audit can never leave a half-written `data_audit_report.json` on disk. |

## Measured speedups (xxhash + lru_cache hot path)

Local microbenchmark on Apple Silicon, Python 3.11.2, xxhash 3.7.0
(median of 21 runs, 50 K hashes per round; end-to-end uses 1 K texts of
50–150 Zipfian-English tokens with the cache cleared between runs):

| Scenario                                | Speedup (xxh3 vs blake2b) |
| --------------------------------------- | ------------------------- |
| Raw digest, short keys (2–6 chars)      | 1.31×                     |
| Raw digest, Zipfian English (~3 chars)  | 1.34×                     |
| Raw digest, long keys (40–80 chars)     | 1.33×                     |
| End-to-end `compute_simhash` (cache cleared) | 1.05×                |

xxhash's well-known "4–10× faster than crypto hashes" figure refers to
C-level pure-hash benchmarks; the Python wrapping (UTF-8 encode → call →
`intdigest`) levels the field. The bigger wall-clock win in real audits
comes from the token-level `lru_cache` — Zipfian token frequency means
~10 K cache slots cover the vast majority of a corpus's traffic, so a
second pass over the same corpus runs almost entirely from cache.

The benchmark script is at `tools/bench_simhash.py` (run with
`python tools/bench_simhash.py`); it is not part of the regular `pytest`
suite because it is wall-clock-noisy.

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

`v0.5.2` ([Phase 12 — Data Curation Maturity](phase-12-data-curation-maturity.md)) is the direct continuation of this lineage: MinHash LSH dedup for >50K-row corpora, markdown-aware splitter, code/secrets leakage scan, heuristic quality filter, DOCX/Markdown table preservation. Driven by the post-`v0.5.1` competitive review that compared ForgeLM's ingestion + audit against LLaMA-Factory / Axolotl / Unsloth / NeMo Curator / Dolma / RedPajama / LlamaIndex / LangChain / Marker / Docling.

`v0.5.3` ([Phase 14 — Multi-Stage Pipeline Chains](phase-14-pipeline-chains.md)) was reslotted from `v0.5.2` so the ingestion/audit lineage finishes uninterrupted before the trainer-orchestration surface gets reshaped.
