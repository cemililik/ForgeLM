# Phase 13: Pro CLI & Observability Dashboard

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md).

**Goal:** First paid-tier feature set. Observability and experimentation workflows that open-source users can live without, but teams running ≥5 concurrent experiments cannot. Revenue bridge between consulting (Phase B) and Cloud SaaS (future).
**Estimated Effort:** High (3-4 months)
**Priority:** Medium — gated by Phase 10-12 adoption signal. Do not start until `v0.5.0` has ≥1K monthly PyPI installs and ≥2 paying support contracts.

> **Context:** Revenue model documented in the [monetization plan](../marketing/06_revenue_model.md): Pro CLI is the first tier above OSS. Core rule — everything users can reasonably do via shell scripts + public dashboards stays free; what requires ForgeLM-specific infrastructure (experiment graph, HPO orchestration, team config store) is Pro. No feature gating that degrades the free experience.

### Tasks:

1. [ ] **`forgelm pro` CLI subcommand group**
   Activation via license key (`FORGELM_PRO_KEY` env var or `~/.forgelm/pro.key`). License server minimal: validates key + reports usage quota. Uses `cryptography` library for offline license verification where possible.

2. [ ] **Web dashboard — experiment browser**
   Local-first web UI (FastAPI + HTMX + Tailwind; no SPA bloat). Reads from `checkpoints/` + `audit_log.jsonl`. Visualizes: run list, config diffs across runs, metric comparisons (loss, eval, safety, cost), artifact browser. Launchable via `forgelm pro dashboard --port 8080`. Optional Docker deployment for team use.

3. [ ] **Hyperparameter optimization (HPO) — Optuna integration**
   New config section: `hpo: {n_trials, search_space: {...}, metric: eval_loss, direction: minimize}`. Spawns N subordinate training runs, aggregates, produces best-config YAML + comparison report. Integrates with existing auto-revert thresholds.

4. [ ] **Scheduled training jobs**
   Cron-style config: `schedule: "0 2 * * 0"` (weekly Sunday 2 AM). Wrapper daemon (`forgelm pro schedule run`) watches config, triggers runs, captures output. Pairs naturally with data refresh pipelines ("every Sunday, retrain on latest dataset").

5. [ ] **Cloud GPU cost estimation — real-time pricing**
   Extends Phase 6 GPU cost estimation with live spot pricing from RunPod, Lambda Labs, vast.ai APIs. Before training starts, estimates cost across providers; after training, computes actual cost and logs drift. Optional — free tier stays with static pricing database.

6. [ ] **Team configuration store**
   `forgelm pro team push/pull <config-name>` — shared config repository backed by user's Git repo (simple) or ForgeLM-hosted store (later). Permissions + team member management. Enables "our team's golden LoRA config" patterns.

### Requirements:
- Every Pro feature must have a 90%-equivalent OSS workaround documented. No "you must pay to use ForgeLM properly" messaging — Pro is for convenience and scale, not gatekeeping.
- Dashboard runs locally by default; cloud-hosted is a separate track.
- License validation must work offline after first activation (air-gapped compliance preserved).
- Pricing decisions documented in [marketing/06_revenue_model.md](../marketing/06_revenue_model.md), not here.

### Delivery:
- Target release: `v0.6.0-pro` (separately distributed; OSS core remains at `v0.5.x`)
- Gated: do not ship before traction validation.

---
