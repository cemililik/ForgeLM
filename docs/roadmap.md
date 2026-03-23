# ForgeLM Enterprise Roadmap (2026+)

Based on the strategic vision outlined in the [2026 Upgrade Proposal](2026_upgrade_proposal.md) and the comprehensive product analysis conducted in March 2026, this roadmap details the execution phases required to transition ForgeLM from a foundational fine-tuning toolkit into a robust **Enterprise MLOps Station**.

> **Guiding Principle:** Reliability before features. Every new capability must be built on a tested, observable, and well-documented foundation.

---

## Current Status Summary

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: SOTA Upgrades | **Complete** | 6/6 |
| Phase 2: Evaluation & Validation | **Complete** | 5/5 |
| Phase 2.5: Reliability & Maturity | **Complete** | 8/8 |
| Phase 3: Enterprise Integration | **In Progress** | 6/6 |
| Phase 4: Ecosystem Growth | **Vision** | 0/5 |

---

## Phase 1: Foundational SOTA Upgrades ✅
**Goal:** Bring the core training engine up to the early-2026 State-of-the-Art (SOTA) standards.
**Status:** Complete

### Tasks:
1. [x] **4-Bit QLoRA & DoRA Implementation:** `model.py` updated to utilize `BitsAndBytesConfig` for NF4 quantization with `use_dora` flag support via PEFT config.
2. [x] **TRL `SFTTrainer` Migration:** Standard HF `Trainer` replaced with `SFTTrainer` for automatic sequence packing and masking.
3. [x] **Chat Template Standardization:** `data.py` now uses `tokenizer.apply_chat_template()` instead of manual string concatenation.
4. [x] **Unsloth Backend Support:** `backend: "unsloth"` option available in YAML for 2x-5x faster training.
5. [x] **Blackwell (GB10) Optimization:** Specific flags for CUDA 13.0 environments. [Design Doc](design_blackwell_optimized.md)
6. [x] **Pre-flight Dataset & Model Validation:** Checks for `safetensors` format and dataset schema patterns before loading weights.

---

## Phase 2: Autonomous Evaluation & Validation (In Progress)
**Goal:** Ensure that training never blindly overwrites good models; implement automated checks.
**Status:** 3 of 5 tasks complete

### Tasks:
1. [x] **Automated Benchmarking:** Post-training evaluation via `lm-evaluation-harness`. Full integration with configurable tasks, min_score threshold, auto-revert, webhook notifications, and `--benchmark-only` CLI mode.
2. [x] **Model Reversion Mechanism:** Auto-discard LoRA adapters if they score worse than baseline. *(Edge cases hardened: NaN/inf handling, rmtree safety, improvement logging)*
3. [x] **Slack/Teams Webhook Integration:** `webhook` section in YAML config sends structured JSON payloads on start/success/failure.
4. [x] **Interactive Configuration Wizard (`forgelm --wizard`):** Step-by-step CLI to generate valid `config.yaml`. [Design Doc](design_wizard_mode.md) *(Implemented in Phase 3)*
5. [x] **Runtime Smoke Test Automation:** `tests/runtime_smoke.py` verifies full training loops on CPU/CI environments.

---

## Phase 2.5: Reliability & Production Readiness (NEW — Top Priority)
**Goal:** Harden the existing codebase for production use. No new features — only stability, observability, and safety improvements.
**Estimated Effort:** Medium (2-3 weeks)

> **Rationale:** The March 2026 product analysis identified critical reliability gaps — silent exception handling, insufficient test coverage, and missing observability — that must be resolved before adding new features. Building on an untested foundation compounds technical debt.

### Tasks:
1. [x] **Structured Logging Migration:** Replace all `print()` statements with Python `logging` module. Add configurable log levels (`--log-level`) and JSON log format option for cloud/container environments.
2. [x] **Silent Failure Elimination:** Audit and fix all `except Exception:` blocks across the codebase. Every caught exception must be logged with context. Critical failures (data formatting fallback, adapter disable failure) must emit warnings visible to the user.
3. [x] **Test Coverage Expansion:** Add unit tests for each core module:
   - `config.py`: Validation edge cases, conflicting configuration detection
   - `data.py`: Format detection, chat template fallback, empty dataset handling
   - `model.py`: Backend selection, quantization config resolution
   - `webhook.py`: Payload format, env var resolution, timeout handling
