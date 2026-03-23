# ForgeLM Enterprise Roadmap (2026+)

Based on the strategic vision outlined in the [2026 Upgrade Proposal](2026_upgrade_proposal.md), the comprehensive product analysis (March 2026), and competitive landscape research against Axolotl, LLaMA-Factory, Unsloth, TRL, and torchtune, this roadmap details the execution phases for ForgeLM's evolution into the standard **config-driven, enterprise-grade LLM fine-tuning platform**.

> **Guiding Principles:**
> 1. Reliability before features.
> 2. Enterprise differentiation over feature parity.
> 3. Every new capability must be config-driven, testable, and optional.

---

## Current Status Summary

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: SOTA Upgrades | **Complete** | 6/6 |
| Phase 2: Evaluation & Validation | **Complete** | 5/5 |
| Phase 2.5: Reliability & Maturity | **Complete** | 8/8 |
| Phase 3: Enterprise Integration | **Complete** | 6/6 |
| Phase 4: Ecosystem Growth | **Complete** | 5/5 |
| Phase 5: Alignment & Post-Training Stack | **Complete** | 5/5 |
| Phase 6: Enterprise Trust & Compliance | **Complete** | 5/5 |
| Phase 7: Next-Gen Model Support | **Complete** | 5/5 |

---

## Phase 1–4: Complete ✅

<details>
<summary>Click to expand completed phases</summary>

### Phase 1: Foundational SOTA Upgrades ✅ (6/6)
4-Bit QLoRA & DoRA, TRL SFTTrainer, Chat Templates, Unsloth Backend, Blackwell Optimization, Pre-flight Validation.

### Phase 2: Autonomous Evaluation & Validation ✅ (5/5)
Automated Benchmarking (lm-eval-harness), Model Reversion, Webhook Integration, Wizard Mode, Runtime Smoke Tests.

### Phase 2.5: Reliability & Production Readiness ✅ (8/8)
Structured Logging, Silent Failure Elimination, Test Coverage, Dependency Pinning, Security Hardening, CLI Maturity, Error Diagnostics, CI/CD Hardening.

### Phase 3: Enterprise Integration ✅ (6/6)
Wizard Mode, Benchmarking, Docker/Compose, JSON Output, Offline/Air-Gapped Mode, Checkpoint Resume.

### Phase 4: Ecosystem Growth ✅ (5/5)
ORPO Trainer, W&B/MLflow/TensorBoard, Multi-Dataset Training, Model Card Generation, DeepSpeed/FSDP.

</details>

---

## Phase 5: Alignment & Post-Training Stack
**Goal:** Provide the complete modern post-training pipeline: SFT → Preference Optimization → RL for Reasoning. This is the single most critical gap vs competitors — every major tool (Axolotl, TRL, Unsloth, LLaMA-Factory) supports DPO and GRPO.
**Estimated Effort:** High (2-3 months)
**Priority:** Critical — market expectation

> **Context:** The 2026 post-training landscape has settled on a modular stack: SFT first, then preference alignment (DPO/SimPO/KTO), optionally followed by reasoning RL (GRPO/DAPO). ORPO alone is insufficient — enterprises need the full menu. Research (arxiv 2603.19335) shows algorithm rankings are scale-dependent, so users must be able to choose.

### Tasks:
1. [x] **DPO Trainer:** Direct Preference Optimization — the baseline preference method. TRL's `DPOTrainer` integration with ForgeLM config. `trainer_type: "dpo"` in YAML. Requires `chosen`/`rejected` dataset format.
2. [x] **SimPO Trainer:** Simple Preference Optimization — no reference model needed, lower memory than DPO. +6.4 points on AlpacaEval 2 vs DPO at 7B scale. `trainer_type: "simpo"`.
3. [x] **KTO Trainer:** Kahneman-Tversky Optimization — uses binary thumbs-up/down feedback instead of paired preferences. More practical for production data collection. `trainer_type: "kto"`.
4. [x] **GRPO Trainer:** Group Relative Policy Optimization — the method behind DeepSeek-R1. Online RL that generates and scores responses during training. Critical for reasoning/math/code fine-tuning. `trainer_type: "grpo"`. Requires reward model or verifiable reward function.
5. [x] **Alignment Strategy Auto-Selection:** Based on dataset format (paired preferences vs binary feedback vs verifiable rewards), automatically recommend or select the appropriate trainer. Surfaced in `--wizard` and `--dry-run`.

