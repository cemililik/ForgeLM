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
`data_audit_report.json` is written there. Stdout shows a human-readable
summary; pass `--output-format json` to get the full report on stdout for
CI/CD consumption.

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
| `dir/` containing other `*.jsonl` | Each `*.jsonl` becomes a pseudo-split named after the file stem |

The auditor reads the first text-bearing column it finds, in this priority:
`text` → `content` → `completion` → `prompt`. For `messages`-format chat
data, the role-tagged content is concatenated.

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
from forgelm.data_audit import audit_dataset, asdict

report = audit_dataset("data/sft.jsonl", output_dir="./audit/")
print(report.total_samples, report.pii_summary)

# Or serialize manually:
import json
json.dump(asdict(report), open("custom_path.json", "w"), indent=2)
```

`AuditReport` is a plain dataclass — `dataclasses.asdict()` gives you a
JSON-ready dict. The PII regex helpers (`detect_pii`, `mask_pii`) and the
simhash function (`compute_simhash`) are also part of the public API.
