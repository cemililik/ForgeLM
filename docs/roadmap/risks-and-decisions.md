# Riskler, Fırsatlar, Rekabet ve Kararlar

> **Not:** Bu dosya yönetişim ve stratejik karar kayıtlarını içerir. Her quarterly gate'te yeniden değerlendirilir.

## Risk Matrix

### High Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Dependency Breaking Changes** (TRL, PEFT, Unsloth) | Training pipeline breaks without warning | High | Version pinning with upper bounds, CI nightly builds against latest deps, compatibility matrix |
| **EU AI Act Non-Compliance** (August 2026 deadline) | Enterprise customers cannot adopt ForgeLM for high-risk AI | High | Phase 8 deep compliance: Annex IV docs, audit log, risk assessment, human gate, data governance |
| **Safety Degradation from Fine-Tuning** | Fine-tuned models lose alignment, enterprise liability | High | Phase 6 safety evaluation pipeline, auto-revert on safety regression |
| **Alignment Method Lock-In** | ForgeLM supports only ORPO while market demands DPO/GRPO | High | Phase 5 is top priority — critical market expectation |
| **Compliance window closing** (Aug 2, 2026) | Enterprise leads not converted before competitors add compliance features | High | Enterprise outreach Day 1; Turkey market as first pilot; deep compliance features (Audit API, managed cloud) as moat |
| **Community flywheel not started** | 0 stars → 0 enterprise credibility → missed EU AI Act window | High | Phase 10.5 Quickstart prioritized; YouTube Academy; Show HN + Reddit launch |

### Medium Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **MoE/VLM Architecture Shift** | ForgeLM cannot train dominant model architectures | Medium | Phase 7 addresses this; monitor PEFT library MoE support |
| **Scope Creep** (too many trainers, model types) | Maintenance burden exceeds capacity, core quality degrades | Medium | Strict phase gating, leverage TRL's existing trainers |
| **Ecosystem Commoditization** (Axolotl, LLaMA-Factory) | Competing tools add similar enterprise features | Medium | Double down on safety + compliance differentiation |
| **GPU/CUDA Version Fragmentation** | Users on different CUDA versions hit incompatibilities | Medium | Docker images pin CUDA versions, compatibility matrix |

### Low Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Model merging adoption uncertainty** | Feature built but rarely used | Low | Implement as separate CLI command, minimal core changes |
| **Notebook template maintenance** | Notebooks break with library updates | Low | Auto-generate from config templates, CI validation |

---

---

## Opportunity Analysis

### Immediate Opportunities
1. **Alignment Stack (Phase 5)** — DPO+GRPO support closes the most critical competitive gap. Every serious fine-tuning workflow in 2026 uses preference optimization.
2. **Safety-as-a-Feature (Phase 6)** — No competitor integrates safety evaluation into the training pipeline. ForgeLM can own "the safest way to fine-tune an LLM."

### Medium-Term Opportunities
3. **EU AI Act Compliance** — August 2026 deadline creates urgent demand. ForgeLM as the only tool generating compliance artifacts is a powerful enterprise sales argument.
4. **MoE Fine-Tuning** — Qwen3, DeepSeek-V3 dominance means MoE support is becoming table stakes.
5. **Cost Transparency** — GPU cost tracking per run enables enterprise budget planning and optimization. Simple to implement, high perceived value.

### Long-Term Opportunities
6. **Managed ForgeLM Service** — SaaS offering: upload data + config → receive trained model + compliance artifacts.
7. **Synthetic Data Pipeline** — Config-driven teacher model distillation before training. Unique integration no competitor offers.
8. **Training Marketplace** — Community-contributed config templates for common use cases.

---

---

## Competitive Positioning (Updated March 2026)

