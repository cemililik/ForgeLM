# ForgeLM Product Strategy

> **Last Updated:** 2026-03-23
> **Purpose:** Define ForgeLM's market position, target users, and strategic direction.

---

## Mission Statement

ForgeLM makes enterprise LLM fine-tuning **simple, repeatable, and secure** through a config-driven, CI/CD-native approach that runs anywhere — cloud, on-premise, or air-gapped.

---

## Target Users

### Primary: MLOps / Data Engineers
- Build automated training pipelines (`git push → train → evaluate → deploy`)
- Need deterministic, YAML-driven workflows — not Jupyter Notebooks
- Operate in CI/CD environments (GitHub Actions, GitLab CI, Jenkins)
- Require silent, headless execution with structured output

### Secondary: AI/ML Engineers at Regulated Industries
- Banks, healthcare, defense — cannot send data to external APIs
- Need on-premise / air-gapped execution with full audit trails
- Require security-conscious defaults (`trust_remote_code: false`)
- Value open-source transparency and reproducibility

### Tertiary: Independent Researchers & Developers
- Want to fine-tune models without deep infrastructure knowledge
- Need sensible defaults and quick-start guides
- Benefit from wizard mode and example configurations

---

## Core Value Proposition

**"YAML in, fine-tuned model out."**

ForgeLM differentiates from competitors through three pillars:

### 1. Config-Driven (Declarative Training)
- Entire training runs defined in a single YAML file
- No Python code required from end users
- Deterministic, reproducible, version-controllable
- Natural fit for CI/CD pipelines and GitOps workflows

### 2. Enterprise-Ready
- Webhook notifications for training lifecycle events
- Automated quality gates (evaluation, auto-revert)
- Meaningful exit codes for pipeline orchestration
- Structured logging for observability platforms

### 3. Run Anywhere
- Standard Transformers backend as universal fallback
- Unsloth backend for high-performance environments
- Docker images for portable deployment
- Air-gapped mode for regulated industries

---

## What ForgeLM is NOT

To maintain focus, ForgeLM explicitly avoids:

- **A GUI/Web application.** Config files are the interface. Users wanting GUIs should use LLaMA-Factory or AutoTrain.
- **A cloud infrastructure provider.** ForgeLM trains models — it does not manage cloud instances. Users bring their own compute.
- **A model serving platform.** ForgeLM outputs trained adapters/models. Deployment is handled by vLLM, TGI, or similar tools.
- **A general ML training framework.** ForgeLM is specifically for LLM fine-tuning with LoRA/QLoRA, not computer vision or classical ML.

---

## Strategic Decisions

### Docker over Direct Cloud API
**Decision:** Provide official Docker images instead of integrating directly with RunPod/Lambda Labs APIs.
**Rationale:** Direct cloud integration creates unsustainable maintenance burden, introduces 3rd-party API dependency risk, and expands scope beyond core competency. Docker images are portable, user-controlled, and work with any cloud provider or on-premise infrastructure.

### Reliability over Features
**Decision:** Phase 2.5 (reliability hardening) inserted before new feature development.
**Rationale:** Silent failures, insufficient test coverage, and print-based logging are production blockers. New features built on unreliable foundations create compounding technical debt.

### Modular Dependencies
**Decision:** All non-core features are optional (`pip install forgelm[unsloth]`, `forgelm[eval]`, etc.).
**Rationale:** Core installation must remain lightweight. Users should only install what they need. This prevents dependency conflicts and reduces attack surface.

---

## Success Metrics

### Short-Term (6 months)
- Zero silent failures in production pipelines
- >80% test coverage on core modules
- `--dry-run` validates full pipeline without GPU
- Docker image available and documented

### Medium-Term (12 months)
- 3+ enterprise teams using ForgeLM in production CI/CD pipelines
- Full `lm-evaluation-harness` integration
- Air-gapped mode validated in isolated environments
- Published CI/CD integration guides for top 3 platforms

### Long-Term (24 months)
- Recognized as the standard open-source tool for config-driven LLM fine-tuning
- Community-contributed config templates for common use cases
- ORPO/preference learning support
- Distributed training (DeepSpeed/FSDP) available

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview and quick start |
| [Architecture](architecture.md) | System design and component details |
| [Configuration Guide](configuration.md) | YAML parameter reference |
| [Usage Guide](usage.md) | How to run training |
| [Data Preparation](data_preparation.md) | Dataset format requirements |
| [Roadmap](roadmap.md) | Phase-based execution plan |
| [Product Strategy](product_strategy.md) | Market position and strategic direction (this document) |
| [Blackwell Design](design_blackwell_optimized.md) | GB10 optimization design |
| [Wizard Mode Design](design_wizard_mode.md) | Interactive configuration wizard design |

All documents are available in Turkish (`*-tr.md`).
