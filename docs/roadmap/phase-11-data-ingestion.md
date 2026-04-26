# Phase 11: Document Ingestion & Data Audit

> **Status:** ✅ **DONE** — landed on `development` for the `v0.5.0` cycle. Modules: [`forgelm/ingestion.py`](../../forgelm/ingestion.py), [`forgelm/data_audit.py`](../../forgelm/data_audit.py); CLI: `forgelm ingest <path>` + `forgelm --data-audit <path>`; tests: [`tests/test_ingestion.py`](../../tests/test_ingestion.py), [`tests/test_data_audit.py`](../../tests/test_data_audit.py); docs: [`docs/guides/ingestion.md`](../guides/ingestion.md), [`docs/guides/data_audit.md`](../guides/data_audit.md). The `v0.5.0` git tag and PyPI publish are the remaining release-engineering steps.

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md).

**Goal:** Turn raw domain documents (PDF, DOCX, EPUB, TXT, plus structured sources) into training-ready JSONL, with automatic data quality reports that plug into EU AI Act Article 10 data governance.
**Estimated Effort:** Medium (1-2 months) — **Actual: 1 day**
**Priority:** High — enterprise onboarding accelerator; bridges ingestion → training → compliance audit in one tool.

> **Context:** Dataset loading today goes through HuggingFace `load_dataset` + JSONL/CSV/Parquet. Enterprises arriving with directories of PDFs (legal, medical, policy manuals) have to write custom preprocessing. This module removes that friction and simultaneously generates governance artifacts that satisfy Article 10 (data collection method, quality metrics, bias declarations).

### Tasks:

1. [x] **`forgelm/ingestion.py` — multi-format → JSONL**
   Parsers for PDF (`pypdf`), DOCX (`python-docx`), EPUB (`ebooklib` + `beautifulsoup4`), plain TXT. Chunking strategies: `sliding` (fixed token window with overlap), `paragraph` (semantic boundary), `semantic` (optional, embedding-based; external dependency). Output: `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` SFT-compatible JSONL. Optional dependency group: `pip install forgelm[ingestion]`.
   ```bash
   forgelm ingest ./book.epub --chunk 2048 --strategy paragraph --output data/sft.jsonl
   forgelm ingest ./policies/ --recursive --output data/policies.jsonl
   ```

2. [x] **`forgelm/data_audit.py` — dataset quality & governance report**
   Analyzes a JSONL dataset, produces `data_audit_report.json` with: sample count per split, column schema, text length distribution (min/max/mean/p50/p95), language detection (top-3), duplicate / near-duplicate rate (simhash-based), null/empty rate, PII flag counts (regex-based; optional `presidio` integration). Feeds Phase 8 Article 10 artifact (`data_governance_report.json`).
   ```bash
   forgelm --data-audit data/sft.jsonl --output audit/
   ```

3. [x] **PII detection hooks**
   Regex-based detector for: emails, phone numbers (international formats), credit cards (Luhn-validated), IBAN, national IDs (TR, DE, FR, US SSN). Counts flags per sample; optionally masks via `--pii-mask`. Does not block training by default — surfaces in audit report.

4. [x] **Near-duplicate detection across splits**
   Simhash / MinHash across train/validation/test. Reports overlap rate. Critical for fair benchmarking — train-test leakage is a silent quality killer.

### Requirements:
- Ingestion must handle malformed files gracefully (scan PDFs with no text layer → warning + empty result, not crash).
- Audit runs on CPU; no GPU required.
- All outputs integrate with Phase 8 compliance artifacts — data governance report references the audit JSON.
- OCR is out of scope; document this as a limitation and suggest external tooling (Tesseract, AWS Textract).

### Delivery:
- Target release: `v0.5.0`
- Can start after Phase 10.5 (Quickstart) lands; no hard blocker on code, but UX sequencing matters.

---
