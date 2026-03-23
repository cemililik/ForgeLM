# ForgeLM Enterprise Roadmap (2026+)

Based on the strategic vision outlined in the 2026 Upgrade Proposal, this roadmap details the execution phases required to transition ForgeLM from a foundational fine-tuning script into a robust **Enterprise MLOps Station**.

---

## Phase 1: Foundational SOTA Upgrades (The 2026 Baseline)
**Goal:** Bring the core training engine up to the early-2026 State-of-the-Art (SOTA) standards.
**Estimated Effort:** Low-Medium

### Tasks:
1. [x] **4-Bit QLoRA & DoRA Implementation:** Update `model.py` to utilize `BitsAndBytesConfig` for NF4 quantization and expose `use_dora` flags via the PEFT config.
2. [x] **TRL `SFTTrainer` Migration:** Replace the standard HF `Trainer` with `SFTTrainer` to support automatic sequence packing and masking.
3. [x] **Chat Template Standardization:** Update `data.py` to use `tokenizer.apply_chat_template()` instead of manual string concatenation to ensure perfect conversational formatting for modern models.
4. [x] **Unsloth Backend Support:** Add a `backend: "unsloth"` option in the YAML configuration to allow users to bypass standard transformers loading for 2x-5x faster training.
5. [x] **Blackwell (GB10) Optimization (v1.1):** Research and implement specific flags like `expandable_segments:True` and create a dedicated `setup_for_blackwell.sh` for CUDA 13.0 environments. [Design Doc](design_blackwell_optimized.md)
6. [x] **Pre-flight Dataset & Model Validation:** Add checks to ensure models are in `safetensors` format and datasets match expected conversational/prompt-completion patterns before loading weights.

### Requirements:
- Deep testing of the `unsloth` library compatibility across different GPUs.
- Updates to the Pydantic schemas in `config.py` to support the new flags.

---

## Phase 2: Autonomous Evaluation & Validation
**Goal:** Ensure that training never blindly overwrites good models; implement automated checks.
**Estimated Effort:** Medium

### Tasks:
1. [/] **Automated Benchmarking:** Integrate a post-training evaluation script (e.g., using EleutherAI's `lm-evaluation-harness` or a custom LLM-as-a-Judge pipeline).
2. [/] **Model Reversion Mechanism:** If the newly trained LoRA adapters score worse on the validation/benchmark sets than the base model, automatically discard the adapters and log an error. (Integrated into `trainer.py`).
3. [x] **Slack/Teams Webhook Integration:** Add `notify_webhook` to the YAML config to send a message when a training job starts, succeeds (with metrics), or fails.
4. [ ] **Interactive Configuration Wizard (`forgelm --wizard`):** A step-by-step CLI prompt to help beginners generate their first valid `config.yaml` without manual editing. [Design Doc](design_wizard_mode.md)
5. [x] **Runtime Smoke Test Automation:** Add `tests/runtime_smoke.py` to verify full training loops on CPU/CI environments.

### Requirements:
- A standardized set of internal test datasets.
- Environment variables or config secrets for webhook URLs.

---

## Phase 3: Cloud & Cost Automation (The Enterprise Crown Jewel)
**Goal:** Abstract away the hardware layer entirely. Allow users to provide only data and configuration, and let ForgeLM handle the cloud infrastructure.
**Estimated Effort:** High

### Tasks:
1. **RunPod / Lambda Labs API Integration:** Create a new module (`cloud.py`). If `target: runpod` is in the execution command, ForgeLM automatically rents a GPU instance via API.
2. **Environment Bootstrapping:** ForgeLM automatically uploads the dataset and config to the rented instance, installs itself, and runs the training job.
3. **Artifact Retrieval & Instance Termination:** Upon completion, the model weights are downloaded to the user's local machine or pushed to a private HF Hub account, and the expensive GPU instance is immediately destroyed to stop billing.

### Requirements:
- RunPod / Lambda Labs API keys.
- Robust error handling (e.g., ensuring instances are destroyed even if the training script crashes).

---

## Risk & Opportunity Analysis

### Opportunities
- **Pioneering Open-Source MLOps:** Very few open-source tools act as a complete, declarative bridge between raw data, hardware rental, and SOTA model training. 
- **Corporate Adoption:** Banks, healthcare providers, and defense contractors desperately need transparent tools that can run inside their VPCs or on-premise without sending data to OpenAI. 
- **Time-to-Market:** Implementing Unsloth and QLoRA immediately puts ForgeLM in the top 10% of training tools available on GitHub.

### Risks
- **Ecosystem Volatility:** The AI space moves incredibly fast. Unsloth or `trl` could introduce breaking changes to their APIs, requiring constant maintenance of ForgeLM.
- **Hardware Dependencies:** Phase 3 requires maintaining active integrations with 3rd-party cloud providers whose APIs or pricing models may change.
- **Dependency Bloat:** Adding `unsloth`, `trl`, evaluation harnesses, and cloud SDKs will drastically increase the size of `requirements.txt`. We must ensure modular installation (e.g., `pip install forgelm[cloud]`).
