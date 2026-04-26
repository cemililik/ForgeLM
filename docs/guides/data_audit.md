# Dataset Audit Guide

`forgelm --data-audit` analyzes a JSONL dataset and produces a
`data_audit_report.json` covering quality, governance, and PII signals.
Phase 11; introduced in `v0.5.0`. The report feeds the EU AI Act Article 10
data governance artifact automatically when present in the trainer's
`output_dir`.

---

## Run it

```bash
# Single split (treated as 'train')
forgelm --data-audit data/sft.jsonl --output ./audit/

# Multi-split: directory containing train.jsonl / validation.jsonl / test.jsonl
forgelm --data-audit data/ --output ./audit/
```

`--output` defaults to `./audit/`. The directory is created if missing;
the **full** `data_audit_report.json` is always written there. Stdout shows
a human-readable summary by default; pass `--output-format json` to get
a **summary** JSON envelope (top-level metrics + report path + notes) on
stdout — the full report still lives on disk under `--output`. CI/CD
consumers should slurp the file from `report_path` rather than parsing
the stdout summary when they need every detail.

No GPU required. No network calls. CPU-only.

---

## What you get

### Per-split metrics

```json
{
  "splits": {
    "train": {
      "sample_count": 1240,
      "columns": ["text"],
      "text_length": {"min": 32, "max": 4096, "mean": 1834.2, "p50": 1900, "p95": 3580},
      "null_or_empty_count": 3,
      "null_or_empty_rate": 0.0024,
      "languages_top3": [
        {"code": "tr", "count": 950},
        {"code": "en", "count": 240},
        {"code": "de", "count": 50}
      ],
      "simhash_distinct": 1180,
      "near_duplicate_pairs": 60,
      "pii_counts": {"email": 18, "phone": 4}
    }
  }
}
```

### Cross-split overlap

```json
{
  "cross_split_overlap": {
    "hamming_threshold": 3,
    "pairs": {
      "train__test": {"leaked_rows_in_train": 7, "leak_rate": 0.0056}
    }
  }
}
```

A non-zero leak rate between train and test is a **silent killer of
benchmark fidelity** — fix the splits before training.

### PII summary

```json
{
  "pii_summary": {
    "email": 18,
    "phone": 4,
    "credit_card": 1,
    "tr_id": 2
  }
}
```

Each row's text payload is scanned with regex; credit cards run through
Luhn validation, TR national IDs run through the TC Kimlik No checksum.
Other categories surface on regex shape alone — false positives are
intentional. Mask with `forgelm ingest --pii-mask` (or in your own
preprocessing) before publishing the dataset.

**Pattern precedence is documented.** `_PII_PATTERNS` iteration order
governs both detection priority and mask precedence — most specific
patterns (`email`, `iban`, `credit_card`, national IDs) are scanned
first, then the noisier `phone` pattern. When a span could match two
categories, the first / narrower one wins and the span is replaced
before the next pattern sees it. Phone is intentionally anchored to
`+CC` or `(area)` formats so bare digit runs (timestamps, log line
numbers, ISO dates) do not flag.

### Near-duplicate detection

64-bit simhash over case-folded word tokens, paired with Hamming distance
≤ 3 (the cutoff the simhash paper uses for the canonical web-page-dedup
deployment, ≈95% similarity at this width). Exposes both:

- **Within-split** pairs: `near_duplicate_pairs` per split.
- **Cross-split** leakage: above.

Quadratic in row count; suitable for datasets up to ~50K rows. Larger
corpora need an LSH band index — out of scope for v0.5.0.

---

## Layout requirements

| Input shape | What you get |
|---|---|
| `*.jsonl` file | Single split named `train` |
| `dir/` containing any of `train.jsonl`, `validation.jsonl`, `test.jsonl` | Each present file becomes its own split |
| `dir/` containing common aliases (`dev`, `val`, `valid`, `eval`, `holdout`) | Folded onto canonical split names — `dev.jsonl` → `validation`, `eval.jsonl` → `test`, etc. |
| `dir/` containing only non-canonical `*.jsonl` | Pseudo-split fallback: each `*.jsonl` becomes its own split AND a warning is emitted that cross-split leakage analysis is meaningless without a real partition |

The auditor reads the first text-bearing column it finds, in this priority:
`text` → `content` → `completion` → `prompt`. For `messages`-format chat
data, the role-tagged content is concatenated.

**Schema drift is surfaced.** Heterogeneous JSONL (rows with optional fields)
is allowed — the column schema is the union of keys across rows; any column
that appears after row 0 is reported under `schema_drift_columns` so
operators can decide whether the drift is intentional.

---

## Article 10 governance integration

When `data_audit_report.json` exists in the trainer's `training.output_dir`
at training time, [`generate_data_governance_report`](../../forgelm/compliance.py)
inlines its findings under the `data_audit` key of the governance artifact.
Your compliance bundle becomes a single self-contained document rather than
a pointer to a separate file.

The recommended workflow:

```bash
# Audit first — surfaces issues before you commit to a long training run
forgelm --data-audit data/policies.jsonl --output ./checkpoints/policy-run/

# Train (governance artifact will inline the audit)
forgelm --config configs/policy-run.yaml
```

---

## CLI reference

```
forgelm --data-audit PATH \
  [--output DIR] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`PATH` may be a `.jsonl` file or a directory. `--output` defaults to
`./audit/`.

Top-level flag (not a subcommand) — exits without touching the trainer.

> **Note:** This matches the behavior summarised at the top of this guide:
> `--output-format json` writes a small envelope (success flag, top-level
> metrics, report path) to stdout. The full `data_audit_report.json` is
> always written to `--output`. Read it from disk if you need every detail.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Audit failed: ... not found or empty` | Path doesn't exist or has no `.jsonl` | Verify the path; pass a file or a `train.jsonl` directory layout |
| `"unknown (install forgelm[ingestion])"` in language stats | `langdetect` not installed | `pip install 'forgelm[ingestion]'` |
| Cross-split leakage flags 100% of rows | All splits contain identical content | Re-shuffle; you probably copied the same JSONL into every split |
| `near_duplicate_pairs` enormous on a large dataset | Simhash quadratic ran for tens of thousands of rows | Sample first; LSH index support is a follow-up |

---

## Programmatic API

```python
from dataclasses import asdict
from forgelm.data_audit import audit_dataset

report = audit_dataset("data/sft.jsonl", output_dir="./audit/")
print(report.total_samples, report.pii_summary)

# Or serialize manually:
import json
json.dump(asdict(report), open("custom_path.json", "w"), indent=2)
```

`AuditReport` is a plain dataclass — `dataclasses.asdict()` gives you a
JSON-ready dict. The PII regex helpers (`detect_pii`, `mask_pii`) and the
simhash function (`compute_simhash`) are also part of the public API.