4. [x] **Dependency Version Pinning:** Add upper-bound version constraints to `pyproject.toml` for critical dependencies (`trl`, `peft`, `transformers`, `unsloth`). Create a compatibility matrix document.
5. [x] **Security Hardening:** Make `trust_remote_code` configurable via YAML (default: `false`). Add warning when enabled. This is an enterprise adoption blocker.
6. [x] **CLI Maturity:**
   - `--version` flag
   - `--dry-run` / `--validate-only` mode (parse config, validate model/dataset access, exit without training)
   - Meaningful exit codes: `0` success, `1` config error, `2` training failure, `3` evaluation failure
7. [x] **Error Diagnostics Improvement:** Differentiate error types in CLI output. Config validation errors should show the exact field and expected type. Training errors should include hardware context (GPU model, VRAM, CUDA version).
8. [x] **CI/CD Pipeline Hardening:** Add to GitHub Actions:
   - Unit test execution with coverage reporting
   - Dependency vulnerability scanning
   - Config template validation test

### Success Criteria:
- Zero silent failures in the codebase
- >80% test coverage on core modules
- All exceptions produce actionable log messages
- `--dry-run` validates full pipeline without GPU

---

## Phase 3: Enterprise Integration
**Goal:** Make ForgeLM the standard tool for config-driven, CI/CD-native, on-premise LLM fine-tuning.
**Estimated Effort:** High (1-3 months)

> **Strategic Decision:** The original Phase 3 proposed direct RunPod/Lambda Labs API integration. After analysis, this approach is **deprioritized** in favor of a containerized strategy. Direct cloud API integration creates unsustainable maintenance burden, 3rd-party API dependency risk, and dilutes ForgeLM's core value proposition. Instead, we provide portable Docker images and let users handle infrastructure with their existing tools (Terraform, Pulumi, Kubernetes).

### Tasks:
1. [x] **Interactive Configuration Wizard (`forgelm --wizard`):** *(Moved from Phase 2)* Hardware detection, model selection, strategy recommendation, YAML generation. [Design Doc](design_wizard_mode.md)
2. [x] **Automated Benchmarking Completion:** Full `lm-evaluation-harness` integration with configurable task sets. Results included in webhook notifications and final output.
3. [ ] **Docker Image & Container Support:** Official `Dockerfile` and `docker-compose.yaml` for single-command training: `docker run forgelm --config job.yaml`. Pre-built images with CUDA, Unsloth, and evaluation dependencies.
4. [x] **JSON Output Mode (`--output-format json`):** Machine-readable structured output for all pipeline stages. Enables programmatic integration with CI/CD systems, dashboards, and orchestrators.
5. [x] **Offline / Air-Gapped Mode:** Full operation without internet access. Local model loading, local dataset only, no HF Hub calls. Critical for defense/healthcare/banking deployments.
6. [x] **Checkpoint Resume (`--resume`):** Resume training from the last saved checkpoint after interruption. Essential for long-running jobs on preemptible instances.

### Requirements:
- Docker multi-stage builds for minimal image size
- Comprehensive testing of offline mode across all code paths
- Documentation: CI/CD integration guide with GitHub Actions, GitLab CI examples

---

## Phase 4: Ecosystem Growth (Vision)
**Goal:** Expand ForgeLM's capabilities for advanced use cases while maintaining simplicity.
**Estimated Effort:** Ongoing

### Tasks:
1. [ ] **ORPO Trainer:** Single-stage preference alignment using `chosen`/`rejected` datasets. Eliminates the need for separate SFT + DPO stages.
2. [ ] **Experiment Tracking Integration:** Optional W&B / MLflow integration for metric logging, model comparison, and hyperparameter search visualization.
3. [ ] **Multi-Dataset Training:** Support multiple JSONL/HF datasets in a single training run with configurable mixing ratios.
4. [ ] **Automatic Model Card Generation:** Generate HF-compatible model cards with training config, metrics, dataset info, and evaluation results.
5. [ ] **DeepSpeed / FSDP Support:** Distributed training across multiple GPUs for larger models (30B+ parameters).