| Competitor | Stars | ForgeLM Advantage | ForgeLM Gap |
|------------|-------|-------------------|-------------|
| **LLaMA-Factory** | ~55-68K | CI/CD-native, safety eval, compliance | Web UI, 100+ models, GaLore/PiSSA, VLM |
| **Unsloth** | ~54-56K | Enterprise features, multi-trainer, safety | Speed (2-5x), Studio GUI, MoE optimization |
| **TRL** | ~17.6K | Full pipeline (not just trainers), Docker, evaluation | GRPO, official HF integration |
| **Axolotl** | ~11.4K | Simpler config, Docker, safety eval | GRPO, GDPO, sequence parallelism, MoE quant |
| **torchtune** | Meta-backed | Config-driven enterprise focus | Knowledge distillation, QAT, PyTorch-native |

**ForgeLM's evolving niche:** Config-driven, CI/CD-native, **safety-conscious**, enterprise LLM fine-tuning. The safety + compliance angle is the strongest differentiator available — no competitor addresses it.

---

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-23 | Inserted Phase 2.5 (Reliability) before new features | Product analysis revealed critical silent failure and test coverage gaps |
| 2026-03-23 | Deprioritized direct cloud API integration (original Phase 3) | Unsustainable maintenance burden, 3rd-party dependency risk, scope creep |
| 2026-03-23 | Adopted Docker-based deployment strategy | Portable, user-controlled infrastructure, minimal maintenance for ForgeLM team |
| 2026-03-23 | Moved wizard mode from Phase 2 to Phase 3 | Reliability work takes priority over UX improvements |
| 2026-03-23 | Added `trust_remote_code` as enterprise adoption blocker | Security risk incompatible with regulated industries |
| 2026-03-23 | Phase 5 (Alignment Stack) prioritized as Critical | Competitive analysis: DPO/GRPO support is market expectation, ORPO alone insufficient |
| 2026-03-23 | Phase 6 (Safety & Compliance) chosen as primary differentiator | No competitor integrates safety evaluation or EU AI Act compliance. August 2026 deadline creates urgency |
| 2026-03-23 | Phase 7 (MoE/VLM/Merging) scoped as ongoing | Model landscape shifting to MoE and multimodal; must support but not at expense of Phase 5-6 |
| 2026-03-23 | Leverage TRL trainers for alignment methods | TRL already implements DPO, KTO, GRPO — ForgeLM wraps with config, evaluation, and pipeline integration rather than reimplementing |
| 2026-03-24 | Phase 8 (EU AI Act Deep Compliance) added with 10 tasks | Gap analysis against Articles 9-17 + Annex IV revealed 6 major gaps. Tier 1 (5 tasks) must complete before August 2, 2026 enforcement. This is ForgeLM's strongest differentiator — no competitor addresses EU AI Act systematically |
| 2026-03-24 | Phase 9 (Advanced Safety Scoring) added with 8 tasks | Community feedback: binary safe/unsafe classification insufficient for production. Confidence scores, harm categories, severity levels, and trend tracking needed. Strengthens core differentiator |
| 2026-04-25 | Phase ordering revised: Quickstart (formerly Phase 12) moved to Phase 10.5, before Data Ingestion | Community flywheel: Quickstart drives stars → enterprise leads → EU AI Act compliance sales. Delay = missed EU AI Act window. |
| 2026-04-25 | Phase 14 (Multi-Stage Pipeline) added to roadmap | Enterprises need SFT → DPO → GRPO chained training as first-class feature; currently requires manual config juggling |
| 2026-04-25 | Enterprise outreach moved to Day 1 (previously Week 7-12) | EU AI Act enforcement in 99 days; enterprise sales cycle is 3-6 months; starting at Week 7 means missing the window |
| 2026-04-25 | v0.3.1rc1 security + config hardening release | Comprehensive code review revealed webhook URL leakage, audit log chain gap, GRPO callable bug, TIES merging error — all fixed |
| 2026-04-25 | Turkey/BDDK/KVKK market added as priority enterprise target | First-mover in Turkish compliance market; BDDK AI guidelines publishing in 2026; no competitors; path to first enterprise case study |
