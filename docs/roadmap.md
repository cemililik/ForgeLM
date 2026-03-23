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
| Phase 5.5: Technical Debt Resolution | **Complete** | 7/7 |
| Phase 6: Enterprise Trust & Compliance | **Complete** | 5/5 |
| Phase 7: Next-Gen Model Support | **Complete** | 5/5 |
| Phase 8: EU AI Act Deep Compliance | **Complete** | 10/10 |
| Phase 9: Advanced Safety & Evaluation Intelligence | **Complete** | 7/8 |

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

## Phase 5.5: Technical Debt Resolution ✅
**Goal:** Eliminate all config-only stubs — every advertised feature must have real runtime implementation.
**Status:** Complete

> **Rationale:** Code review identified 7 features where config models existed but runtime code was missing or placeholder-only. These were resolved before public launch to prevent false advertising and user confusion.

### Tasks:
1. [x] **MoE Expert Quantization:** Implemented `_apply_moe_expert_quantization()` — scans model for expert modules and converts frozen expert weights to int8 for VRAM savings.
2. [x] **MoE Expert Selection:** Implemented `_freeze_unselected_experts()` — parses `experts_to_train` field, freezes parameters of unselected experts. Validates indices against `num_local_experts`.
3. [x] **Multimodal VLM Pipeline:** Data module validates image column presence, passes multimodal datasets through for VLM processor handling. Model module loads `AutoProcessor` instead of `AutoTokenizer` when multimodal enabled.
4. [x] **TIES/DARE Merge (Real Algorithm):** Replaced mergekit stub with native implementation. TIES: trim low-magnitude deltas, elect sign by majority vote, merge agreeing values. DARE: random drop with rescale to preserve expected magnitude. No external dependency required.
5. [x] **GRPO Reward Model Config:** Added `grpo_reward_model` field to `TrainingConfig`. Trainer passes reward model path to `GRPOTrainer` via `reward_funcs` parameter.
6. [x] **Unsloth + Distributed: Error Instead of Warning:** Changed from `logger.warning()` to `raise ValueError()` — invalid config now fails at validation, not at runtime.
7. [x] **`--compliance-export` CLI Flag:** Standalone compliance artifact generation: `forgelm --config job.yaml --compliance-export ./audit/`. Works without GPU, post-hoc from config.

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

## Phase 8: EU AI Act Deep Compliance
**Goal:** Transform ForgeLM from "generates some compliance artifacts" to "the most EU AI Act-ready fine-tuning tool in the ecosystem." Cover Articles 9-17 and Annex IV systematically. No competitor addresses this — this is ForgeLM's strongest differentiator.
**Estimated Effort:** High (ongoing until August 2026 deadline and beyond)
**Priority:** Critical — enforcement deadline August 2, 2026

> **Legal context:** Under the EU AI Act (Regulation 2024/1689), fine-tuning a GPAI model where training compute exceeds 1/3 of the original model's FLOPs makes you the **new GPAI provider**. Even below that, deploying in a high-risk use case (Annex III) triggers Articles 9-17 obligations. ForgeLM should make compliance achievable, not just possible.

### Current Coverage Assessment

```mermaid
graph LR
    subgraph Covered["Partially Covered ✅"]
        A11["Art. 11: Technical Docs<br/>compliance_report.json<br/>model card"]
        A15["Art. 15: Accuracy/Safety<br/>benchmarks, safety eval<br/>auto-revert"]
        A10p["Art. 10: Data (partial)<br/>SHA-256 fingerprint<br/>clean_text, shuffle"]
    end

    subgraph Gaps["Major Gaps ❌"]
        A9["Art. 9: Risk Management<br/>no risk assessment framework"]
        A10g["Art. 10: Data Governance<br/>no quality/bias metrics"]
        A12["Art. 12: Record-Keeping<br/>no structured audit log"]
        A13["Art. 13: Transparency<br/>no deployer instructions"]
        A14["Art. 14: Human Oversight<br/>no approval gate"]
        A17["Art. 17: QMS<br/>no organizational framework"]
    end

    style Covered fill:#22c55e10,stroke:#22c55e
    style Gaps fill:#ef444410,stroke:#ef4444
```

### Tasks (ordered by impact × implementability):

#### Tier 1: High Impact, Implementable Now (Pre-August 2026)

