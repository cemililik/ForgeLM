# Dataset Audit Guide

`forgelm audit PATH` analyzes a JSONL dataset and produces a
`data_audit_report.json` covering quality, governance, and PII signals.
Phase 11 (introduced in `v0.5.0`) shipped the underlying audit;
Phase 11.5 (`v0.5.1`) promoted it from a top-level flag to a first-class
subcommand and added LSH-banded near-duplicate detection, streaming
JSONL reading, PII severity tiers, an atomic on-disk write, and a
verbose-by-default truncation policy on the human summary.

The report feeds the EU AI Act Article 10 data governance artifact
automatically when present in the trainer's `output_dir`.

---

## Run it

```bash
# Single split (treated as 'train')
forgelm audit data/sft.jsonl --output ./audit/

# Multi-split: directory containing train.jsonl / validation.jsonl / test.jsonl
forgelm audit data/ --output ./audit/

# Show every split (including those with no findings)
forgelm audit data/ --verbose

# Tighter / wider near-duplicate threshold
forgelm audit data/ --near-dup-threshold 5
```

> **Legacy alias:** `forgelm --data-audit PATH` keeps working unchanged
> as a deprecation alias and logs a one-line notice. New scripts should
> use the `audit` subcommand. Removal targeted no earlier than `v0.7.0`.

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
      "train__test": {
        "leaked_rows_in_train": 7,
        "leak_rate_train": 0.0056,
        "leaked_rows_in_test": 7,
        "leak_rate_test": 0.7
      }
    }
  }
}
```

The audit reports leak rate **in both directions** because they tell
different stories. With 1240 train rows and 10 test rows where 7 leak,
`leak_rate_train = 7/1240 = 0.56%` looks negligible but
`leak_rate_test = 7/10 = 70%` is the metric that actually destroys
benchmark fidelity. Always read the smaller-side rate — that is the
silent killer of test integrity.

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

### PII severity tiers (Phase 11.5)

The flat `pii_summary` map gives compliance reviewers no guidance on
*how bad* a finding is. Phase 11.5 adds a `pii_severity` block alongside:

```json
{
  "pii_severity": {
    "total": 25,
    "by_tier": {"critical": 1, "high": 2, "medium": 18, "low": 4},
    "by_type": {
      "credit_card": {"count": 1, "tier": "critical"},
      "tr_id":      {"count": 2, "tier": "high"},
      "email":      {"count": 18, "tier": "medium"},
      "phone":      {"count": 4, "tier": "low"}
    },
    "worst_tier": "critical"
  }
}
```

The tier table is consensus regulatory weighting (PCI-DSS for financial
identifiers; GDPR Art. 9 + ENISA for government IDs). Pipelines that
gate on PII severity should read `pii_severity.worst_tier` and refuse
to publish on `critical` / `high` without explicit review.

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

Phase 11.5 swapped the underlying scan to **LSH banding**: pigeonhole
chooses `bands = threshold + 1`, candidate pairs are exactly the rows
that collide in any band-bucket, and the Hamming check only runs on
candidates. Recall stays exact at the default threshold; cost drops from
`O(n²)` to roughly `O(n × k)` (the `_count_leaked_rows` cross-split
helper uses the same banded shape). The brute-force path remains as the
fallback when the threshold is high enough that bands shrink below
4 bits — `find_near_duplicates` returns the same result either way.

Phase 11.5 also made the simhash backend pluggable:

- **xxhash.xxh3_64** drives the per-token digest when the optional
  `xxhash` dep is installed (now part of `forgelm[ingestion]`); it is
  several times faster than BLAKE2b on short keys.
- **BLAKE2b** is the fallback so a bare install still works.
- A module-scope `lru_cache(maxsize=10_000)` memoises the digest at the
  token level — Zipfian token frequency means the cache covers most of
  a corpus's traffic with a small footprint.

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

```text
forgelm audit PATH \
  [--output DIR] \
  [--verbose] \
  [--near-dup-threshold N] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`PATH` may be a `.jsonl` file or a directory. `--output` defaults to
`./audit/`. `--verbose` shows every split in the human summary even when
it has zero findings (default folds clean splits into one tail line so
multi-split audits stay short — has no effect on the on-disk JSON
report). `--near-dup-threshold N` overrides the default Hamming-distance
cutoff of 3 (≈95 % similarity).

> **Note:** This matches the behavior summarised at the top of this guide:
> `--output-format json` writes a small envelope (success flag, top-level
> metrics, report path) to stdout. The full `data_audit_report.json` is
> always written to `--output` via `tempfile.NamedTemporaryFile` +
> `os.replace` — Phase 11.5 hardening so a crashed audit can never leave
> a half-written report on disk.

The legacy `forgelm --data-audit PATH` flag is preserved as a
deprecation alias and logs a one-line notice. Behaviour is identical;
new scripts should use the subcommand.

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
