---
title: Near-Duplicate Detection
description: LSH-banded simhash and MinHash LSH for catching near-duplicates in training data.
---

# Near-Duplicate Detection

Duplicates and near-duplicates inflate your training distribution towards whatever's repeated, and — when they straddle train/eval splits — make your evaluation metrics meaningless. ForgeLM ships two algorithms: simhash for accuracy and small-to-medium corpora, MinHash LSH for scale.

## Algorithm choice

| Algorithm | Recall | Speed | Best for |
|---|---|---|---|
| **LSH-banded simhash** (default) | Exact within Hamming threshold | ~50K rows/sec | Corpora < 50K rows |
| **MinHash LSH** | Approximate (>95% of true duplicates) | ~500K rows/sec | Corpora > 50K rows |

ForgeLM auto-selects based on row count — simhash for small, MinHash for large — but you can override via `--dedup-algo`.

## Quick example

```shell
$ forgelm audit data/train.jsonl --dedup-threshold 3
⚠ near-duplicate pairs: 47 (LSH-banded simhash, threshold 3)

$ jq '.near_duplicates[]' audit/data_audit_report.json | head
{"row_a": 1240, "row_b": 4521, "hamming": 1, "similarity": 0.984}
{"row_a": 9012, "row_b": 9013, "hamming": 0, "similarity": 1.0}
```

A `hamming: 0` means *exact* duplicates (same simhash); higher values are progressively less similar.

## Threshold tuning

The `--dedup-threshold` is a Hamming distance on the 64-bit simhash. Defaults are:

| Threshold | Captures | False-positive rate |
|---|---|---|
| 0 | Exact duplicates only | ~0% |
| 1-2 | Trivial-edit duplicates ("Hello!" vs "Hello.") | <1% |
| **3** (default) | Paraphrases with shared structure | 1-2% |
| 5+ | Loose paraphrases; high false-positive rate | 5-15% |

Most teams stick with 3.

## What near-dup catches that exact-match doesn't

```text
Row A: "Welcome to our customer support. How can I help you today?"
Row B: "Welcome to our customer support — how can I help you today?"
```

Exact-match misses these (different punctuation). Simhash with threshold 3 catches them.

```text
Row A: "Send your CV to ali@example.com"
Row B: "Send your CV to ali@example.com or call us"
```

Threshold 3 also catches these (same first half, slight extension).

## Cross-split awareness

Audit runs near-dup detection both *within* and *across* splits. Cross-split duplicates are the high-priority bug — they make your benchmark scores unreliable. Audit's `cross_split_overlap` field reports how many train rows have a near-duplicate in validation or test. See [Cross-Split Leakage](#/data/leakage).

## MinHash LSH for scale

For corpora over 50K rows, switch to MinHash:

```shell
$ forgelm audit data/large.jsonl --dedup-algo minhash --num-perm 256
✓ near-duplicate pairs: 1,247 (MinHash LSH, 256 permutations, threshold 0.85)
```

MinHash trades small accuracy for big speed — typical recall is >95% of true duplicates while running 10× faster than simhash on million-row datasets.

| MinHash flag | Description |
|---|---|
| `--num-perm` | Number of hash permutations (default 128). More = higher accuracy, more memory. |
| `--minhash-threshold` | Jaccard similarity threshold (default 0.85). |
| `--minhash-bands` | LSH banding parameter (default auto-derived from threshold). |

## Streaming behaviour

Both algorithms are streaming — they don't load the whole dataset into memory. A 10M-row corpus dedupes in a few minutes on a laptop CPU.

## Removing duplicates

`forgelm audit` *detects* duplicates; it doesn't remove them by default (data modification is intentional). To deduplicate:

```shell
$ forgelm audit data/train.jsonl --remove-duplicates --output-clean data/train.dedup.jsonl
✓ removed 47 near-duplicate rows; wrote data/train.dedup.jsonl (12,353 rows)
```

When duplicates are within a single split, ForgeLM keeps the first occurrence. Across splits, it keeps the train-side row by default and removes from validation/test (configurable).

## Common pitfalls

:::warn
**Threshold too aggressive.** Hamming threshold 5+ on simhash will flag legitimately different examples as duplicates. Stick with 3 unless you've measured false-positive rate on your specific data.
:::

:::warn
**MinHash permutations too low.** `--num-perm 64` saves memory but recall drops to ~85%. Stay above 128 for production use.
:::

:::tip
**Run dedup BEFORE manually splitting train/val/test.** If your splits are produced upstream and have leakage, you can't fix that with deduplication; you have to re-split. Audit on the combined dataset before splitting catches this.
:::

## See also

- [Dataset Audit](#/data/audit) — runs dedup as part of the standard audit.
- [Cross-Split Leakage](#/data/leakage) — the highest-priority deduplication concern.
- [Quality Filter](#/data/quality-filter) — sister feature for catching low-quality rows.
