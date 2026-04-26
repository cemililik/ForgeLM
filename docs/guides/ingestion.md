# Document Ingestion Guide

Convert raw enterprise corpora (PDF / DOCX / EPUB / TXT / Markdown) into the
SFT-ready JSONL ForgeLM trains on. Phase 11; introduced in `v0.5.0`.

> Pair with [`forgelm --data-audit`](data_audit.md) afterwards to surface
> length-distribution / language / near-duplicate / PII metrics, and with
> [`forgelm --generate-data`](../reference/usage.md) if you want the chunks
> expanded into Q&A `messages` form via a teacher model.

---

## Install

```bash
pip install 'forgelm[ingestion]'
```

The extra brings in `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, and
`langdetect`. They are optional because plain text + Markdown work without
any of them. Importing the module does not pull these in unless the matching
extractor is exercised.

OCR is **out of scope.** Scanned PDFs without a text layer surface a warning
and produce zero chunks; pre-process them with Tesseract or AWS Textract
before ingest.

---

## Single command — file in, JSONL out

```bash
forgelm ingest ./book.epub --output data/sft.jsonl
forgelm ingest ./policies/ --recursive --output data/policies.jsonl
forgelm ingest ./scan.pdf --strategy sliding --chunk-size 1024 --overlap 128 \
  --output data/scan.jsonl
```

Output is one chunk per line:

```json
{"text": "Article 10 of the EU AI Act requires high-risk AI providers to ..."}
{"text": "Data quality criteria include relevance, representativeness ..."}
```

The trainer's data loader treats `{"text": "..."}` as a pre-formatted SFT
column (see [`forgelm/data.py`](../../forgelm/data.py)) — no further
preprocessing required.

---

## Chunking strategies

| Strategy | When | Behavior |
|---|---|---|
| `paragraph` (default) | Prose, policy docs, articles | Greedy paragraph packer; never splits a paragraph mid-sentence. |
| `sliding` | Long technical documents, code mixed with prose | Fixed-size character window with `--overlap` for context bleed. |

> Semantic / embedding-based chunking is reserved for a follow-up phase — it
> raises `NotImplementedError` today and is intentionally hidden from the CLI
> `--strategy` choice list to avoid runtime crashes.

`--chunk-size` is measured in **characters, not tokens**. As a rough rule,
`--chunk-size 2048` corresponds to ≈500–700 tokens for typical English /
Turkish text — set the value with `model.max_length` in mind (e.g. a model
with `max_length: 2048` tokens benefits from `--chunk-size 6000-8000` so the
formatter has headroom for system prompt + chat template overhead).
Paragraphs longer than the soft cap are emitted on their own — better than
mid-sentence splits.

**Sliding overlap is bounded.** `--overlap` must be both `< --chunk-size`
*and* `≤ --chunk-size // 2` — values above that explode chunk count
(`--overlap 199 --chunk-size 200` would emit ~one chunk per character).
The CLI rejects pathological combinations up front.

**Files are processed in lexicographic order** (sorted glob result), so a
re-run with the same input + flags produces the same JSONL byte-for-byte.

---

## PII masking on the way in

Add `--pii-mask` to redact emails, phone numbers, credit cards (Luhn-validated),
IBAN, and national IDs (TR Kimlik No, DE Personalausweis, FR INSEE, US SSN)
before any chunk lands in the JSONL:

```bash
forgelm ingest ./customer_emails/ --output data/anon.jsonl --pii-mask
```

Detected spans are replaced with `[REDACTED]`. Detection is regex-based —
false positives are intentional. Audit your output afterwards with
`forgelm --data-audit` to verify.

---

## Recursive directory walk

```
./policies/
├── 2024_q1.pdf
├── 2024_q2.pdf
└── archive/
    ├── 2023.docx
    └── 2022.epub
```

```bash
forgelm ingest ./policies/ --recursive --output data/all_policies.jsonl
```

Files with unsupported extensions (`.png`, `.zip`, etc.) are skipped silently.
Files with supported extensions but no extractable text (scanned PDFs,
empty DOCX) skip with a warning.

**Encrypted PDFs** are caught explicitly: an empty-password decrypt is
attempted automatically (covers owner-encrypted PDFs that are still
readable); if that fails, a `ValueError` surfaces with a recommended
external decrypt path (`qpdf --decrypt input.pdf out.pdf` /
`pdftk input.pdf input_pw <password> output out.pdf`). Wiring a CLI
password flag is intentionally avoided — keeping passwords out of shell
history is safer.

**Binary content masquerading as text** (a `.txt` file that's actually a
zip / image renamed) surfaces a warning when more than 1% of the file
decodes as Unicode replacement characters. The chunks still write —
operators decide whether to keep them — but the warning is loud enough
to catch in CI logs.

---

## End-to-end example

