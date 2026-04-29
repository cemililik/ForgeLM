---
title: Combined Masking (--all-mask)
description: One-flag shorthand for combined PII + secrets scrubbing on ingest.
---

# Combined Masking — `--all-mask`

`--all-mask` is a CLI shorthand that runs both [Secrets Scrubbing](#/data/secrets) and [PII Masking](#/data/pii-masking) on the same ingest pass, in the documented order (secrets first, PII second). It exists purely as ergonomics — no new detector, no new behaviour.

## Why it exists

The "scrub everything detectable before training on shared corpora" workflow is common enough that operators were typing both flags together every time:

```shell
$ forgelm ingest ./mixed_corpus/ --secrets-mask --pii-mask --output data/clean.jsonl
```

`--all-mask` collapses that to one flag:

```shell
$ forgelm ingest ./mixed_corpus/ --all-mask --output data/clean.jsonl
```

The two forms produce byte-identical output. The shorthand is purely UX.

## How it composes

`--all-mask` is **additive** with the explicit flags. All three of these run the same two detectors:

```shell
$ forgelm ingest ./input/ --all-mask                    --output out.jsonl
$ forgelm ingest ./input/ --all-mask --pii-mask         --output out.jsonl
$ forgelm ingest ./input/ --all-mask --secrets-mask     --output out.jsonl
$ forgelm ingest ./input/ --all-mask --pii-mask --secrets-mask --output out.jsonl
```

This is a deliberate design choice — set-union semantics mean a future script that always passes `--pii-mask` (because it's an old habit) won't break when `--all-mask` enters the mix. There's no error, no conflict; both flags just stay True.

## Mask order

When both subsystems run, **secrets are masked first**, then PII. This ordering matters because:

1. Some credential shapes (e.g. JWTs) overlap with email-like substrings; running secrets first prevents the email regex from chewing into the middle of a JWT.
2. The `[REDACTED-SECRET]` placeholder is structurally different from `[REDACTED]`, so a downstream auditor can still tell which kind of span was rewritten.

The order is internal to the ingest pipeline; you don't have to think about it when using `--all-mask`.

## What lands in the JSONL

Both detectors share the same JSONL after the pass — secrets become `[REDACTED-SECRET]`, PII becomes `[REDACTED]`:

```text
Before: "Reach me at alice@example.com or use AKIAIOSFODNN7EXAMPLE."
After:  "Reach me at [REDACTED] or use [REDACTED-SECRET]."
```

## When NOT to use `--all-mask`

- **You want only one of the two.** Pass the explicit flag instead.
- **You want a different mask token.** The two detectors carry their own placeholders; if you need a different scheme, mask programmatically via `forgelm.data_audit.mask_pii` / `mask_secrets`.
- **You're auditing without modifying.** Use [`forgelm audit`](#/data/audit) instead — it scans the same patterns but reports counts without rewriting.

## Common pitfalls

:::warn
**`--all-mask` is not a compliance certification.** It's a defence-in-depth measure. For high-stakes corpora (legal, medical), pair it with manual review and the audit step.
:::

:::tip
For corpora that legitimately contain credentials (security training, CTF data) or PII (anonymisation research), don't reach for `--all-mask`. Document the exception in your dataset card and skip ingest masking entirely.
:::

## See also

- [PII Masking](#/data/pii-masking) — the underlying personal-data detector.
- [Secrets Scrubbing](#/data/secrets) — the underlying credentials detector.
- [Document Ingestion](#/data/ingestion) — where `--all-mask` is invoked.
- [Dataset Audit](#/data/audit) — the audit-only counterpart that detects without rewriting.