### Config Example:
```yaml
training:
  trainer_type: "dpo"  # "sft", "orpo", "dpo", "simpo", "kto", "grpo"
  dpo_beta: 0.1        # DPO temperature
  simpo_gamma: 0.5     # SimPO margin term
  grpo_num_generations: 4  # GRPO responses per prompt
```

### Requirements:
- TRL already provides DPOTrainer, KTOTrainer, and GRPO — integration is config-to-trainer mapping
- Each trainer must support all existing features: auto-revert, benchmarks, webhooks, JSON output
- Data module must auto-detect dataset format: `chosen`/`rejected` (DPO/SimPO), `completion`/`label` (KTO), `prompt`-only (GRPO)

---

## Phase 6: Enterprise Trust & Compliance
**Goal:** Make ForgeLM the safest, most auditable fine-tuning tool — a unique differentiator that no competitor offers. Target: EU AI Act compliance (full enforcement August 2026) and regulated industry adoption.
**Estimated Effort:** High (2-3 months)
**Priority:** High — differentiator, no competitor does this well

> **Context:** Fine-tuning aligned models demonstrably compromises safety, even with benign data (confirmed by multiple papers, Microsoft Feb 2026). The EU AI Act requires machine-readable audit trails, risk classification, and continuous monitoring for high-risk AI systems. No fine-tuning tool addresses this in the training loop today. ForgeLM can own this space.

### Tasks:
1. [x] **Post-Training Safety Evaluation:** Run safety classifiers (Llama Guard, ShieldGemma, or configurable) on model outputs after training. Compare safety scores before vs after fine-tuning. Auto-revert if safety degrades beyond threshold. Integrated into the existing evaluation pipeline.
   ```yaml
   evaluation:
     safety:
       enabled: true
       classifier: "meta-llama/Llama-Guard-3-8B"  # or local path
       test_prompts: "safety_prompts.jsonl"  # adversarial test set
       max_safety_regression: 0.05  # max allowed safety score drop
   ```
2. [x] **LLM-as-Judge Evaluation Pipeline:** Use a strong LLM (GPT-4, Claude, local judge model) to score fine-tuned model outputs on quality, helpfulness, and instruction-following. 500x-5000x cheaper than human evaluation. Configurable judge model and scoring rubric.
   ```yaml
   evaluation:
     llm_judge:
       enabled: true
       judge_model: "gpt-4o"  # or local model path
       judge_api_key_env: "OPENAI_API_KEY"
       eval_dataset: "eval_prompts.jsonl"
       min_score: 7.0  # out of 10
   ```
3. [x] **GPU Cost & Resource Tracking:** Track per-run metrics: GPU-hours, peak VRAM usage, total training time, estimated cloud cost (based on GPU type). Include in JSON output, webhook notifications, and model card.
   ```json
   {
     "resource_usage": {
       "gpu_hours": 2.4,
       "peak_vram_gb": 22.1,
       "training_duration_seconds": 8640,
       "gpu_model": "NVIDIA A100 80GB",
       "estimated_cost_usd": 7.20
     }
   }
   ```
4. [x] **EU AI Act Compliance Export:** Generate machine-readable compliance artifacts alongside the model card. Includes: training data provenance (dataset source, size, date), model lineage (base model, adapter method, hyperparameters), evaluation results (benchmarks, safety scores, LLM-judge), risk classification metadata, and timestamp-signed audit trail.
   ```bash
   forgelm --config job.yaml --compliance-export ./audit/
   # Outputs: audit/compliance_report.json, audit/training_manifest.yaml, audit/model_card.md
   ```
5. [x] **Training Data Provenance Tracking:** Record dataset fingerprints (hash, size, schema, source URL), preprocessing steps applied, and sample counts per split. Stored in model card and compliance export. Critical for reproducibility audits.

### Requirements:
- Safety evaluation requires a separate model load (judge/classifier) — must handle GPU memory carefully
- LLM-as-judge must support both API-based (OpenAI, Anthropic) and local judge models
- Cost estimation needs GPU pricing database (configurable, with defaults for common GPUs)
- All compliance data must be exportable without GPU (post-hoc from saved artifacts)