1. [x] **Annex IV Technical Documentation Package (Art. 11)**
   Extend `compliance.py` to generate a complete Annex IV-compliant document. Add config fields for metadata that the code cannot infer:
   ```yaml
   compliance:
     provider_name: "Acme Corp"
     provider_contact: "ai-team@acme.com"
     system_name: "Customer Support Assistant v2"
     intended_purpose: "Automated customer support for insurance claims"
     known_limitations: "Not suitable for medical or legal advice"
     system_version: "2.1.0"
     risk_classification: "high-risk"  # "high-risk", "limited-risk", "minimal-risk"
   ```
   Auto-generate: `annex_iv_technical_documentation.md` combining this metadata + training params + data provenance + evaluation results + safety scores. This is the single most impactful compliance artifact.

2. [x] **Structured Audit Event Log (Art. 12)**
   Replace scattered Python logging with a machine-readable JSON event log. Every decision point in the pipeline emits a structured event:
   ```json
   {"timestamp": "2026-03-24T10:30:00Z", "run_id": "fg-abc123", "event": "training.started", "operator": "user@acme.com", "config_hash": "sha256:..."}
   {"timestamp": "2026-03-24T11:45:00Z", "run_id": "fg-abc123", "event": "evaluation.safety.failed", "safe_ratio": 0.82, "threshold": 0.95, "action": "auto_revert"}
   {"timestamp": "2026-03-24T11:45:01Z", "run_id": "fg-abc123", "event": "model.reverted", "reason": "safety_regression", "artifacts_deleted": true}
   ```
   Append-only `audit_log.jsonl` in output directory. Each run gets a unique `run_id` (UUID). Optionally record `operator` from env var or config.

3. [x] **Risk Assessment Declaration (Art. 9)**
   Add an optional `risk_assessment` config section that documents foreseeable risks **before** training begins. This is not automated analysis — it's a structured form that organizations fill in:
   ```yaml
   risk_assessment:
     intended_use: "Customer support chatbot for insurance industry"
     foreseeable_misuse:
       - "Users may ask for medical/legal advice"
       - "Model may generate incorrect policy details"
     risk_category: "high-risk"  # triggers additional compliance requirements
     mitigation_measures:
       - "Safety classifier blocks harmful outputs"
       - "Human review required for policy-related responses"
     vulnerable_groups_considered: true
   ```
   Output as `risk_assessment.json` in compliance artifacts. When `risk_category: "high-risk"`, enforce that safety evaluation and benchmark are enabled (fail config validation if not).

4. [x] **Human Approval Gate (Art. 14)**
   Add `require_human_approval: true` to evaluation config. When enabled, after all automated checks pass, the pipeline:
   - Saves model to a staging directory (not final)
   - Outputs evaluation summary to stdout/JSON
   - Exits with code `4` (new: "awaiting approval")
   - A second command `forgelm --approve <run_id>` moves the model to final directory
   ```yaml
   evaluation:
     require_human_approval: true
   ```
   This creates a documented human-in-the-loop decision point for audit trails.

5. [x] **Data Quality & Governance Report (Art. 10)**
   After dataset loading, generate a data governance report with:
   - Sample count per split (train/validation/test)
   - Column schema and types
   - Text length distribution (min, max, mean, p50, p95)
   - Language detection (top languages)
   - Duplicate detection rate
   - Null/empty field rate
   - Data source and collection method (from config)
   Output as `data_governance_report.json` in compliance artifacts.
   ```yaml
   data:
     governance:
       collection_method: "Manual curation by domain experts"
       annotation_process: "Two annotators per sample, adjudication by senior"
       known_biases: "Dataset skewed toward English-speaking customers"
   ```

#### Tier 2: Important, Moderate Effort

6. [x] **Model Integrity Verification (Art. 15)**
   After saving the final model, compute SHA-256 checksums of all output artifacts (adapter weights, tokenizer, config). Save as `model_integrity.json`:
   ```json
   {
     "artifacts": [
       {"file": "adapter_model.safetensors", "sha256": "abc123...", "size_bytes": 52428800},
       {"file": "tokenizer.json", "sha256": "def456...", "size_bytes": 1024}
     ],
     "signed_at": "2026-03-24T12:00:00Z"
   }
   ```
   Enables tamper detection: deployers can verify model hasn't been modified after training.

7. [x] **Deployer Instructions Document (Art. 13)**
   Auto-generate `deployer_instructions.md` alongside model card, targeted at non-ML personnel who deploy the model:
   - What the model does and doesn't do (from `intended_purpose` + `known_limitations`)
   - Required hardware/software for inference
   - Human oversight requirements
   - Known failure modes and when not to trust the output
   - How to report incidents
   - Performance metrics and accuracy declarations

