# Sürüm Notları

> **Not:** Bu dosya yayınlanmış ve yakında yayınlanacak sürümleri takip eder. Her sürüm, bir veya daha fazla tamamlanmış phase'e karşılık gelir.

## v0.3.0 Release

**Status:** Complete
**Release Date:** March 2026

### Features:
1. [x] **GaLore**: Optimizer-level memory optimization — full-parameter training via gradient low-rank projection as an alternative to LoRA. Config fields: `galore_enabled`, `galore_optim`, `galore_rank`, `galore_update_proj_gap`, `galore_scale`, `galore_proj_type`, `galore_target_modules`.
2. [x] **Long-Context Training**: RoPE scaling, NEFTune noise injection, sliding window attention, and sample packing for extended context windows. Config fields: `rope_scaling`, `neftune_noise_alpha`, `sliding_window_attention`, `sample_packing`.
3. [x] **Synthetic Data Pipeline**: Teacher-to-student distillation via `--generate-data` CLI flag. New `SyntheticDataGenerator` class in `forgelm/synthetic.py`. Configurable teacher model, backend, seed prompts, and output format.
4. [x] **PyPI Publishing**: `pip install forgelm` now works. Automated publishing via `publish.yml` GitHub Actions workflow.
5. [x] **GPU Cost Estimation**: Auto-detection for 18 GPU models with per-run cost tracking. Included in JSON output, webhook notifications, and model cards.
6. [x] **Nightly CI**: `.github/workflows/nightly.yml` for compatibility testing against latest dependency versions.
7. [x] **Expanded Adversarial Prompts**: 6 category files, 140 prompts (up from 50) covering general safety, bias/discrimination, harmful instructions, privacy/PII, misinformation, and jailbreak attempts.

---

---

## v0.3.1rc1 — "Security & Config Hardening" (2026-04-25)

**Status:** Released (release candidate)

### Changes:
- **Security**: Webhook URLs excluded from HuggingFace Hub model cards — prevent credential leaks
- **Security**: User-supplied strings sanitized before Markdown template embedding (content injection prevention)
- **Config robustness**: All 19 Pydantic sub-models now enforce `extra="forbid"` — YAML typos are errors, not silent bugs
- **Config robustness**: Deprecated `lora.use_dora` / `lora.use_rslora` booleans now auto-normalize to `lora.method: "dora"/"rslora"` with deprecation warnings
- **Compliance**: Audit log hash chain now restores continuity across process restarts — cross-run tamper evidence
- **Compliance**: Compliance manifests correctly report pre-OOM-recovery batch size
- **GRPO**: Reward model path now correctly wrapped as callable (was passing string, causing TypeError)
- **Safety**: Safety classifier now receives full `[INST] prompt [/INST] response` conversation context (was response-only)
- **Data**: Extension-less files now raise clear ValueError instead of silently loading wrong format
- **Merging**: TIES tie-breaking fixed (zero-vote no longer zeros parameters); DARE now deterministic with seed=42
- **Config validators**: New — mix_ratio negative/all-zero, float32+4bit warning, high LoRA rank warning, eval_steps>save_steps warning
- **Tests**: 25 new regression tests; coverage threshold raised from 25% to 40%

---

## v0.4.0 — "Post-Training Completion" (Planlandı)

Odak: [Phase 10](phase-10-post-training.md). Full post-training handoff: inference, chat, GGUF export, VRAM fit-check, deployment config generation. All five Phase 10 tasks (inference.py, chat.py, export, fit-check, deploy) complete before tagging v0.4.0.

---

## v0.4.5 — "Quickstart Layer" (Planlandı)

Focus: [Phase 10.5](phase-12-quickstart.md) (Quickstart). Pre-built templates, sample datasets, `forgelm quickstart <template>` command. Direct community growth driver. Unblocked by Phase 10 tasks 1 + 2 (inference.py and chat.py) only; can begin development in parallel with Phase 10 tasks 3-5.

---

## v0.5.0 — "Data Ingestion" (Planlandı)

Odak: [Phase 11](phase-11-data-ingestion.md). Document ingestion pipeline: PDF/DOCX/EPUB → JSONL, PII detection, near-duplicate audit. Builds on Quickstart foundation.

---

## v0.5.1 — "Pipeline Chains" (Planlandı)

Focus: [Phase 14](phase-14-pipeline-chains.md). Multi-stage SFT → DPO → GRPO chained config, pipeline provenance artifacts for EU AI Act Annex IV compliance. No hard blockers; starts after Phase 10 lands.

---

## v0.6.0-pro — "Pro CLI" (Planlandı, gated)

Odak: [Phase 13](phase-13-pro-cli.md). Traction doğrulamasına bağlı — `v0.5.0` için ≥1K aylık PyPI install + ≥2 ücretli destek sözleşmesi olmadan başlama.
