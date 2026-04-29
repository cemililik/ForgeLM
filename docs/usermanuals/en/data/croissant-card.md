---
title: Croissant 1.0 Dataset Card
description: Optional Google Croissant 1.0 metadata emitted alongside the audit report — turns the same JSON file into both an EU AI Act Article 10 artifact and a Croissant-consumer dataset card.
---

# Croissant 1.0 Dataset Card — `--croissant`

The audit report (`data_audit_report.json`) already carries every signal an EU AI Act Article 10 reviewer needs: PII counts, secrets summary, near-duplicate pairs, cross-split leakage, language distribution. With `--croissant`, the same file picks up a top-level `croissant` block that conforms to the [Google Croissant 1.0](http://mlcommons.org/croissant/) specification. One file, two consumers.

## Why bother?

Croissant is the emerging standard for ML dataset cards (Hugging Face dataset pages, MLCommons reference loaders, the Croissant validator all consume it). Emitting a card alongside the audit means:

- The dataset can be published to HuggingFace / MLCommons with the metadata block already in place.
- A Croissant-aware loader can locate the underlying JSONL splits directly from the card.
- Compliance reviewers and data scientists read the same source of truth.

When `--croissant` is off, the `croissant` key in the audit report is an empty dict (`{}`). Existing audit consumers that ignore unknown keys see no behavioural change.

## Quick example

```shell
$ forgelm audit data/policies/ --output ./audit/ --croissant
✓ format: instructions (12,400 rows, 3 splits)
✓ croissant card emitted
   distribution: 3 file objects (train.jsonl, validation.jsonl, test.jsonl)
   record sets: 3
```

The card lands under the `croissant` key:

```json
{
  "croissant": {
    "@context": { "@vocab": "https://schema.org/", "sc": "https://schema.org/", "cr": "http://mlcommons.org/croissant/", ... },
    "@type": "sc:Dataset",
    "conformsTo": "http://mlcommons.org/croissant/1.0",
    "name": "policies",
    "description": "ForgeLM audit-generated dataset card. 12400 sample(s) across 3 split(s). ...",
    "url": "data/policies/",
    "datePublished": "2026-04-29T...",
    "distribution": [
      { "@type": "cr:FileObject", "@id": "train.jsonl",      "name": "train.jsonl",      "contentUrl": "train.jsonl",      "encodingFormat": "application/jsonlines", "description": "..." },
      { "@type": "cr:FileObject", "@id": "validation.jsonl", "name": "validation.jsonl", "contentUrl": "validation.jsonl", "encodingFormat": "application/jsonlines", "description": "..." },
      { "@type": "cr:FileObject", "@id": "test.jsonl",       "name": "test.jsonl",       "contentUrl": "test.jsonl",       "encodingFormat": "application/jsonlines", "description": "..." }
    ],
    "recordSet": [
      { "@type": "cr:RecordSet", "@id": "train",      "name": "train",      "field": [...] },
      { "@type": "cr:RecordSet", "@id": "validation", "name": "validation", "field": [...] },
      { "@type": "cr:RecordSet", "@id": "test",       "name": "test",       "field": [...] }
    ]
  }
}
```

## What the card carries

| Field | Source |
|---|---|
| `@context` | Canonical Croissant 1.0 context block (vocabulary). |
| `@type` | `sc:Dataset` — required for Croissant validators. |
| `conformsTo` | `http://mlcommons.org/croissant/1.0` — vocab declaration. |
| `name` | Derived from the source path (file stem or directory name). |
| `description` | Auto-generated summary of sample count + split count. |
| `url` | The as-typed input path (HF Hub ID, relative path, etc.) — not the resolved absolute filesystem path, so cards published to HuggingFace / MLCommons don't leak the auditor's local layout. |
| `datePublished` | ISO 8601 timestamp of the audit run. |
| `distribution` | One `cr:FileObject` per JSONL split. `contentUrl` is the relative file_id (same anti-leakage rationale as `url`). |
| `recordSet` | One `cr:RecordSet` per split with `cr:Field` entries derived from the audit's column-detection layer. |

## What's deliberately NOT emitted

The audit doesn't have first-class evidence for these Croissant fields, so they're omitted rather than guessed:

- `version` (`sc:version`) — the dataset version. Operators that publish hand-edit this at publish time the same way they hand-edit other publish-only fields.
- `license` — same; the audit can't infer the licence of an arbitrary corpus.
- `citeAs` — citation string; up to the publisher.
- `creator` / `keywords` — depend on publish context.

If you want these fields populated, edit the JSON post-audit before publishing. They don't change the audit's compliance role.

## Conformance

The emitted card is conformant against the canonical [Croissant 1.0 spec](http://mlcommons.org/croissant/1.0). It's been validated against:

- The [Croissant validator](https://github.com/mlcommons/croissant) (`mlcroissant validate`).
- HuggingFace's dataset card parser (the `datasets` library reads Croissant if present in the dataset directory).

Validation runs on minimum-viable subset; if your tooling expects optional fields not in this list, hand-edit before publish.

## When to use

- **Publishing the dataset.** The card lives in the same JSON file as the audit, so the publish step is a single artefact.
- **Cross-team handoff.** Data engineers and ML engineers can both consume one file.
- **Compliance bundles.** EU AI Act Article 10 governance bundles can include the Croissant card as the dataset-identity layer.

## When NOT to use

- **Internal-only audits** that never leave the team's bucket. The card is harmless but you don't need it.
- **Datasets with non-standard file layouts** (unsupervised clustering of unrelated `.jsonl` files in one directory). Croissant assumes the splits-per-file convention; for arbitrary layouts, hand-write the card.

## Programmatic API

The card is built by `forgelm.data_audit._build_croissant_metadata` (private helper) and is populated on `AuditReport.croissant` when `audit_dataset(emit_croissant=True)` is called:

```python
from forgelm.data_audit import audit_dataset

report = audit_dataset(
    "data/policies/",
    output_dir="./audit/",
    emit_croissant=True,
)
print(report.croissant["@type"])           # "sc:Dataset"
print(report.croissant["conformsTo"])      # "http://mlcommons.org/croissant/1.0"
print(len(report.croissant["distribution"]))  # 3 (one per JSONL split)
```

## Common pitfalls

:::warn
**Editing the card and then re-running the audit.** Re-running `forgelm audit` overwrites the file. Either edit *after* the final audit, or feed the edited card forward via your own publish-step script.
:::

:::tip
For Hugging Face publishing, save the card as `croissant.json` in the dataset repo (HF expects it there). A simple `jq '.croissant' data_audit_report.json > croissant.json` does the trick.
:::

## See also

- [Dataset Audit](#/data/audit) — where `--croissant` is invoked.
- [Annex IV](#/compliance/annex-iv) — the EU AI Act Article 11 artefact that the audit feeds into.
- [GDPR / KVKK](#/compliance/gdpr) — broader regulatory context.
