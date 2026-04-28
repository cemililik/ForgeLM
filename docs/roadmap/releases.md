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

## v0.3.1rc1 — "Security & Config Hardening" (2026-04-25)

**Status:** Folded into v0.4.0 (changes shipped as part of the v0.4.0 release; no standalone tag)

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

## v0.4.0 — "Post-Training Completion" (2026-04-26)

**Status:** Released — published to PyPI on 2026-04-26 ([release notes](https://github.com/cemililik/ForgeLM/releases/tag/v0.4.0)).

Odak: [Phase 10](phase-10-post-training.md). Full post-training handoff: inference, chat, GGUF export, VRAM fit-check, deployment config generation.

### Features:
1. [x] **`forgelm/inference.py`** — Shared generation primitives: `load_model`, `generate`, `generate_stream` (streaming via background thread, with timeout-based deadlock guard), `logit_stats`, `adaptive_sample`. Supports transformers + peft (merge-and-unload) + unsloth backends.
2. [x] **`forgelm chat`** — Interactive terminal REPL with streaming output, `/reset`, `/save` (system prompt persisted), `/temperature`, `/system` slash commands. Optional `rich` rendering with markup escape on token output. History capped at 50 turns.
3. [x] **`forgelm export`** — GGUF conversion via `llama-cpp-python`'s `convert_hf_to_gguf.py`. Supports adapter merge before conversion. K-quants (`q2_k`/`q3_k_m`/`q4_k_m`/`q5_k_m`) routed through an honest `.f16.gguf` intermediate (manifest SHA-256 always matches the file actually written); `q8_0` and `f16` are direct. SHA-256 appended to `model_integrity.json`. `pip install forgelm[export]`.
4. [x] **`forgelm --fit-check`** — Pre-flight VRAM estimator. Architecture via `AutoConfig` with word-bounded size-hint fallback. Formula: base weights + (LoRA adapter ⊕ GaLore projection — mutually exclusive) + optimizer state (AdamW/8bit/GaLore) + activations (gradient-checkpointing aware). Verdicts: FITS / TIGHT / OOM / UNKNOWN. `--output-format json` for CI/CD.
5. [x] **`forgelm deploy`** — Deployment config generator for 4 targets: `ollama` (Modelfile), `vllm` (YAML), `tgi` (docker-compose.yaml), `hf-endpoints` (JSON). Local-path validation rejects HF Hub IDs for `tgi`/`ollama` (would silently produce broken volumes). Does not run the server itself.
6. [x] **`pip install forgelm[export]`** — Optional `llama-cpp-python>=0.2.90` extra. `pip install forgelm[chat]` — Optional `rich>=13.0.0` extra.

### Notebooks:
- New: [`post_training_workflow.ipynb`](../../notebooks/post_training_workflow.ipynb) — end-to-end Phase 10 toolchain walkthrough.
- Updated: `quickstart_sft.ipynb` gets a "Next Steps" section pointing into the new toolchain.

---

## v0.4.5 — "Quickstart Layer" (2026-04-26)

**Status:** Released — published to PyPI on 2026-04-26 ([release notes](https://github.com/cemililik/ForgeLM/releases/tag/v0.4.5)). Focus: [Phase 10.5](phase-10-5-quickstart.md) (Quickstart). One-command bundled templates, sample datasets, opinionated defaults — primary community growth driver.

### Features:
1. [x] **`forgelm/quickstart.py`** — Template registry (`@dataclass(frozen=True) Template`), `auto_select_model()` GPU-aware downsizing (≥10 GB VRAM → primary model; otherwise fallback ≤2B), `run_quickstart()` end-to-end orchestrator that copies the bundled seed dataset, substitutes `model.name_or_path` and `data.dataset_name_or_path`, and writes a `configs/<template>-YYYYMMDDHHMMSS.yaml` the existing trainer accepts unchanged.
2. [x] **`forgelm quickstart <template>` CLI subcommand** — `--list` (text + JSON via `--output-format json`), `--model` / `--dataset` overrides, `--dry-run` (generate config but skip training), `--no-chat` (skip post-training chat REPL), `--output` (custom YAML path). On a successful train, subprocess-invokes `forgelm chat <output_dir>` for an immediate sanity loop. Top-level flags (`--output-format`, `--quiet`, `--log-level`, `--offline`) propagate to the train + chat subprocesses.
3. [x] **5 bundled templates** under [`forgelm/templates/`](../../forgelm/templates/):
   - `customer-support` (Qwen2.5-7B-Instruct ↔ SmolLM2-1.7B-Instruct, SFT, 58-example seed JSONL)
   - `code-assistant` (Qwen2.5-Coder-7B-Instruct ↔ Qwen2.5-Coder-1.5B-Instruct, SFT, 59-example seed)
   - `domain-expert` (Qwen2.5-7B-Instruct ↔ SmolLM2-1.7B-Instruct, BYOD — empty data, README walks through the workflow)
   - `medical-qa-tr` (Qwen2.5-7B-Instruct ↔ Qwen2.5-1.5B-Instruct, SFT, 49 Turkish Q&A with safety disclaimers)
   - `grpo-math` (Qwen2.5-Math-7B-Instruct ↔ Qwen2.5-Math-1.5B-Instruct, GRPO trainer, 40 grade-school math prompts each carrying a `gold_answer` for the built-in regex correctness reward)
4. [x] **Conservative defaults** — every template ships with QLoRA 4-bit NF4, rank=8, batch=1 + gradient accumulation, gradient checkpointing on, safety eval / compliance artifacts opt-in only.
5. [x] **GRPO baseline reward** — when `grpo_reward_model` is unset, `forgelm/grpo_rewards.combined_format_length_reward` (format-match × 0.8 + length-shaping × 0.2) is wired by default so prompt-only datasets don't crash inside `trl.GRPOTrainer`. If the dataset additionally carries a `gold_answer` field (the bundled grpo-math seed does), `_math_reward_fn` is appended for an additive correctness signal.
6. [x] **Wizard integration** — `forgelm --wizard` now opens with "Start from a template?". Yes → invokes the quickstart flow (BYOD path validates the supplied dataset path before continuing); No → falls through to the existing 8-step interactive flow. No bifurcation: same code paths, same YAML schema.
7. [x] **License hygiene** — [`forgelm/templates/LICENSES.md`](../../forgelm/templates/LICENSES.md) catalogs all bundled seed datasets (CC-BY-SA 4.0, author-original); contributing guide for new templates.
8. [x] **Tests + CI** — `tests/test_quickstart.py`, `tests/test_quickstart_hardening.py`, `tests/test_grpo_math_reward.py`, `tests/test_grpo_format_reward.py`, `tests/test_wizard_byod.py`, `tests/test_cli_quickstart_wiring.py`, `tests/test_packaging.py`. Includes a regression test that loads every generated YAML through `load_config` (the strongest guard against template drift). Nightly CI smoke-tests every template via `quickstart --dry-run` + `--config <out> --dry-run`, plus a dedicated `wheel-install-smoke` job that builds the wheel and reruns quickstart from a fresh venv to catch broken `package_data` globs.
9. [x] **`pyproject.toml` `[tool.setuptools.package-data]`** — bundles `*.yaml`, `*.jsonl`, `*.md` under `forgelm.templates` into the wheel so `pip install forgelm` users get the templates too.

---

## v0.5.0 — "Document Ingestion & Data Audit"

**Status:** Shipped (PR #11 merged to `main` 2026-04-27). Focus: [Phase 11](phase-11-data-ingestion.md). Bridges raw enterprise corpora to ForgeLM's training data format and surfaces governance signals before training.

### Features:

1. [x] **`forgelm/ingestion.py`** + **`forgelm ingest`** subcommand — Multi-format document → JSONL pipeline with `paragraph` (default) and `sliding` chunking strategies, recursive directory walk, optional `--pii-mask`. Supported extensions: `.pdf` (`pypdf`), `.docx` (`python-docx`), `.epub` (`ebooklib` + `beautifulsoup4`), `.txt`, `.md`. Output is `{"text": ...}` JSONL recognized by ForgeLM's data loader as pre-formatted SFT input — no further preprocessing needed. OCR is intentionally out of scope; scanned PDFs warn and produce zero chunks.

2. [x] **`forgelm/data_audit.py`** + **`forgelm --data-audit`** top-level flag — Per-split metrics (sample count, column schema, length distribution `min/max/mean/p50/p95`, top-3 language detection, null/empty rate), 64-bit simhash near-duplicate detection within each split, cross-split overlap report (catches train-test leakage), PII regex with Luhn-validated credit cards and TC Kimlik checksum-validated TR IDs. Layout: single `.jsonl` → treated as `train`; directory → split-keyed (`train.jsonl` / `validation.jsonl` / `test.jsonl`) auto-discovered. Writes `data_audit_report.json` to `--output` (default `./audit/`); `--output-format json` mirrors the report on stdout for CI/CD. CPU-only, no network.

3. [x] **EU AI Act Article 10 integration** — `generate_data_governance_report` now inlines `data_audit_report.json` under the `data_audit` key when present in the trainer's `output_dir`. Compliance bundle becomes a single self-contained document.

4. [x] **`pyproject.toml` `[ingestion]` extra** — `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, `langdetect`. Cross-platform; no native compilation. Plain TXT / Markdown ingestion + the audit module work without installing the extra (PII regex, simhash, length stats are pure stdlib).

5. [x] **Tests + docs** — `tests/test_ingestion.py` and `tests/test_data_audit.py` (54 tests; PDF round-trip skips when `pypdf` missing). New guides: [`docs/guides/ingestion.md`](../guides/ingestion.md), [`docs/guides/data_audit.md`](../guides/data_audit.md). README feature section, install matrix, and roadmap status updated.

---

## v0.5.1 — "Ingestion / Audit Polish"

**Status:** Merged on `main` (carried in via Phase 11/12 PRs). The `v0.5.1` git tag and PyPI publish are the remaining release-engineering steps. Focus: [Phase 11.5](phase-11-5-backlog.md). Operational polish on top of `v0.5.0`'s ingestion + audit surface — no new training capabilities, but materially better handling for large corpora and a cleaner CLI shape.

### Features:

1. [x] **`forgelm audit` subcommand** — Promotes the `--data-audit` top-level flag to a first-class subcommand with its own `--output` default. The flag is preserved as a deprecation alias; existing pipelines keep working.
2. [x] **LSH-banded near-duplicate detection** — Replaces the `O(n²)` pair scan inside each split (and across splits) with locality-sensitive-hashing bands (4 × 16-bit on the 64-bit fingerprint, hash-bucket lookup). Drops average-case to `O(n × k)` and unblocks audits on 100K+ row corpora.
3. [x] **Streaming `_read_jsonl_split`** — The audit's JSONL reader now yields rows lazily and the per-split aggregator stays generator-based until simhash collection. Bounds memory on multi-million-row splits.
4. [x] **Token-aware `--chunk-tokens`** — Optional ingestion flag that sizes chunks against an HF tokenizer instead of raw character counts. Removes a class of "my chunks blew through `max_length`" surprises.
5. [x] **PDF page-level header / footer dedup** — Repeated page headers (company watermark, page number) used to inflate near-duplicate counts; common-prefix / common-suffix detection across pages now strips them.
6. [x] **PII severity tiers** — Audit output adds a `pii_severity` block grading each PII type as `low / medium / high / critical` (e.g. `credit_card` → critical, `phone` → low) so compliance reviewers get a one-glance verdict.
7. [x] **`summarize_report` truncation policy** — Multi-split summaries get a `verbose=False` default that suppresses zero-finding splits. Operators see issues, not 100 lines of "all clean" rows.
8. [x] **Structured ingestion notes** — `IngestionResult.extra_notes` keeps the human-readable list but gains a parallel `notes_structured: {key: value}` map (e.g. `{"skipped_files": 3, "pii_redactions": {...}}`) for programmatic consumers.
9. [x] **Wizard "ingest first" entry point** — A first-class wizard option ("I have raw documents") routes to `forgelm ingest`, surfaces a JSONL path, and folds it back into the BYOD prompt — closing the onboarding loop end-to-end.
10. [x] **xxhash backend for simhash + token-level memo** — Drop-in faster non-crypto digest path (BLAKE2b kept as fallback for sites that can't add the optional dep). Token-level `lru_cache` memoizes repeat tokens (the/and/etc.) for a 2–5× speedup on long corpora.
11. [x] **Atomic audit report write** — `data_audit_report.json` is written via `tempfile.NamedTemporaryFile` + atomic rename so a crashed audit never leaves a half-written report on disk.

---

## v0.5.2 — "Data Curation Maturity"

**Status:** Tier 1 merged on `main` via PR #13 (2026-04-29). The `v0.5.2` git tag and PyPI publish are the remaining release-engineering steps. One hardening follow-up tracked outside the release: [#14 — webhook SSRF DNS-rebinding TOCTOU](https://github.com/cemililik/ForgeLM/issues/14) (defence-in-depth on top of the existing `allow_private_destinations: false` default). Focus: [Phase 12](phase-12-data-curation-maturity.md). Direct continuation of the Phase 11/11.5 ingestion + audit lineage — closes the four gaps surfaced by the post-`v0.5.1` competitive review (LLaMA-Factory / Axolotl / Unsloth / NeMo Curator / Dolma / RedPajama / LlamaIndex / LangChain / Marker / Docling).

### Tier 1 features (shipped):

1. [x] **MinHash LSH dedup option** — Opt-in `--dedup-method minhash --jaccard-threshold 0.85` route via `datasketch` (`[ingestion-scale]` extra) for >50K-row corpora. Default simhash + LSH banding stays untouched.
2. [x] **Markdown-aware splitter** — New `--strategy markdown` preserves heading hierarchy (`# H1` / `## H2`), code-block boundaries, and inlines a heading breadcrumb so SFT loss sees document context.
3. [x] **Code / secrets leakage tagger** — New `secrets_summary` block in audit JSON (AWS / GitHub / Slack / OpenAI / Google / JWT / OpenSSH / PGP / Azure storage). Ingest gains `--secrets-mask` (mask order: secrets → PII so combined detectors don't double-count). `[ingestion-secrets]` extra (`detect-secrets`); regex-only fallback when missing.
4. [x] **Heuristic quality filter** — Opt-in `--quality-filter` adds a `quality_summary` block with Gopher / C4 / RefinedWeb-style heuristics (mean-word-length, alphabetic ratio, end-of-line punctuation, short-paragraph ratio). ML classifiers stay deferred to Phase 13+.
5. [x] **DOCX / Markdown table preservation** — `_extract_docx` emits markdown table syntax (header + separator + body rows) instead of the previous `" | "` flat join; uneven rows padded; all-blank rows trimmed; the new markdown chunker keeps these blocks intact across chunks.

### Tier 2/3 (deferred to [Phase 12.5 backlog](phase-12-5-backlog.md)):

- Presidio adapter (`--pii-engine presidio` + `[ingestion-pii-ml]` extra).
- Croissant metadata compatibility (audit JSON `--croissant` flag).
- `forgelm ingest --all-mask` composite flag.
- Wizard "audit first" entry point (mirrors Phase 11.5's ingest-first hook).

---

## v0.5.3 — "Pipeline Chains" (Planned)

**Status:** Planned. Focus: [Phase 14](phase-14-pipeline-chains.md). Multi-stage SFT → DPO → GRPO chained config, pipeline provenance artifacts for EU AI Act Annex IV compliance. Reslotted from `v0.5.2` so the ingestion / audit lineage finishes uninterrupted; no hard blockers, starts after the `v0.5.2` PyPI tag is published. Folds in [#14 webhook SSRF hardening](https://github.com/cemililik/ForgeLM/issues/14) (defence-in-depth on top of the existing `allow_private_destinations: false` default).

---

## v0.6.0-pro — "Pro CLI" (Planned, gated)

Focus: [Phase 13](phase-13-pro-cli.md). Gated on traction validation — do not ship before `v0.5.0` reaches ≥1K monthly PyPI installs and ≥2 paying support contracts.
