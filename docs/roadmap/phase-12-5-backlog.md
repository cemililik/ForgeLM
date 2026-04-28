# Phase 12.5 — Data Curation Polish Backlog

> **Follow-up to Phase 12.** Phase 12 (`v0.5.2`) shipped the five Tier 1
> must-haves: MinHash LSH dedup option, markdown-aware splitter,
> code/secrets leakage tagger, heuristic quality filter, DOCX/Markdown
> table preservation. Three Tier 2/3 items were tagged "if scope allows"
> in the [original Phase 12 plan](phase-12-data-curation-maturity.md);
> they didn't make the same release because the Tier 1 surface was
> already a complete coherent ship and adding more would have grown the
> review window without proportional value. This file pins them as the
> follow-up backlog so a future minor release can pick them up without
> reopening the Phase 12 plan.
>
> **Scope:** small additions only — none require new architecture.
> Each row is one PR.

| # | Item | Source | Effort | Impact |
|---|---|---|---|---|
| **1** | **Presidio adapter** (`[ingestion-pii-ml]` extra, optional) | Phase 12 plan Tier 2 #6 | S–M | ML-NER signal regex misses (person names, organisations, locations); maps into the existing `pii_severity` table with new tier rows. Default regex+Luhn+TC-Kimlik path stays. |
| **2** | **Croissant metadata compatibility** (audit JSON) | Phase 12 plan Tier 2 #7 | S | Adds a Google Croissant-shaped subset to `data_audit_report.json` so the file doubles as both an EU AI Act Article 10 governance artifact and a Croissant-consumer dataset card. Opt-in `--croissant` flag; existing audit consumers unaffected. |
| **3** | **`forgelm ingest --all-mask` composite flag** | Phase 12 plan Tier 3 #8 | XS | One-flag shorthand that runs `--secrets-mask` then `--pii-mask` in the documented order. Pure UX; no new behaviour. Test: combined-fixture roundtrip. |
| **4** | **Wizard "audit first" entry point** | Phase 12 plan Tier 3 #9 | S | Mirrors Phase 11.5's `_offer_ingest_for_directory` pattern: when the user provides a JSONL, the wizard offers to run `forgelm audit` and prints the verdicts before continuing. Closes the audit loop in the BYOD path. |

## Why these landed here, not in Phase 12

- **Tier 2 (#1, #2)** add new optional dependencies (`presidio-analyzer`, plus a small Croissant schema mapping). Adding two new extras at once expands the install / extras-skip test matrix; carving them into their own PR keeps each behaviour individually reviewable. Neither closes a competitive gap that mattered for the `v0.5.2` ship — Phase 12's regex+Luhn+TC-Kimlik PII detector and the EU AI Act governance bundle covered the immediate compliance surface.
- **Tier 3 (#3, #4)** are pure UX polish. They don't unlock anything the operator cannot do today by typing two flags or running `forgelm audit` themselves; they smooth the path. Worth doing, not worth gating Phase 12 on.

## Picking up an item

1. Open an issue referencing the row number above.
2. PR scope: ONE row per PR.
3. Update this file when the row lands — strike through and link the
   commit / PR.
4. If a row turns out to be the wrong shape, edit it here before doing
   the work. Stale backlog rows are worse than missing rows.

## Out of scope (still)

The "Won't-do" list at the bottom of [`phase-12-data-curation-maturity.md`](phase-12-data-curation-maturity.md) is not weakened by this backlog. VLM PDF parsing, embedding-based semantic dedup, built-in OCR, ML quality classifiers, GPU/Ray scale, and HTML extractor stay out of scope as deliberately as Phase 12 declared them.