```bash
# 1. Ingest
forgelm ingest ./policies/ --recursive --output data/policies.jsonl

# 2. Audit (catches near-duplicates, PII, length outliers)
forgelm --data-audit data/policies.jsonl --output ./audit/

# 3. (optional) Expand to Q&A via a teacher model
forgelm --config configs/synth.yaml --generate-data

# 4. Train
forgelm quickstart domain-expert --dataset data/policies.jsonl
```

---

## CLI reference

```
forgelm ingest INPUT_PATH \
  --output FILE \
  [--chunk-size N] \
  [--overlap N] \
  [--strategy {sliding,paragraph,semantic}] \
  [--recursive] \
  [--pii-mask] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`--output-format json` emits a machine-readable summary to stdout (file
paths, chunk count, format counts, notes). Useful for CI/CD pipelines.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: PDF ingestion requires the 'ingestion' extra` | Extra not installed | `pip install 'forgelm[ingestion]'` |
| "No extractable text in '<x>.pdf'" warning + 0 chunks | Scanned PDF, no text layer | OCR first (Tesseract / AWS Textract) |
| `FileNotFoundError: No supported files found at '<dir>'` | Directory has only unsupported extensions | Verify file extensions match `.pdf / .docx / .epub / .txt / .md` |
| `ValueError: overlap must be in [0, chunk_size)` | `--overlap >= --chunk-size` | Reduce `--overlap` |

---

## Limitations

- **OCR:** out of scope. Use external tooling — see the worked example below.
- **Tables / figures:** PDF/DOCX tables are flattened to plain text. Structure is lost.
- **Metadata:** title / author / page numbers are dropped — only body text reaches the JSONL.
- **Encoding:** non-UTF-8 input is read with `errors="replace"`; binary noise becomes Unicode replacement characters.
- **Semantic chunking:** raises `NotImplementedError` until embedding support lands in a follow-up phase.

---

## Working with scanned PDFs (OCR handoff)

`forgelm ingest` does not perform OCR. Scanned PDFs without a text layer
surface as a warning and emit zero chunks. The clean way is to OCR
externally first, then pipe the result through ingestion. Two recipes,
in increasing order of cost:

### Recipe A — Tesseract (local, free)

```bash
# Install once.
brew install tesseract            # macOS
# or: sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng  # Debian/Ubuntu

# 1. Convert each scanned PDF page to a searchable PDF (text layer added).
ocrmypdf scan_input.pdf scan_with_text_layer.pdf --language eng+tur

# 2. Now ingest as a normal text-bearing PDF.
forgelm ingest scan_with_text_layer.pdf --output data/scan.jsonl
```

`ocrmypdf` is the recommended wrapper — it handles deskew, page rotation,
and writes a hidden text layer rather than burning OCR'd characters into
the visual layer. Pure `tesseract` works too if you only need plain text:

```bash
# Per-page extraction, concatenate to a TXT, ingest the TXT.
pdftoppm -r 300 scan_input.pdf scan_page -png
for img in scan_page-*.png; do tesseract "$img" - >> scan_pages.txt; done
forgelm ingest scan_pages.txt --output data/scan.jsonl
```

### Recipe B — AWS Textract (cloud, paid; better on tables / forms)

```bash
# 1. Upload scanned PDFs to S3.
aws s3 cp scan_input.pdf s3://my-ingest-bucket/scan_input.pdf

# 2. Start an async Textract job. (See AWS Textract docs for the polling
#    + SNS notification pattern; a complete shell loop is out of scope.)
aws textract start-document-text-detection \
    --document-location "{\"S3Object\":{\"Bucket\":\"my-ingest-bucket\",\"Name\":\"scan_input.pdf\"}}"

# 3. Once the job finishes, dump LINE blocks to text and ingest.
python -c "
import boto3, sys
client = boto3.client('textract')
job = sys.argv[1]
result = client.get_document_text_detection(JobId=job)
for block in result['Blocks']:
    if block['BlockType'] == 'LINE':
        print(block['Text'])
" $JOB_ID > scan_textract.txt
forgelm ingest scan_textract.txt --output data/scan.jsonl
```

Textract is materially better than Tesseract on:
- Multi-column layouts (academic papers, magazines)
- Mixed-language pages
- Forms / tables (separate `start-document-analysis` API)

The trade-off is per-page cost (~$0.0015 / page for text detection at
the time of writing) and a network dependency.

### What about forms with PII?

Pre-process with `--pii-mask` after OCR, before publishing the dataset:

```bash
ocrmypdf medical_scan.pdf medical_with_text.pdf --language tur+eng
forgelm ingest medical_with_text.pdf --output data/medical.jsonl --pii-mask
forgelm --data-audit data/medical.jsonl --output ./audit/
```

The audit step verifies redaction worked: any remaining PII flag in
`data_audit_report.json` is a row that escaped masking.

For larger corpora or a domain with lots of jargon, consider running
`forgelm --generate-data` (synthetic data pipeline) on the ingested JSONL
to expand a small seed into many Q&A pairs before fine-tuning.
