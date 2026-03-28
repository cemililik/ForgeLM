# Changelog

All notable changes to ForgeLM are documented here.

## [0.3.0] — 2026-03-28

### Added

**GaLore Optimizer Integration**
- Full-parameter training via gradient low-rank projection — alternative to LoRA
- 6 optimizer variants: `galore_adamw`, `galore_adamw_8bit`, `galore_adafactor`, + layerwise versions
- Configurable rank, update_proj_gap, scale, proj_type, target_modules
- Validation: layerwise + multi-GPU incompatibility detection, LoRA co-existence warning

**Long-Context Optimizations**
- RoPE scaling support: linear, dynamic, YaRN, LongRoPE with configurable factor
- NEFTune noise injection (`neftune_noise_alpha`) for improved training quality
- Sliding window attention override for Mistral-family models
- Sample packing for efficient short-sequence training

**Synthetic Data Pipeline**
- Teacher→student distillation with `--generate-data` CLI command
- Three teacher backends: API (OpenAI-compatible), local (HuggingFace model), file (pre-generated)
- Configurable system prompt, temperature, max_new_tokens, rate limiting
- Four output formats: messages (chat), instruction, chatml, prompt_response
- Seed prompts from JSONL file or inline config

**GPU Cost Estimation**
- Auto-detection for 18 GPU models (T4, A100, H100, RTX 4090, etc.)
- Per-run cost calculation based on training duration and GPU type
- Manual override via `training.gpu_cost_per_hour`

**CI/CD & Publishing**
- PyPI publishing workflow (`.github/workflows/publish.yml`) — `pip install forgelm`
- Nightly compatibility testing (`.github/workflows/nightly.yml`)
- Expanded adversarial prompt library: 140 prompts across 6 categories (was 50/3)

**Wizard Enhancements**
- GaLore strategy option with rank and optimizer selection
- Long-context auto-detection (max_length > 4096) with RoPE scaling prompt
- NEFTune noise injection option

### Fixed
- SFTConfig `max_length` → `max_seq_length` for TRL compatibility
- `device_map={"":0}` for single GPU without 4-bit (prevents model splitting)
- Gradient checkpointing disabled on CPU (requires CUDA)
- Pre-formatted `text` column datasets now properly handled
- Chat template applied during inference in notebooks

### Changed
- Version bump: 0.2.0 → 0.3.0
- All notebooks use SmolLM2-135M for faster Colab testing (was 1.7B)
- Notebooks include base vs fine-tuned model comparison
- 297 tests (up from 242), 0 lint errors

---

## [0.2.0] — 2026-03-26

Major release: ForgeLM goes from a basic SFT fine-tuning tool to a full-stack LLM training platform with alignment, distributed training, safety evaluation, and EU AI Act compliance.

### Added

**Alignment & Post-Training Stack**
- 6 trainer types: SFT, DPO, SimPO, KTO, ORPO, GRPO
- Per-trainer hyperparameters (`dpo_beta`, `kto_beta`, `grpo_num_generations`, etc.)
- Dataset format auto-detection with trainer_type mismatch suggestions

**Distributed Training**
- DeepSpeed ZeRO-2, ZeRO-3, ZeRO-3+Offload presets
- FSDP support with sharding strategies (FULL_SHARD, SHARD_GRAD_OP)
- Unsloth + distributed conflict detection

**Safety & Evaluation**
- Safety classifier gate (Llama Guard) with binary and confidence-weighted scoring
- S1-S14 harm category breakdown with severity levels (critical/high/medium/low)
- Low-confidence alert system for uncertain classifications
- Cross-run safety trend tracking (`safety_trend.jsonl`)
- LLM-as-Judge scoring (API and local model support)
- Automated benchmark evaluation via lm-evaluation-harness
- Built-in adversarial prompt library (50 prompts across 8 categories)
- Human approval gate (`require_human_approval`, exit code 4)