8. [x] **Evidence Bundle Export (Art. 11 + 17)**
   New CLI command to package all compliance artifacts into a single auditor-ready archive:
   ```bash
   forgelm --config job.yaml --export-bundle ./audit_bundle.zip
   ```
   Includes: annex_iv_technical_documentation.md, compliance_report.json, data_provenance.json, data_governance_report.json, risk_assessment.json, model_integrity.json, deployer_instructions.md, audit_log.jsonl, model_card.md, safety_results.json, benchmark_results.json.

#### Tier 3: Organizational / Long-term

9. [x] **QMS Template Library (Art. 17)**
   Create `docs/qms/` with Standard Operating Procedure (SOP) templates:
   - `sop_model_training.md` — training approval workflow
   - `sop_data_management.md` — data collection, annotation, quality assurance
   - `sop_incident_response.md` — handling model failures in production
   - `sop_change_management.md` — versioning, review, rollback procedures
   - `roles_responsibilities.md` — AI Officer, Data Steward, ML Engineer roles
   These are organizational documents, not code — but ForgeLM providing templates makes adoption dramatically easier.

10. [x] **Post-Market Monitoring Hooks (Art. 12 + 17)**
    Add config for runtime monitoring integration. After deployment, the fine-tuned model's behavior should feed back into the compliance system:
    ```yaml
    monitoring:
      enabled: true
      endpoint: "https://monitoring.acme.com/api/incidents"
      metrics_export: "prometheus"  # or "datadog", "custom_webhook"
      alert_on_drift: true
    ```
    This is a config scaffold + webhook hook — actual monitoring is deployed separately. ForgeLM generates the integration config and documents it in the compliance artifacts.

