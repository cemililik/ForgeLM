---
title: Quality Filter
description: Heuristic filters from Gopher, C4, and RefinedWeb for catching low-quality training rows.
---

# Quality Filter

Not all rows in your training data are equally useful. Boilerplate, OCR errors, repeated lines, and pure-symbol noise dilute the signal. ForgeLM's quality filter applies heuristics drawn from the Gopher, C4, and RefinedWeb research lineages — conservatively, so it never silently drops rows.

## What gets flagged

| Heuristic | What it catches |
|---|---|
| **Low alpha ratio** | `<55%` alphabetic characters — usually code dumps, log spam, or pure symbols. |
| **Abnormal mean word length** | Words averaging `<3` or `>10` characters — often OCR garbage or URL-only rows. |
| **Repeated line ratio** | Rows where `>30%` of lines are duplicated — boilerplate or extraction artifacts. |
| **Short content** | Total length below a configurable minimum — often empty after extraction. |
| **Bullet-only rows** | Rows where `>90%` of lines start with bullet markers — usually extracted nav menus. |
| **Symbol density** | Excessive `_-=#*` density — usually rendered tables or pre-formatted text. |

Each row gets a `quality_flags` list in the audit report. The filter never automatically drops; it's your call.

## Quick example

```shell
$ forgelm audit data/ingested.jsonl
⚠ quality flags:
   short_response: 24
   repeated_lines: 12
   abnormal_word_length: 6
   bullet_only: 3
```

To drop flagged rows:

```shell
$ forgelm audit data/ingested.jsonl --drop-quality-flags --output-clean data/clean.jsonl
✓ dropped 45 rows; wrote data/clean.jsonl (12,355 rows)
```

## Tuning thresholds

```yaml
audit:
  quality_filter:
    enabled: true
    min_alpha_ratio: 0.55              # default 0.55
    min_mean_word_length: 3            # default 3
    max_mean_word_length: 10           # default 10
    max_repeated_line_ratio: 0.30      # default 0.30
    min_content_length: 50             # default 50 characters
    max_bullet_ratio: 0.90             # default 0.90
```

For corpora that legitimately violate one of these (e.g. code-heavy datasets violate alpha ratio), turn off the specific check rather than the whole filter:

```yaml
audit:
  quality_filter:
    enabled: true
    skip: ["min_alpha_ratio"]          # code, math, log datasets
```

## Conservative-by-default

The thresholds are tuned to *flag, not drop*. The reasons:

1. Domain mismatch — a quality filter tuned on web crawls misjudges medical or legal text.
2. Silent dropping is invisible to the user. Better to surface flags and let the human decide.
3. Audit reports are compared across dataset versions; a sudden change in flag counts is informative.

If you want stricter filtering — for instance, on a public web crawl going into pre-training — pair the filter with a manual review of edge cases.

## Programmatic API

```python
from forgelm.data_audit import score_quality

text = "= = = = = = = =\n* * *\n[no content]"
flags = score_quality(text)
print(flags)
# {'low_alpha_ratio': True, 'symbol_density': True, 'short_content': True}
```

## Common pitfalls

:::warn
**Auto-dropping without review.** Set `--drop-quality-flags` carefully — it removes rows without showing you what got removed. Run `forgelm audit` first to inspect what's flagged.
:::

:::warn
**Filtering code datasets with default thresholds.** Code has more symbols and shorter mean word length than prose. Either disable the affected checks or use code-specific thresholds.
:::

## See also

- [Dataset Audit](#/data/audit) — runs the quality filter as part of standard audit.
- [Document Ingestion](#/data/ingestion) — most quality issues originate at extraction time.