**EU AI Act Compliance (Articles 9-17)**
- Annex IV technical documentation generator
- Structured audit event log (`audit_log.jsonl`) with hash chaining
- Risk assessment declaration (risk level, domain, mitigations)
- Data governance reporting (source, quality, bias mitigation)
- Model integrity verification (SHA-256 checksums for all artifacts)
- Deployer instructions generator (Article 13)
- Evidence bundle export (ZIP archive for auditors)
- QMS SOP templates (5 documents: training, validation, monitoring, change, incident)
- Post-market monitoring configuration scaffold

**Model Capabilities**
- MoE fine-tuning support (expert quantization, selective training)
- Multimodal VLM pipeline detection
- Model merging: TIES, DARE, SLERP, linear interpolation
- Advanced PEFT methods: PiSSA, rsLoRA, DoRA
- Automatic model card generation (HuggingFace format)

**CLI & UX**
- `--wizard` interactive config generator with GPU detection
- `--dry-run` config validation (JSON and text output)
- `--benchmark-only` evaluate existing models without training
- `--merge` standalone model merging
- `--compliance-export` generate audit artifacts
- `--quiet` suppress INFO logs
- `--offline` air-gapped mode (HF_HUB_OFFLINE)
- `--resume` checkpoint resume (auto-detect or explicit path)
- `--output-format json` machine-readable output
- `--log-level` configurable logging
- Exit codes: 0 (success), 1 (config error), 2 (training error), 3 (eval failure), 4 (awaiting approval)

**Infrastructure**
- Docker multi-stage build + docker-compose (training + TensorBoard)
- CI pipeline: 3 parallel jobs (lint, test matrix 3.10/3.11/3.12, validate)
- Ruff linting + formatting enforced
- 242 unit tests across 20 test files
- Branch protection rules on main
- GitHub issue templates (bug report, feature request) + PR template
- Apache License 2.0
- CONTRIBUTING.md + CODE_OF_CONDUCT.md

**Documentation**
- 6 user guides (quickstart, alignment, CI/CD, enterprise, safety, troubleshooting)
- 5 Colab-ready notebooks (SFT, DPO, KTO, GRPO, multi-dataset)
- Full EN/TR documentation (architecture, configuration, usage, roadmap)

### Changed

- Structured logging (`logging` module) replaces all `print()` calls
- Config validation via Pydantic v2 with `extra="forbid"` (typos caught)
- `trust_remote_code` now configurable via YAML (default: false)
- `bf16`/`fp16` auto-detected based on GPU capability
- `no_cuda` replaced with `use_cpu` (HF deprecation)
- `device_map` uses `{"": 0}` on single GPU without 4-bit (prevents model splitting)
- `gradient_checkpointing` auto-disabled on CPU
- `num_proc` for dataset processing scales with CPU count
- `enable_input_require_grads` always called for LoRA compatibility
- Dependency upper bounds pinned to prevent breaking changes
- `max_length` → `max_seq_length` for TRL SFTConfig compatibility
- `text` column datasets supported without reformatting

### Fixed

- 54 code review findings resolved (4 critical, 12 high, 19 medium, 14 low)
- Silent exception handling eliminated across all modules
- MoE expert quantization no longer corrupts weights (was using int8 cast)
- SLERP merge saves/restores base state correctly
- Webhook sanitizes metrics to numeric values only
- DARE merge handles `drop_rate >= 1.0` without division by zero
- Early stopping callback only added when validation data exists
- Audit log uses hash chaining for tamper evidence
- Model integrity hashes all files recursively (not just top-level)
- Checkpoint cleanup only removes `checkpoint-*` dirs (not entire output_dir)

## [0.1.0] — 2026-01-15

### Added

- Initial release
- SFT fine-tuning with TRL SFTTrainer
- LoRA/QLoRA (4-bit NF4) via PEFT
- Unsloth backend support
- DoRA adapter support
- YAML-based configuration
- Webhook notifications (Slack/Teams)
- Model versioning
- Basic evaluation checks (max loss, baseline comparison)
- Auto-revert on quality degradation
