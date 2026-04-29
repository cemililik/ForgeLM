---
title: Document Ingestion
description: Convert PDF, DOCX, EPUB, TXT, and Markdown into SFT-ready JSONL with one command.
---

# Document Ingestion

Most fine-tuning datasets don't start as JSONL — they start as PDFs, contracts, EPUBs, or messy Markdown notes. `forgelm ingest` walks your input directory, extracts text in a format-aware way, and emits SFT-ready JSONL.

```mermaid
flowchart LR
    A[Input dir<br/>PDF/DOCX/EPUB/MD] --> B[Format detect]
    B --> C[Extract text<br/>preserve structure]
    C --> D[Chunk by tokens<br/>or by Markdown]
    D --> E[Apply masking<br/>PII + secrets]
    E --> F[Output JSONL]
    classDef io fill:#1c2030,stroke:#0ea5e9,color:#e6e7ec
    classDef step fill:#161a24,stroke:#f97316,color:#e6e7ec
    class A,F io
    class B,C,D,E step
```

## Quick example

```shell
$ forgelm ingest ./policies/ \
    --recursive \
    --strategy markdown \
    --max-tokens 1024 \
    --all-mask \
    --output data/policies.jsonl
✓ scanned 47 files (12 PDF, 8 DOCX, 27 MD)
✓ extracted 12,240 chunks (avg 743 tokens)
✓ masked 18 PII matches, 0 secret matches
✓ wrote data/policies.jsonl (8.2 MB)
```

`--all-mask` is the documented shorthand for `--secrets-mask --pii-mask`
in the right order. See [Combined Masking](#/data/all-mask) for the
full behaviour and set-union semantics.

## Supported formats

| Format | Extractor | Notes |
|---|---|---|
| **PDF** | `pypdf` | Header/footer dedup, table extraction (best-effort). |
| **DOCX** | `python-docx` | Tables emit as Markdown tables; preserves headings. |
| **EPUB** | `ebooklib` | Strips navigation/index; preserves chapter structure. |
| **TXT** | built-in | Treated as one document; chunked by `--max-tokens`. |
| **Markdown** | built-in | Markdown-aware splitter respects heading hierarchy. |

Install the ingestion extras: `pip install 'forgelm[ingestion]'`. See [Installation](#/getting-started/installation).

## Chunking strategies

| Strategy | Behaviour | Best for |
|---|---|---|
| `tokens` | Hard cap at `--max-tokens` per chunk; tries to split on sentence boundaries. | Plain text, mixed content. |
| `markdown` | Splits on Markdown headings (h1/h2/h3), respects hierarchy. | Documentation, structured corpora. |
| `paragraph` | One chunk per paragraph (or merged paragraphs to fit). | Books, prose. |
| `sentence` | One chunk per sentence (rare; for very fine-grained data). | NLI tasks, short Q&A. |

Most teams pick `markdown` for documentation and `tokens` for everything else.

## Output formats

By default, `forgelm ingest` emits the `instructions` format with synthetic prompts:

```json
{"prompt": "Summarise the following passage.", "completion": "Section 4.2 of the policy specifies…", "metadata": {"source": "policy.pdf", "chunk": 17}}
```

For domain-expert SFT, you typically want `--format raw` which emits the chunk as-is and lets you generate prompts later (or use it for continued pre-training):

```json
{"text": "Section 4.2: All payment processing must comply with PCI-DSS standards…", "metadata": {"source": "policy.pdf", "chunk": 17}}
```

For Q&A datasets, use `--format qa` with a prompt-generation LLM:

```yaml
ingestion:
  format: "qa"
  qa_generator:
    model: "openai:gpt-4o-mini"        # or local model
    prompts_per_chunk: 3
```

## CLI flags

| Flag | Description |
|---|---|
| `--recursive` | Walk subdirectories. |
| `--strategy {tokens,markdown,paragraph,sentence}` | Chunking strategy. |
| `--max-tokens N` | Token cap per chunk (default 1024). |
| `--overlap N` | Sliding-window overlap between chunks (default 0). |
| `--pii-mask` | Mask emails, phone, IDs, IBAN before writing. See [PII Masking](#/data/pii-masking). |
| `--secrets-mask` | Redact AWS keys, GitHub PATs, JWTs, etc. See [Secrets Scrubbing](#/data/secrets). |
| `--language LANG` | Force a language (default: auto-detect per chunk). |
| `--include "*.pdf,*.md"` | Glob patterns to include. |
| `--exclude "drafts/*"` | Glob patterns to exclude. |
| `--output PATH` | Output file (`.jsonl`). |

## Common pitfalls

:::warn
**Forgetting `--pii-mask`.** The default is *no* masking, on the principle of "don't silently modify your data". For real corpora, enable it explicitly. The audit step ([Dataset Audit](#/data/audit)) will flag PII regardless, but better to mask at ingest.
:::

:::warn
**Pure-image PDFs.** ForgeLM doesn't ship OCR. If your PDFs are scanned images, run them through Tesseract or a commercial OCR first.
:::

:::warn
**`--max-tokens` larger than the model's context.** Chunks longer than `model.max_length` will be truncated at training time, losing the tail. Match `--max-tokens` to the training context.
:::

:::tip
**Always audit after ingest.** A clean ingest doesn't mean a clean dataset. Run `forgelm audit data/output.jsonl` to check for cross-split leakage, near-duplicates, and PII the masking missed.
:::

## See also

- [Dataset Audit](#/data/audit) — the next step after ingest.
- [PII Masking](#/data/pii-masking) — how the masking works.
- [Dataset Formats](#/concepts/data-formats) — what each output format looks like.
