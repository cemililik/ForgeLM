# Phase 11.5 — Ingestion / Audit follow-up backlog

Items deliberately scoped out of Phase 11 (`v0.5.0`). Tracked here so a
future minor / patch release can pick them up in priority order. Each row
is small enough to land as its own focused PR.

| # | Item | Why deferred | Effort | Impact |
|---|---|---|---|---|
| **1** | LSH banding for near-duplicate detection | Current implementation is `O(n²)` and documented to top out around ~50K rows. LSH bands (4 × 16-bit on the 64-bit fingerprint, hash-bucket lookup) drop average-case to `O(n × k)`. | M | Unblocks audits on 100K+ row corpora |
| **2** | Streaming `_read_jsonl_split` | Current implementation slurps the whole split into RAM (~400 MB for 100K × 4 KB rows). A generator-based audit pipeline would allow line-at-a-time processing. | M | RAM-bounded audits on large datasets |
| **3** | Token-aware `--chunk-size` for ingestion | Today the cap is char-based. Optional `--chunk-tokens` flag with a tokenizer arg would let operators size chunks against `model.max_length` directly. | S | Fewer surprises when sizing for tokenizer-bound models |
| **4** | PDF page-level header / footer dedup | Repeated page headers (company watermark, page number) end up in every chunk and inflate near-duplicate counts. Common-prefix / common-suffix detection across pages would clean this. | S | Reduces audit false-positives on long PDFs |
| **5** | Token MD5 cache in `compute_simhash` | Each row re-hashes every token. Common tokens ("the", "and") would benefit from a `functools.lru_cache`-backed memo. 2-5× speedup expected on long corpora. | XS | Faster audits |
| **6** | xxhash backend for simhash | MD5 is fine but not optimised; xxhash is non-crypto and substantially faster. Drop-in replacement once the dep is added under the `[ingestion]` extra. | XS | Throughput |
| **7** | Audit progress bar (`tqdm`) | 30K-row audit runs ~3-5 minutes silent. A `--progress` flag emitting a `tqdm` bar (or fallback `logger.info` every N rows) closes the UX gap. | XS | Operator-facing UX |
| **8** | `forgelm audit` as a proper subcommand | Today `--data-audit` is a top-level flag sharing `--output` with `--compliance-export`. Promoting it to a subcommand (`forgelm audit <path>`) lets each mode own its `--output` default. Breaking change — defer until 0.6.0 or wrap in alias. | S | Cleaner CLI surface |
| **9** | PII severity tiers | Today `pii_summary` is a flat count map. Categorising into `low / medium / high / critical` (e.g. `credit_card` → critical, `phone` → low) would give compliance reviewers a one-glance verdict. | S | Compliance UX |
| **10** | `summarize_report` truncation policy | 10-split summary spans 100+ lines. A `--verbose` flag (or default truncation showing only "issues") would help TUI navigation. | XS | Operator-facing UX |
| **11** | Structured ingestion notes | `IngestionResult.extra_notes` is currently a free-text string list. Promoting to `{key: value}` dicts (e.g. `{"skipped_files": 3}`) would make programmatic consumption easier. | XS | Library-side UX |
| **12** | Wizard "ingest first" entry point | Today the wizard hints at `forgelm ingest` when a directory is given as a dataset path. A first-class wizard option ("I have raw documents") routing to ingest could close the loop. | S | Onboarding UX |
| **13** | OCR handoff documentation | Out of scope for ingestion itself, but a worked example pairing Tesseract / AWS Textract output with `forgelm ingest` would stop "OCR is out of scope" from being a dead-end. | XS | Onboarding |
| **14** | `ebooklib.read_epub(options=…)` deprecation | Newer ebooklib versions emit a deprecation warning when `options` is omitted. Set `options={"ignore_ncx": True}` (or whatever the upstream recommends) to silence. | XS | Cleanliness |
| **15** | Output-path race window | `output_dir` is `mkdir`'d then `open`'d non-atomically. Low risk in practice (operator-controlled tmp dir) but a `tempfile.NamedTemporaryFile` + atomic-rename pattern would tighten it. | XS | Defensive depth |

## Picking up an item

1. Open an issue referencing the item number above.
2. PR scope: ONE row per PR.
3. Update this file when the row lands — strike through and link the
   commit / PR.
4. If a row turns out to be the wrong shape, edit it here before doing the
   work. Stale backlog rows are worse than missing rows.