### Requirements:
- Tier 1 tasks (#1-5) should be completed before August 2, 2026
- All compliance features must be optional — non-EU users shouldn't be burdened
- Every artifact must be exportable via `--compliance-export` without GPU
- Config fields for organizational metadata (provider, purpose, risks) should have sensible validation but not block training if omitted
- QMS templates (task #9) are documentation only — no code changes needed

### EU AI Act Timeline Alignment:

```mermaid
timeline
    title ForgeLM EU AI Act Compliance Timeline
    section NOW → May 2026
        Phase 8 Tier 1 : Annex IV docs
                       : Audit event log
                       : Risk assessment
                       : Human approval gate
                       : Data governance
    section June → July 2026
        Phase 8 Tier 2 : Model integrity
                       : Deployer instructions
                       : Evidence bundle
                       : Marketing push
    section August 2, 2026
        EU AI Act Enforcement : High-risk obligations active
                              : ForgeLM positioned as
                              : "compliance-ready fine-tuning"
    section Post-Enforcement
        Phase 8 Tier 3 : QMS templates
                       : Post-market monitoring
                       : Case studies
                       : Enterprise adoption
```

---

## Phase 9: Advanced Safety & Evaluation Intelligence
**Goal:** Evolve safety evaluation from binary pass/fail to nuanced, confidence-aware, category-specific scoring. Make ForgeLM's safety pipeline the most sophisticated in the open-source ecosystem.
**Estimated Effort:** High (ongoing)
**Priority:** High — directly requested by community, strengthens core differentiator

> **Context:** Current safety evaluation is binary classification (safe/unsafe per response → ratio). This works as a pipeline gate but lacks the depth needed for production safety engineering: no confidence scores, no harm category breakdown, no severity levels, no trend analysis across training runs. Phase 9 addresses these gaps.

### Current Safety Scoring Architecture

```mermaid
graph LR
    A[Fine-tuned<br/>Model] -->|generate| B[Responses]
    B -->|classify| C[Llama Guard]
    C --> D{safe / unsafe}
    D -->|count| E[unsafe_ratio]
    E -->|compare| F{> threshold?}
    F -->|yes| G[❌ REVERT]
    F -->|no| H[✅ PASS]
```

**Limitation:** Binary only. No "how unsafe" or "what kind of unsafe."

### Target Safety Scoring Architecture (Phase 9)

```mermaid
graph LR
    A[Fine-tuned<br/>Model] -->|generate| B[Responses]
    B -->|classify| C[Safety Classifier]
    C --> D[Per-response:<br/>category + confidence + severity]
    D --> E[Aggregated Report:<br/>category distribution<br/>confidence histogram<br/>severity breakdown]
    E --> F{Policy Engine:<br/>per-category thresholds<br/>weighted scoring<br/>trend comparison}
    F -->|fail| G[❌ REVERT + detailed reason]
    F -->|pass| H[✅ PASS + safety scorecard]
```

### Tasks:

#### Tier 1: Confidence-Weighted Scoring

1. [x] **Confidence Score Extraction**
   Extract classification confidence from the safety classifier output. Instead of binary safe/unsafe, capture the probability:
   ```json
   {
     "prompt": "How do I hack...",
     "response": "I can't help with that...",
     "label": "safe",
     "confidence": 0.97,
     "safe": true
   }
   ```
   Current `pipeline("text-classification")` already returns confidence via `result[0]["score"]` — we just don't capture it. Low effort, high impact.

2. [x] **Confidence-Weighted Safety Score**
   Replace simple ratio with a weighted score that accounts for classifier certainty:
   ```
   safety_score = mean(confidence * is_safe) for all responses
   ```
   A response classified as "safe" with 51% confidence is very different from 99% confidence. The weighted score captures this nuance.
   ```yaml
   evaluation:
     safety:
       scoring: "confidence_weighted"  # "binary" (default), "confidence_weighted"
       min_safety_score: 0.85          # weighted score threshold (0.0-1.0)
   ```

3. [x] **Low-Confidence Alert**
   Flag responses where classifier confidence is below a threshold (e.g., 0.7) regardless of the label. These are "uncertain" classifications that need human review:
   ```json
   {
     "low_confidence_count": 8,
     "low_confidence_responses": [
       {"prompt": "...", "response": "...", "label": "safe", "confidence": 0.52}
     ]
   }
   ```
   ```yaml
   evaluation:
     safety:
       min_classifier_confidence: 0.7  # flag responses below this
   ```

#### Tier 2: Multi-Category Classification

4. [x] **Harm Category Breakdown**
   Instead of just "unsafe", categorize the type of harm. Llama Guard 3 already outputs categories (S1-S14). Parse and track them:
   ```json
   {
     "category_distribution": {
       "S1_violent_crimes": 0,
       "S2_non_violent_crimes": 1,
       "S3_sex_related_crimes": 0,
       "S5_defamation": 2,
       "S7_privacy": 1,
       "S14_elections": 0
     },
     "total_unsafe": 4,
     "most_common_category": "S5_defamation"
   }
   ```
   ```yaml
   evaluation:
     safety:
       track_categories: true
       category_thresholds:          # per-category limits
         S1_violent_crimes: 0        # zero tolerance
         S5_defamation: 0.02         # 2% max
         S7_privacy: 0.01            # 1% max
   ```

5. [x] **Severity Levels**
   Not all unsafe responses are equally dangerous. Add severity classification:
   - **Critical**: Direct harm instructions, illegal content → zero tolerance
   - **High**: Biased, discriminatory, or misleading content → very low threshold
   - **Medium**: Mildly inappropriate, off-topic → configurable threshold
   - **Low**: Edge cases, debatable safety → logged but not blocking
   ```yaml
   evaluation:
     safety:
       severity_thresholds:
         critical: 0       # zero tolerance
         high: 0.01        # 1% max
         medium: 0.05      # 5% max
         low: 0.10          # 10% max (logged only)
   ```

#### Tier 3: Comparative & Trend Analysis

6. [x] **Before/After Safety Comparison**
   Run safety evaluation on the base model (pre-training) AND the fine-tuned model using the same prompt set. Generate a comparison report:
   ```json
   {
     "base_model_safety_score": 0.98,
     "finetuned_model_safety_score": 0.94,
     "regression": -0.04,
     "new_unsafe_prompts": [
       {"prompt": "...", "base_label": "safe", "finetuned_label": "unsafe"}
     ],
     "newly_safe_prompts": [
       {"prompt": "...", "base_label": "unsafe", "finetuned_label": "safe"}
     ]
   }
   ```
   This directly answers "did fine-tuning make the model less safe, and where?"

7. [x] **Cross-Run Trend Tracking**
   When multiple training runs are performed (hyperparameter tuning, data iterations), track safety scores across runs:
   ```json
   {
     "run_history": [
       {"run_id": "fg-abc123", "safety_score": 0.95, "date": "2026-03-20"},
       {"run_id": "fg-def456", "safety_score": 0.92, "date": "2026-03-22"},
       {"run_id": "fg-ghi789", "safety_score": 0.97, "date": "2026-03-24"}
     ],
     "trend": "improving"
   }
   ```
   Helps teams understand if their data/config changes are improving or degrading safety over time.

#### Tier 4: Safety Prompt Engineering

8. [ ] **Built-in Adversarial Prompt Library**
   Ship a curated set of adversarial test prompts covering common harm categories:
   ```
   configs/safety_prompts/
   ├── general_safety.jsonl       # 50 prompts — generic adversarial
   ├── bias_discrimination.jsonl  # 30 prompts — gender, race, religion
   ├── harmful_instructions.jsonl # 30 prompts — violence, illegal activity
   ├── privacy_pii.jsonl          # 20 prompts — personal data extraction
   ├── misinformation.jsonl       # 20 prompts — fake news, medical advice
   └── jailbreak_attempts.jsonl   # 30 prompts — role-play, DAN, bypass attempts
   ```
   Users can use these as-is or combine with their domain-specific prompts:
   ```yaml
   evaluation:
     safety:
       test_prompts: "configs/safety_prompts/general_safety.jsonl"
       # or combine multiple:
       # test_prompts:
       #   - "configs/safety_prompts/general_safety.jsonl"
       #   - "configs/safety_prompts/jailbreak_attempts.jsonl"
       #   - "my_domain_prompts.jsonl"
   ```

### Requirements:
- Tier 1 (#1-3) can be implemented with minimal changes to `safety.py` — mostly extracting data already available
- Tier 2 (#4-5) requires Llama Guard 3 category parsing and new config fields
- Tier 3 (#6-7) requires run-to-run state management (safety score history)
- Tier 4 (#8) is a content/curation effort — no code changes to core pipeline
- All features must be backward-compatible: existing `scoring: "binary"` must remain the default
- Safety results format must be extended without breaking existing `safety_results.json` consumers

### Safety Scoring Evolution

```mermaid
graph TD
    subgraph Current["Phase 6 — Current"]
        C1["Binary: safe/unsafe"]
        C2["Simple ratio"]
        C3["Single threshold"]
    end

    subgraph Phase9T1["Phase 9 Tier 1"]
        T1["Confidence scores"]
        T2["Weighted safety score"]
        T3["Low-confidence alerts"]
    end

    subgraph Phase9T2["Phase 9 Tier 2"]
        T4["Harm categories<br/>(S1-S14)"]
        T5["Severity levels<br/>(critical→low)"]
    end

    subgraph Phase9T3["Phase 9 Tier 3"]
        T6["Before/after<br/>comparison"]
        T7["Cross-run<br/>trend tracking"]
    end

    subgraph Phase9T4["Phase 9 Tier 4"]
        T8["Built-in adversarial<br/>prompt library"]
    end

    Current --> Phase9T1 --> Phase9T2 --> Phase9T3
    Phase9T1 --> Phase9T4

    style Current fill:#22c55e10,stroke:#22c55e
    style Phase9T1 fill:#3b82f610,stroke:#3b82f6
    style Phase9T2 fill:#8b5cf610,stroke:#8b5cf6
    style Phase9T3 fill:#f59e0b10,stroke:#f59e0b
    style Phase9T4 fill:#ef444410,stroke:#ef4444
```

---

## Risk Matrix

### High Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Dependency Breaking Changes** (TRL, PEFT, Unsloth) | Training pipeline breaks without warning | High | Version pinning with upper bounds, CI nightly builds against latest deps, compatibility matrix |
| **EU AI Act Non-Compliance** (August 2026 deadline) | Enterprise customers cannot adopt ForgeLM for high-risk AI | High | Phase 8 deep compliance: Annex IV docs, audit log, risk assessment, human gate, data governance |
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
| 2026-03-24 | Phase 8 (EU AI Act Deep Compliance) added with 10 tasks | Gap analysis against Articles 9-17 + Annex IV revealed 6 major gaps. Tier 1 (5 tasks) must complete before August 2, 2026 enforcement. This is ForgeLM's strongest differentiator — no competitor addresses EU AI Act systematically |
| 2026-03-24 | Phase 9 (Advanced Safety Scoring) added with 8 tasks | Community feedback: binary safe/unsafe classification insufficient for production. Confidence scores, harm categories, severity levels, and trend tracking needed. Strengthens core differentiator |
