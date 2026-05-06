# Phase 12: Data Curation Maturity

> **Note (post-consolidation):** Originally targeted `v0.5.2`, now ships
> as part of the consolidated `v0.5.0` release alongside Phases 11, 11.5,
> and 12.5 — see [releases.md](releases.md#v050-document-ingestion-data-curation-pipeline).
> Version-label references below preserve the historical planning trail.
>
> **Status:** ✅ **Tier 1 DONE** — landed on `development` for the (originally) `v0.5.2` cycle. All five must-have tasks shipped: MinHash LSH dedup option (`[ingestion-scale]` extra via `datasketch`), markdown-aware splitter (`--strategy markdown`), code/secrets leakage tagger (`[ingestion-secrets]` extra via `detect-secrets` with regex fallback), heuristic quality filter (`--quality-filter`), DOCX/Markdown table preservation. Tier 2 (Presidio adapter, Croissant metadata) and Tier 3 (`--all-mask` composite, wizard "audit first" hook) are deferred to a follow-up **Phase 12.5** backlog file (analogous to Phase 11.5 → `phase-11-5-backlog.md`). Modules: [`forgelm/data_audit.py`](../../forgelm/data_audit/), [`forgelm/ingestion.py`](../../forgelm/ingestion.py), [`forgelm/cli.py`](../../forgelm/cli/); tests: [`tests/test_data_audit_phase12.py`](../../tests/test_data_audit_phase12.py), [`tests/test_ingestion_phase12.py`](../../tests/test_ingestion_phase12.py); CLI tests added in [`tests/test_cli_subcommands.py`](../../tests/test_cli_subcommands.py).

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md). Phase 11 + 11.5 built the ingestion / audit lineage (Phase 11 → `v0.5.0`, Phase 11.5 → `v0.5.1`); this phase moves the same lineage from **enterprise-acceptable** to **enterprise-competitive**.

**Goal:** Mature ForgeLM's `forgelm ingest` + `forgelm audit` layer along three axes — **scale** (LSH-based near-duplicate detection beyond ~50K rows, large-corpus throughput), **security** (code/secret leakage scanning + optional ML-based PII), and **quality** (markdown-aware chunking + heuristic quality filters + table structure preservation). The competitive review that followed Phase 11.5 (see `docs/roadmap/phase-11-5-backlog.md` "Measured speedups" section + the 2026-04-27 ingestion-comparison synthesis) lists the exact gaps this phase closes.

**Estimated Effort:** Medium (4-6 weeks) — **Actual: ~1 day** (single-author implementation, leveraging the streaming aggregator + tier-mapped pattern from Phase 11.5).
**Priority:** High — answers the enterprise demand surfaced after the `v0.5.0` PyPI launch; sequences naturally with Phase 14 (Multi-Stage Pipeline Chains), which is reslotted to `v0.5.3`.

> **Context:** Phase 11 shipped multi-format extraction (PDF/DOCX/EPUB/TXT/MD) + paragraph/sliding chunkers; Phase 11.5 added token-aware chunking, PDF page-level header/footer dedup, the `forgelm audit` subcommand, PII severity tiers, LSH-banded simhash dedup, and atomic JSON writes. The cross-tool comparison (LLaMA-Factory / Axolotl / Unsloth / NeMo Curator / Dolma / RedPajama / LlamaIndex / LangChain / Marker / Docling) found ForgeLM **uncontested** in the *fine-tuning + compliance* niche but **behind** in four concrete areas: (1) MinHash LSH dedup for >50K-row corpora, (2) heading-preserving markdown chunking, (3) code / credential leakage scanning, (4) DOCX/PDF table structure preservation. This phase closes those four. Layout-aware PDF parsing (Marker/Docling delegation) and embedding-based semantic dedup are **deliberately deferred to Phase 13+** — adding either would require runtime ML dependencies that conflict with `docs/marketing/strategy/05-yapmayacaklarimiz.md` ("we don't write our own quantization / VLM") and the air-gapped reproducibility guarantees Annex IV depends on.

## Tasks

### Tier 1 — Must-have (Phase 12's thesis)

