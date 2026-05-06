# ForgeLM Roadmap

> **Configuration-driven, enterprise-grade LLM fine-tuning platform** — built on three principles: reliability before features, enterprise differentiation over feature parity, every capability config-driven and testable.

## Status at a glance

| Type | Phase | Status |
|-----|-------|--------|
| ✅ Done | [Phase 1-9](roadmap/completed-phases.md) | SOTA upgrades, evaluation, reliability, enterprise integration, ecosystem, alignment stack, safety, EU AI Act compliance (Articles 9-17 + Annex IV), advanced safety intelligence |
| ✅ Done | [Phase 10 — Post-Training Completion](roadmap/phase-10-post-training.md) | `inference.py`, `chat`, `export` (GGUF), `--fit-check`, `deploy` — shipped `v0.4.0` |
| ✅ Done | [Phase 10.5 — Quickstart Layer & Onboarding](roadmap/phase-10-5-quickstart.md) | `forgelm quickstart <template>`, 5 bundled templates with seed datasets — shipped `v0.4.5` |
| ✅ Done | [Phase 11 + 11.5 + 12 + 12.5 — Document Ingestion & Data Curation Pipeline](roadmap/releases.md#v050-document-ingestion-data-curation-pipeline) | `forgelm ingest`, `forgelm audit`, PII regex + simhash dedup, LSH banding, streaming reader, PII severity tiers, wizard ingest+audit, MinHash LSH dedup, markdown splitter, code/secrets scan, quality heuristics, DOCX table preservation, `--all-mask`, Croissant 1.0, Presidio NER — shipped `v0.5.0` (PyPI 2026-04-30) |
| 📋 Planned | [Phase 14 — Multi-Stage Pipeline Chains](roadmap/phase-14-pipeline-chains.md) | SFT → DPO → GRPO chained config, pipeline provenance artifacts → `v0.5.1` |
| 📋 Planned | [Phase 13 — Pro CLI & Observability Dashboard](roadmap/phase-13-pro-cli.md) | License-gated dashboard, HPO, scheduled jobs, team config store → `v0.6.0-pro` |

> **Status legend:** ✅ Released (PyPI) · 🟡 Merged on main, publish pending · ⏳ Planned

**Released:** `v0.5.0` — "Document Ingestion + Data Curation Pipeline" — PyPI 2026-04-30 (Phases 11 + 11.5 + 12 + 12.5 consolidated).

- **Phase 11** — `forgelm ingest` (PDF / DOCX / EPUB / TXT / Markdown → SFT-ready JSONL) + `forgelm audit` (length / language / near-duplicate / cross-split leakage / PII regex with Luhn + TC Kimlik validators) + EU AI Act Article 10 governance integration.
- **Phase 11.5** — operational polish: LSH-banded near-duplicate detection, streaming JSONL reader, token-aware `--chunk-tokens`, PDF page-level header/footer dedup, `forgelm audit` subcommand, PII severity tiers, atomic audit writes, wizard "ingest first" entry point.
- **Phase 12** — data curation maturity: MinHash LSH dedup option (`--dedup-method minhash`, `[ingestion-scale]` extra), markdown-aware splitter (`--strategy markdown`), code/secrets leakage tagger (`--secrets-mask`, `secrets_summary` always-on), heuristic quality filter (`--quality-filter`), DOCX/Markdown table preservation.
- **Phase 12.5** — small additive polish: `--all-mask` shorthand for combined PII + secrets scrubbing, `forgelm audit --croissant` emits a Google Croissant 1.0 dataset card, optional Presidio ML-NER PII adapter (`--pii-ml`, `[ingestion-pii-ml]` extra), wizard "audit first" entry point.

Originally planned as four sequential PyPI tags (`v0.5.0` / `v0.5.1` / `v0.5.2` / `v0.5.3`), consolidated into one comprehensive `v0.5.0` release because the four phases form one coherent surface (ingest → polish → mature → polish) hard to use in parts.

**Latest release on PyPI:** `v0.5.0` — Document Ingestion + Data Curation Pipeline (2026-04-30). `forgelm ingest`, `forgelm audit`, MinHash LSH dedup, Presidio ML-NER, Croissant 1.0 dataset cards, EU AI Act Article 10 governance integration.

**Earlier:** `v0.4.5` — Quickstart Layer (2026-04-26); `v0.4.0` — Post-Training Completion (2026-04-26).

**Next:** `v0.5.1` — Multi-Stage Pipeline Chains (Phase 14). SFT → DPO → GRPO chained config, pipeline provenance artifacts. Folds in [#14 webhook SSRF hardening](https://github.com/cemililik/ForgeLM/issues/14).

**Current state:** 17 phases (1, 2, 2.5, 3, 4, 5, 5.5, 6, 7, 8, 9, 10, 10.5, 11, 11.5, 12, 12.5) complete. 2 phases (13, 14) planned. `v0.5.1`: Phase 14. `v0.6.0-pro` (Phase 13) gated on adoption metrics.

## Quick summary of what's planned

```mermaid
graph LR
    P10[Phase 10<br/>Post-Training<br/>Completion] --> P105[Phase 10.5<br/>Quickstart<br/>Layer]
    P10 --> P11[Phase 11<br/>Data<br/>Ingestion]
    P105 --> P11
    P11 --> P115[Phase 11.5<br/>Ingestion<br/>Polish]
    P115 --> P12[Phase 12<br/>Data Curation<br/>Maturity]
    P12 --> P125[Phase 12.5<br/>Data Curation<br/>Follow-up]
    P12 --> P14[Phase 14<br/>Pipeline<br/>Chains]
    P14 --> P13[Phase 13<br/>Pro CLI<br/>+ Dashboard]

    P10 -.-> V1[v0.4.0]
    P105 -.-> V15[v0.4.5]
    P11 -.-> V2[v0.5.0 ✅ Released]
    P115 -.-> V2
    P12 -.-> V2
    P125 -.-> V2
    P14 -.-> V23[v0.5.1]
    P13 -.-> V3[v0.6.0-pro]

    style P10 fill:#003300,stroke:#00ff88
    style P105 fill:#003300,stroke:#00ff88
    style P11 fill:#004400,stroke:#88ff88
    style P115 fill:#004400,stroke:#88ff88
    style P12 fill:#004400,stroke:#88ff88
    style P125 fill:#004400,stroke:#88ff88
    style P14 fill:#002244,stroke:#00aaff
    style P13 fill:#442200,stroke:#ffaa00
```

## Guiding principles

1. **Reliability before features.** Every new capability ships with tests, docs, and CI coverage.
2. **Enterprise differentiation over feature parity.** ForgeLM's edge is safety + compliance, not feature count. Don't compete on features already owned by Unsloth (speed), LLaMA-Factory (GUI), or Axolotl (sequence parallelism).
3. **Config-driven, testable, optional.** Every new capability is a YAML flag. No global state, no magic, no mandatory integrations.
4. **Kill criteria over hype criteria.** Every phase has a measurable quarterly gate. Missed gates = rethink, not push harder.

## Documentation map

```
docs/
├── roadmap.md                                  # This file — short index
├── roadmap-tr.md                               # Turkish mirror
└── roadmap/
    ├── completed-phases.md                     # Phase 1-10 archive (detailed)
    ├── phase-10-post-training.md               # Completed — v0.4.0
    ├── phase-10-5-quickstart.md                # Done (Phase 10.5) — shipped as v0.4.5
    ├── phase-11-data-ingestion.md              # Done (Phase 11) — consolidated into v0.5.0
    ├── phase-11-5-backlog.md                   # Done (Phase 11.5) — consolidated into v0.5.0; ingestion/audit polish
    ├── phase-12-data-curation-maturity.md      # Done (Phase 12 Tier 1) — consolidated into v0.5.0; MinHash LSH, markdown splitter, secrets scan
    ├── phase-12-5-backlog.md                   # Done (Phase 12.5) — consolidated into v0.5.0; Presidio adapter, Croissant metadata, --all-mask, wizard audit-first
    ├── phase-13-pro-cli.md                     # Planned — v0.6.0-pro (gated)
    ├── phase-14-pipeline-chains.md             # Planned — v0.5.1 (follow-up to the v0.5.0 consolidation)
    ├── releases.md                             # v0.3.0 → v0.6.0 release notes
    └── risks-and-decisions.md                  # Risk matrix, opportunities, competitive positioning, decision log
```

## How this roadmap is maintained

- **Weekly** — Progress check against active phase's tasks.
- **Monthly** — Decision log update if scope changes (`roadmap/risks-and-decisions.md`).
- **Quarterly** — Full review: close completed phases, re-prioritize planned phases, update competitive analysis. Each phase gate has explicit kill criteria: if the gate is missed, the phase is rethought — not just delayed.
- **Annually** — Archive completed phases to `completed-phases.md`, retire outdated planning files.

## Related documents

- [Product Strategy](product_strategy.md) — Market position, target users, strategic decisions
- [Architecture](reference/architecture.md) — System design reference
- [Configuration Guide](reference/configuration.md) — YAML reference for all phases
- [Usage Guide](reference/usage.md) — How to run ForgeLM
- **Internal only:** Marketing + strategy planning in `docs/marketing/` (gitignored)

---

**For individual phase details:** Follow the links in the status table above.
**For the big picture:** Start with [Product Strategy](product_strategy.md) → pick a phase → read its dedicated file.
