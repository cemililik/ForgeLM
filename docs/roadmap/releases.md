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

## v0.4.0 — "Post-Training Completion" (Planlandı)

Odak: [Phase 10](phase-10-post-training.md). Inference, chat, GGUF export, VRAM fit-check, deployment config generation.

---

## v0.5.0 — "Quickstart Layer" (Planlandı)

Odak: [Phase 11](phase-11-data-ingestion.md) + [Phase 12](phase-12-quickstart.md). Document ingestion + data audit + quickstart templates.

---

## v0.6.0-pro — "Pro CLI" (Planlandı, gated)

Odak: [Phase 13](phase-13-pro-cli.md). Traction doğrulamasına bağlı — `v0.5.0` için ≥1K aylık PyPI install + ≥2 ücretli destek sözleşmesi olmadan başlama.
