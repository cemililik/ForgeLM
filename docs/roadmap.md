# ForgeLM Roadmap

> **Configuration-driven, enterprise-grade LLM fine-tuning platform** — built on three principles: reliability before features, enterprise differentiation over feature parity, every capability config-driven and testable.

## Status at a glance

| Tür | Phase | Status |
|-----|-------|--------|
| ✅ Done | [Phase 1-9](roadmap/completed-phases.md) | SOTA upgrades, evaluation, reliability, enterprise integration, ecosystem, alignment stack, safety, EU AI Act compliance (Articles 9-17 + Annex IV), advanced safety intelligence |
| 📋 Planned | [Phase 10 — Post-Training Completion](roadmap/phase-10-post-training.md) | `forgelm/inference.py`, `chat`, `export` (GGUF), `fit-check`, `deploy` → `v0.4.0` |
| 📋 Planned | [Phase 10.5 — Quickstart Layer & Onboarding](roadmap/phase-12-quickstart.md) | `forgelm quickstart <template>`, 5 templates, sample datasets → `v0.4.5` |
| 📋 Planned | [Phase 11 — Document Ingestion & Data Audit](roadmap/phase-11-data-ingestion.md) | PDF/DOCX/EPUB → JSONL, PII detection, near-duplicate audit → `v0.5.0` |
| 📋 Planned | [Phase 12 — (reserved)](roadmap/phase-12-quickstart.md) | Merged into Phase 10.5 |
| 📋 Planned | [Phase 13 — Pro CLI & Observability Dashboard](roadmap/phase-13-pro-cli.md) | License-gated dashboard, HPO, scheduled jobs, team config store → `v0.6.0-pro` |
| 📋 Planned | [Phase 14 — Multi-Stage Pipeline Chains](roadmap/phase-14-pipeline-chains.md) | SFT → DPO → GRPO chained config, pipeline provenance artifacts → `v0.5.1` |

**Current milestone:** `v0.3.1rc1` — security hardening and config robustness (April 2026). Webhook URL credential leak, audit log chain gap, GRPO callable bug, TIES merging error — all fixed.

**Current state:** 11 phases (1, 2, 2.5, 3, 4, 5, 5.5, 6, 7, 8, 9) complete. 5 phases (10, 10.5, 11, 13, 14) planned. Target `v0.4.0` release: Phase 10. Target `v0.4.5`: Phase 10.5 (Quickstart). Target `v0.5.0`: Phase 11.

## Quick summary of what's planned

```mermaid
graph LR
    P10[Phase 10<br/>Post-Training<br/>Completion] --> P105[Phase 10.5<br/>Quickstart<br/>Layer]
    P10 --> P11[Phase 11<br/>Data<br/>Ingestion]
    P105 --> P11
    P11 --> P13[Phase 13<br/>Pro CLI<br/>+ Dashboard]
    P11 --> P14[Phase 14<br/>Pipeline<br/>Chains]

    P10 -.-> V1[v0.4.0]
    P105 -.-> V15[v0.4.5]
    P11 -.-> V2[v0.5.0]
    P14 -.-> V25[v0.5.1]
    P13 -.-> V3[v0.6.0-pro]

    style P10 fill:#002244,stroke:#00aaff
    style P105 fill:#003300,stroke:#00ff88
    style P11 fill:#002244,stroke:#00aaff
    style P13 fill:#442200,stroke:#ffaa00
    style P14 fill:#002244,stroke:#00aaff
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
    ├── completed-phases.md                     # Phase 1-9 archive (detailed)
    ├── phase-10-post-training.md               # Active planning
    ├── phase-11-data-ingestion.md              # Active planning
    ├── phase-12-quickstart.md                  # Active planning (now Phase 10.5)
    ├── phase-13-pro-cli.md                     # Active planning (gated)
    ├── phase-14-pipeline-chains.md             # Active planning
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