1. [x] **MinHash LSH dedup option** (`[ingestion-scale]` extra, `datasketch>=1.6.0,<2.0.0`)
   `find_near_duplicates` and `_count_leaked_rows` keep simhash + LSH banding as the **default**; an opt-in `--dedup-method minhash --jaccard-threshold 0.85` route delegates to [datasketch](https://github.com/ekzhu/datasketch) `MinHashLSH`. Simhash is ideal up to ~50K rows; MinHash LSH is the industry standard above that scale (NeMo Curator, Dolma, RedPajama all use it). Surface contract:
   ```bash
   forgelm audit data/large_corpus.jsonl --dedup-method minhash --jaccard-threshold 0.85
   ```
   ```python
   # Programmatic:
   forgelm.data_audit.audit_dataset(..., dedup_method="minhash", minhash_jaccard=0.85)
   ```
   `cross_split_overlap` and `near_duplicate_pairs` share the same method parameter. Audit JSON gains `near_duplicate_summary.method: "minhash" | "simhash"`; default-method audits stay **schema-additive** (older parsers reading `pairs_per_split` keep working unchanged) — the on-disk JSON is *not* byte-identical because `near_duplicate_summary.method` and `cross_split_overlap.method` are now always present alongside the existing fields.

2. [x] **Markdown-aware splitter** (new third strategy: `--strategy markdown`)
   `_chunk_markdown(text, max_chars_or_tokens, ...)` parses heading hierarchy (`# H1` / `## H2` / `### H3`); breaks chunks at heading boundaries; inlines the heading path **into the chunk body** (`# H1 / ## H2\n\n…`) rather than as a separate metadata field — output stays `{"text": "..."}` JSONL so SFT loss benefits from the heading signal. Code-block (` ``` `) and list-item boundaries are preserved (no mid-code-block splits). Composes with token-aware mode: `--strategy markdown --chunk-tokens 1024 --tokenizer Qwen/Qwen2.5-7B-Instruct`. Existing `paragraph` and `sliding` behaviour stays byte-identical.

3. [x] **Code / secrets leakage tagger** (`[ingestion-secrets]` extra, `detect-secrets>=1.5.0,<2.0.0`)
   Audit gains a `secrets_summary` block: AWS / GCP / Azure access keys, GitHub / GitLab / Slack tokens, OpenSSH / PGP private-key headers, JWT, OpenAI API keys (`sk-…`), generic high-entropy strings. Audit JSON shape:
   ```json
   {
     "secrets_summary": {
       "total": 3,
       "by_type": {"aws_access_key": 1, "github_token": 2},
       "lines_flagged": 3
     }
   }
   ```
   Ingest side: `--secrets-mask` flag mirrors `--pii-mask`'s helper pattern, replacing detected spans with `[REDACTED-SECRET]`. The `detect-secrets` package is optional; without it a regex-only fallback set (~10 common patterns) runs and an INFO log says *"install `forgelm[ingestion-secrets]` for full coverage"*. Compliance angle is **critical** — credentials leaked into an SFT corpus are memorised by the trained model; Phase 12 is the first line of defence for this risk class.

4. [x] **Heuristic quality filter** (audit-side, opt-in `forgelm audit --quality-filter`)
   Classic Gopher / C4 / RefinedWeb heuristics: mean-word-length (flag if outside 3-12 chars), alphabetic-character ratio (< 70 % → flag), end-of-line punctuation ratio (< 50 % → flag), repeated-line ratio (top-3 distinct lines covering > 30 % of non-empty lines → flag), short-paragraph ratio (`\n\n`-separated blocks with < 5 words, > 50 % of total → flag). Markdown fenced code blocks are stripped before heuristics run so legitimate code rows don't trip the prose-oriented checks. Opt-in default-off; new `quality_summary`:
   ```json
   {
     "quality_summary": {
       "samples_flagged": 47,
       "by_check": {
         "low_alpha_ratio": 12,
         "low_punct_endings": 8,
         "abnormal_mean_word_length": 3,
         "short_paragraphs": 27,
         "repeated_lines": 5
       },
       "overall_quality_score": 0.94
     }
   }
   ```
   ML-based classifiers (NeMo Curator's fastText / DeBERTa quality model) are **out of scope** — deferred to Phase 13+ (model dependency, non-deterministic, reproducibility risk).

5. [x] **DOCX / Markdown table preservation**
   `_extract_docx` replaces the current `" | "` flat join with markdown table syntax:
   ```text
   | Header 1 | Header 2 | Header 3 |
   |---|---|---|
   | Cell A1  | Cell A2  | Cell A3  |
   ```
   PDF tables stay flat — `pypdf`'s table support is weak and Docling delegation is Phase 13+ scope. The Markdown extractor (`.md` route) already expects markdown, so the new strategy aligns naturally. SFT use cases where this matters (code-assistant, financial-assistant, tabular Q&A) get a noticeable lift; that lift is measured post-merge, not gated on Phase 12 acceptance.

### Tier 2 — Should-have (Phase 12 if scope allows; otherwise Phase 12.5)

6. [ ] **Presidio adapter** (`[ingestion-pii-ml]` extra, optional)
   ForgeLM keeps the regex + Luhn + TC Kimlik checksum PII detector as the **default**. `--pii-engine presidio` opts into Microsoft Presidio for the ML-NER signals regex misses (person names, organisations, locations). Presidio output maps into the existing `pii_severity` table with a new tier (`person_name` → medium, `organization` → low). Scope is ingest-side only; audit contract is unchanged. Fallback: missing Presidio → INFO log *"install `forgelm[ingestion-pii-ml]` for ML-based detection"*.

7. [ ] **Croissant metadata compatibility** (audit JSON, optional)
   Audit report gains a top-level `croissant_compatible: true` flag plus a subset of Google's [Croissant ML metadata](https://github.com/mlcommons/croissant) schema fields (`@type: "sc:Dataset"`, `name`, `description`, `recordSet`, …). Combined with the EU AI Act Article 10 governance bundle, this produces a **dual-standard** artifact — both Croissant consumers and AI Act auditors can parse the same file. Opt-in: `--croissant` flag or programmatic `croissant=True`. Existing audit consumers are unaffected (additive only).

### Tier 3 — Could-have (skip if scope is exhausted)

8. [ ] **`forgelm ingest --secrets-mask` + `--pii-mask` composite flag**
   Runs both masking passes sequentially in one ingest pass (secrets first — high-entropy spans masked; PII second — remaining spans). Order matters because some secrets (GitHub tokens) partially match PII regexes (`de_id`-shaped). Single-flag shorthand: `--all-mask` enables both. Test: known fixtures combining secrets + PII, roundtrip + masked-output coverage.

9. [ ] **Wizard "audit first" entry point**
   Phase 11.5 added the ingest-first hook. Phase 12 mirrors it for symmetry: when the user provides a JSONL path, the wizard offers to run `forgelm audit` automatically; the summary is printed to stdout and the user decides whether to proceed based on the leakage / PII / quality verdicts. UX shape: *"Detected 18 emails, 1 critical-tier PII (credit card), and 7 near-duplicate pairs in your dataset. Continue training?"*. New helper: `_offer_audit_for_jsonl`.

## Won't-do (deliberately out of Phase 12 scope)

- ❌ **VLM-based PDF parsing** (Marker / Docling / Nemotron-Parse) — Phase 13+ scope. ForgeLM holds the "we don't write our own VLM" line (`docs/marketing/strategy/05-yapmayacaklarimiz.md`); even external delegation (Docling) adds runtime weight + risks the air-gapped guarantee. Ships as a separate optional extra in a later phase.
- ❌ **Embedding-based semantic dedup** (NeMo Curator `semantic.py` analogue) — runtime embedding-model dependency + non-deterministic chunk counts violate Annex IV reproducibility. Deferred to Phase 13+ (only viable if a deterministic-snapshot mode is designed first).
- ❌ **Built-in OCR** — out of scope since Phase 11; docs already point at Tesseract / AWS Textract recipes. This stays unchanged.
- ❌ **ML-based quality classifier** (fastText / DeBERTa) — non-deterministic + model-snapshot dependency. The heuristic filter in Tier 1 #4 is sufficient for this phase; classifiers are Phase 13+.
- ❌ **GPU/Ray-scale execution** (NeMo Curator territory) — ForgeLM's niche is *small-to-medium corpus, enterprise compliance*. 8 TB pretraining curation is NeMo Curator's job; ForgeLM should be sufficient for 100K–1M-row SFT corpora, which Phase 12 (streaming + LSH) achieves without distributed runtime.
- ❌ **HTML extractor** — useful for enterprise scrape (intranet wikis) but scope creep. Operators can pre-process with BeautifulSoup; ForgeLM doesn't need to ingest HTML directly.

## Requirements

- **Backward compatibility**: Default-flag `forgelm ingest` and `forgelm audit` outputs are **schema-additive** with v0.5.1 (older parsers keep working) — they are *not* byte-identical because new always-on fields (`secrets_summary`, `near_duplicate_summary.method`, `cross_split_overlap.method`) are now part of every report. v0.5.1 audit consumers must parse v0.5.2 reports without changes; the stdout JSON envelope retains the v0.5.1 `near_duplicate_pairs_per_split` key alongside the richer `near_duplicate_summary`.
- **Optional extras**: Every new heavy dependency (`datasketch`, `detect-secrets`, `presidio-analyzer`) goes under `pyproject.toml` `[project.optional-dependencies]` with the `ImportError` + install-hint pattern from `docs/standards/architecture.md` §3.
- **Determinism**: Every new path (MinHash, markdown chunker, secrets scan, quality heuristics) preserves the fixed-input → fixed-output contract. Annex IV reproducibility guarantee.
- **CLI**: All new flags appear in `forgelm audit --help` and `forgelm ingest --help`; `--output-format json` envelope is additive.
- **Compliance**: New audit fields (`secrets_summary`, `quality_summary`) are auto-inlined into the governance bundle by `forgelm/compliance.py::_maybe_inline_audit_report` without code changes — the existing `json.load` path passes them through as-is.
- **Documentation**: `docs/guides/ingestion.md` + TR mirror, `docs/guides/data_audit.md` + TR mirror, `docs/qms/sop_data_management.md` (new SOP step for secrets scan + quality filter), `CHANGELOG.md`, `docs/reference/usage.md` + TR mirror, `docs/standards/architecture.md` extras matrix.
- **Tests**: At least three tests per Tier 1 task (happy path + edge case + extras-skip). MinHash needs a `test_minhash_parity_with_simhash_at_default_threshold` (LSH parity-style). Markdown splitter needs a heading-preservation test. Secrets needs known-fixture roundtrip + mask test.
- **Smoke**: `forgelm --config config_template.yaml --dry-run` must produce v0.5.1-equivalent output; new flags have no effect on dry-run.
- **Lint + coverage**: ruff clean, coverage stays at `fail_under=40` (Phase 12 adds new code; tests must not drop the floor).

## Kill criteria

For the quarterly gate review:

- **Tier 1 task #1 (MinHash LSH)**: If it doesn't land within 6 weeks **and** a 100K-row smoke fixture under `forgelm audit --dedup-method minhash` doesn't beat the brute-force O(n²) baseline by ≥ 5× → demote to Tier 2, keep simhash as default, push the MinHash extra to v0.5.3.
- **Tier 1 task #4 (Quality filter)**: If false-positive rate on industry benchmark fixtures exceeds 10 % → opt-in default-off (already the plan), document the limitation, add a *"calibrate before applying"* note for operators.
- **Compatibility regression**: If a v0.5.1 audit consumer (the Phase 11/11.5 compliance bundle inliner) cannot parse a v0.5.2 report → kill, roll back any non-additive changes.
- **Performance regression**: If the default simhash path slows by > 5 % vs. the Phase 11.5 baseline (`tests/bench_simhash.py`) → revisit the refactor.

If fewer than three Tier 1 items land within three months, Phase 12 is reset; the "Data Curation Maturity" thesis is re-examined (refresh the competitive analysis, ask whether it's still the right work).

## Delivery

- **Target release: `v0.5.2`** — natural continuation of Phase 11.5 (`v0.5.1`). Phase 14 (Multi-Stage Pipeline Chains) is reslotted from `v0.5.2` to `v0.5.3`.
- Phase 14 reslot rationale: Phase 12 is an extension of the ingestion lineage and shares thematic continuity with Phase 11.5; Phase 14 is an independent feature whose 3-6-week scope can run after Phase 12 with a parallel implementer. Phase 14 has high enterprise demand, but the EU AI Act enforcement deadline (August 2026) gives the audit / secrets surface higher near-term weight.
- Phase 13 (Pro CLI) `v0.6.0-pro` — after Phase 12 + 14, traction-gated.
- Roadmap table (`docs/roadmap.md` + TR mirror), the mermaid diagram, and `releases.md` are all updated by this phase doc; this file pins those commitments.

## Module touchpoints

| Module | Change | Risk |
|---|---|---|
| `forgelm/data_audit.py` | `compute_minhash`, `find_near_duplicates_minhash`, `_count_leaked_rows_minhash` (parallel API surface); `secrets_summary` builder; `quality_summary` builder; `audit_dataset(..., dedup_method=...)` parameter | Low — additive; default behaviour preserved |
| `forgelm/ingestion.py` | `_chunk_markdown`, `_strategy_dispatch` "markdown" branch; `_extract_docx` markdown-table output; `--secrets-mask` extractor wiring | Low-medium — DOCX output shape changes; v0.5.1 fixtures must update |
| `forgelm/cli.py` | `--strategy markdown`, `--dedup-method`, `--jaccard-threshold`, `--quality-filter`, `--secrets-mask`, `--pii-engine`, `--croissant` flags | Low — argparse additions only |
| `forgelm/wizard.py` | (Tier 3) `_offer_audit_for_jsonl` helper; BYOD path post-validation hook | Low — opt-in pattern, symmetric with the existing `_offer_ingest_for_directory` |
| `pyproject.toml` | New extras: `[ingestion-scale]` (datasketch), `[ingestion-secrets]` (detect-secrets), `[ingestion-pii-ml]` (presidio-analyzer); version bump `0.5.1rc1 → 0.5.2rc1` | Low |
| `docs/guides/{ingestion,data_audit}{,-tr}.md` | New sections: markdown splitter, secrets scan, quality filter, MinHash; legacy CLI patterns preserved | Low |
| `docs/qms/sop_data_management.md` | Quality-check checklist gains `--quality-filter` + secrets-scan rows; v0.5.1 `forgelm audit` is already documented (Phase 11.5 update) | Low |
| `docs/standards/architecture.md` | Extras matrix gains `ingestion-scale`, `ingestion-secrets`, `ingestion-pii-ml` rows | Low |
| `CHANGELOG.md` | New "Unreleased — Phase 12 (Data Curation Maturity, targeting v0.5.2)" section | Low |

## Suggested sequencing (4-6 week plan)

| Week | Work | Output |
|---|---|---|
| 1 | Tier 1 #1 — MinHash LSH dedup + datasketch extra + tests | `compute_minhash`, parity test, `--dedup-method` flag |
| 2 | Tier 1 #2 — Markdown splitter + token-aware composition + tests | `_chunk_markdown`, `--strategy markdown`, heading-preservation test |
| 3 | Tier 1 #3 — Code/secrets scan + extra + ingest `--secrets-mask` + tests | `secrets_summary`, detect-secrets integration, mask roundtrip test |
| 4 | Tier 1 #4 + #5 — Quality filter + DOCX table preservation + tests | `quality_summary`, markdown-table output, fixture tests |
| 5 | Tier 2 #6 — Presidio adapter (if scope allows) + Tier 2 #7 Croissant metadata | `--pii-engine presidio`, `--croissant` flag |
| 6 | Docs + roadmap + smoke + tag prep | Guides, CHANGELOG, releases.md, `v0.5.2rc1` |

Tier 3 items (composite mask, wizard audit-first) either join Weeks 5-6 if scope permits, or move to a Phase 12.5 backlog file.

---