### Requirements:
- Each feature must be fully optional (no new required dependencies)
- Modular installation: `pip install forgelm[tracking]`, `pip install forgelm[distributed]`

---

## Risk Matrix

### High Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Dependency Breaking Changes** (TRL, PEFT, Unsloth) | Training pipeline breaks without warning | High | Version pinning with upper bounds, CI nightly builds against latest deps, compatibility matrix |
| **Silent Failures in Production** | Models trained on incorrectly formatted data, undetected quality regression | High | Phase 2.5 eliminates all silent exception handling |
| **Security: `trust_remote_code=True`** | Arbitrary code execution from untrusted model repos | Medium | Make configurable, default to `false`, document risk |

### Medium Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Scope Creep** (cloud automation, too many features) | Maintenance burden exceeds capacity, core quality degrades | Medium | Strict phase gating — no Phase 3 work until Phase 2.5 criteria met |
| **Ecosystem Commoditization** | Competing tools (Axolotl, LLaMA-Factory) add similar features | Medium | Double down on CI/CD-native + enterprise positioning |
| **GPU/CUDA Version Fragmentation** | Users on different CUDA versions hit incompatibilities | Medium | Docker images pin CUDA versions, compatibility matrix |

### Low Severity
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Blackwell-specific code becomes obsolete** | Wasted effort if architecture not widely adopted | Low | Keep as optional, detect-and-enable pattern |
| **HF Hub API changes** | Dataset/model loading breaks | Low | Abstract behind interface, version pin `huggingface_hub` |

---

## Opportunity Analysis

### Immediate Opportunities
1. **CI/CD Pipeline Integration** — ForgeLM's YAML-driven design is uniquely suited for `git push → train → evaluate → notify` workflows. A demo tutorial showing this flow would drive GitHub adoption significantly.
2. **On-Premise / Air-Gapped Market** — Banks, healthcare, defense cannot send data externally. ForgeLM + Docker image = complete on-premise solution with zero cloud dependency.

### Medium-Term Opportunities
3. **Enterprise Consulting & Support** — Organizations adopting ForgeLM for production will need custom integrations, training, and support contracts.
4. **Model Registry Integration** — Versioned model storage with comparison dashboards bridges the gap between training and deployment.

### Long-Term Opportunities
5. **Managed ForgeLM Service** — SaaS offering where users upload data + config and receive trained models. Built on the same open-source core.
6. **Training Marketplace** — Pre-built config templates for common use cases (customer support bot, legal document analyzer, code assistant).

---

## Competitive Positioning

| Competitor | ForgeLM Advantage | ForgeLM Disadvantage |
|------------|-------------------|----------------------|
| **Axolotl** | Simpler config, easier onboarding, CI/CD-native | Axolotl supports more model architectures and training methods |
| **LLaMA-Factory** | Declarative YAML vs GUI dependency, better for automation | LLaMA-Factory has web UI for non-technical users |
| **Unsloth (direct)** | Multi-backend fallback, evaluation, webhook, enterprise features | Unsloth is faster when used directly |
| **AutoTrain** | Open-source, on-premise, full control, no vendor lock-in | AutoTrain is more user-friendly for beginners |
| **Custom Scripts** | Validated pipeline, config management, checkpoint handling | Custom scripts offer unlimited flexibility |

**ForgeLM's niche is clear:** Config-driven, CI/CD-native, on-premise LLM fine-tuning. Own this niche — do not try to be everything.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-23 | Inserted Phase 2.5 (Reliability) before new features | Product analysis revealed critical silent failure and test coverage gaps |
| 2026-03-23 | Deprioritized direct cloud API integration (original Phase 3) | Unsustainable maintenance burden, 3rd-party dependency risk, scope creep |
| 2026-03-23 | Adopted Docker-based deployment strategy | Portable, user-controlled infrastructure, minimal maintenance for ForgeLM team |
| 2026-03-23 | Moved wizard mode from Phase 2 to Phase 3 | Reliability work takes priority over UX improvements |
| 2026-03-23 | Added `trust_remote_code` as enterprise adoption blocker | Security risk incompatible with regulated industries |