---

## Phase 7: Next-Gen Model Support
**Goal:** Support the model architectures and training paradigms that define mid-2026 and beyond: MoE, multimodal, long-context, and model merging.
**Estimated Effort:** Very High (3-6 months, ongoing)
**Priority:** High — market alignment

> **Context:** The model landscape has shifted. Qwen3, Mixtral, and DeepSeek-V3 are all MoE architectures. Vision-language models (Qwen2.5-VL, Llama-3.2-Vision) are mainstream. Context windows exceed 128K tokens. Model merging (TIES, DARE) is a standard post-training workflow. ForgeLM must support these to remain relevant.

### Tasks:
1. [x] **MoE (Mixture of Experts) Fine-Tuning:** Support LoRA/QLoRA fine-tuning of MoE models (Qwen3-30B-A3B, Mixtral, DeepSeek). Expert-aware quantization for VRAM reduction. Auto-detect MoE architecture and apply appropriate configuration.
   ```yaml
   model:
     name_or_path: "Qwen/Qwen3-30B-A3B"
     moe:
       quantize_experts: true  # quantize inactive experts for VRAM savings
       experts_to_train: "all"  # "all", "top_k", or list of expert indices
   ```
2. [x] **Multimodal VLM Fine-Tuning:** Support vision-language model fine-tuning (Qwen2.5-VL, Llama-3.2-Vision, GLM-4V). Image+text dataset format with automatic processor handling. New `data.format: "multimodal"` config option.
   ```yaml
   model:
     name_or_path: "Qwen/Qwen2.5-VL-7B-Instruct"
   data:
     dataset_name_or_path: "my_vlm_dataset"
     format: "multimodal"  # expects image_url/image_path + text columns
   ```
3. [x] **Model Merging Integration:** Post-training model merging via mergekit integration. Merge multiple LoRA adapters or fine-tuned models using TIES-Merging, DARE, SLERP, or linear interpolation. Config-driven, testable.
   ```yaml
   merge:
     enabled: true
     method: "ties"  # "ties", "dare", "slerp", "linear"
     models:
       - path: "./checkpoints/run1/final_model"
         weight: 0.7
       - path: "./checkpoints/run2/final_model"
         weight: 0.3
     output_dir: "./merged_model"
   ```
4. [x] **Advanced PEFT Methods:** Support newer parameter-efficient methods beyond LoRA/DoRA:
   - **PiSSA:** Principal component initialization — faster convergence, less quantization error than QLoRA
   - **rsLoRA:** Recommended for high ranks (r>64)
   - **GaLore:** Gradient low-rank projection — memory-efficient full-parameter-like training
   ```yaml
   lora:
     method: "pissa"  # "lora", "dora", "pissa", "galore"
   ```
5. [x] **Notebook & Colab Templates:** Pre-built Jupyter notebooks for common use cases: customer support bot, code assistant, domain-specific Q&A, multilingual fine-tuning. One-click Colab launch. Critical for community growth and onboarding.

### Requirements:
- MoE support depends on PEFT library's MoE handling — verify compatibility
- Multimodal requires processor/image handling — significant data pipeline changes
- Model merging can be a separate CLI command: `forgelm merge --config merge.yaml`
- Notebook templates should auto-generate from config templates where possible
- Each feature must be optional (`pip install forgelm[multimodal]`, `forgelm[merging]`)

---

## Risk Matrix

### High Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Dependency Breaking Changes** (TRL, PEFT, Unsloth) | Training pipeline breaks without warning | High | Version pinning with upper bounds, CI nightly builds against latest deps, compatibility matrix |
| **EU AI Act Non-Compliance** (August 2026 deadline) | Enterprise customers cannot adopt ForgeLM for high-risk AI | Medium | Phase 6 compliance export prioritized before deadline |
| **Safety Degradation from Fine-Tuning** | Fine-tuned models lose alignment, enterprise liability | High | Phase 6 safety evaluation pipeline, auto-revert on safety regression |
| **Alignment Method Lock-In** | ForgeLM supports only ORPO while market demands DPO/GRPO | High | Phase 5 is top priority — critical market expectation |

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
