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

## v0.5.0 — "Document Ingestion + Data Curation Pipeline"

**Status:** Merged on `main` (Phases 11 + 11.5 + 12 + 12.5 consolidated; 2026-04-29). The `v0.5.0` git tag and PyPI publish are the remaining release-engineering steps. One hardening follow-up tracked outside the release: [#14 — webhook SSRF DNS-rebinding TOCTOU](https://github.com/cemililik/ForgeLM/issues/14) (defence-in-depth on top of the existing `allow_private_destinations: false` default).

> **Note on consolidation.** Originally planned as four sequential PyPI tags (`v0.5.0` / `v0.5.1` / `v0.5.2` / `v0.5.3`), the four phases were consolidated into a single `v0.5.0` because they form one coherent surface (ingest → polish → mature → polish) hard to use in parts. Git history retains the four phases as separate commit batches; this entry collapses them into one user-facing release. CHANGELOG.md preserves the phase boundaries inside the `[0.5.0]` section so reviewers can map back to PR history (#11, #12, #13, #18).

### Phase 11 — Document Ingestion & Data Audit

1. [x] **`forgelm/ingestion.py` + `forgelm ingest` subcommand** — Multi-format document → JSONL pipeline with `paragraph` (default) and `sliding` chunking strategies, recursive directory walk, optional `--pii-mask`. Supported extensions: `.pdf` (`pypdf`), `.docx` (`python-docx`), `.epub` (`ebooklib` + `beautifulsoup4`), `.txt`, `.md`. Output is `{"text": ...}` JSONL recognised by ForgeLM's data loader as pre-formatted SFT input. OCR is intentionally out of scope; scanned PDFs warn and produce zero chunks.
2. [x] **`forgelm/data_audit.py` + `forgelm --data-audit` flag** — Per-split metrics (sample count, column schema, length distribution `min/max/mean/p50/p95`, top-3 language detection, null/empty rate), 64-bit simhash near-duplicate detection within each split, cross-split overlap report (catches train-test leakage), PII regex with Luhn-validated credit cards and TC Kimlik checksum-validated TR IDs. CPU-only, no network.
3. [x] **EU AI Act Article 10 integration** — `generate_data_governance_report` inlines `data_audit_report.json` under the `data_audit` key when present in the trainer's `output_dir`.
4. [x] **`pyproject.toml` `[ingestion]` extra** — `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, `langdetect`. Cross-platform; no native compilation.

### Phase 11.5 — Ingestion / Audit Polish

1. [x] **`forgelm audit` subcommand** — promotes the `--data-audit` flag to a first-class subcommand. Flag preserved as a deprecation alias.
2. [x] **LSH-banded near-duplicate detection** — replaces the `O(n²)` pair scan with locality-sensitive-hashing bands; drops average-case to `O(n × k)` and unblocks 100K+ row corpora.
3. [x] **Streaming `_read_jsonl_split`** — JSONL reader yields rows lazily; per-split aggregator stays generator-based until simhash collection.
4. [x] **Token-aware `--chunk-tokens`** — sizes chunks against an HF tokenizer instead of raw character counts.
5. [x] **PDF page-level header / footer dedup** — repeated page headers (company watermark, page number) stripped automatically.
6. [x] **PII severity tiers** — `pii_severity` block grades each PII type as `low / medium / high / critical` + worst-tier verdict.
7. [x] **`summarize_report` truncation policy** — multi-split summaries default to `verbose=False`.
8. [x] **Structured ingestion notes** — parallel `notes_structured: {key: value}` map for programmatic consumers.
9. [x] **Wizard "ingest first" entry point** — first-class wizard option that routes to `forgelm ingest`.
10. [x] **xxhash backend + token-level memo** — drop-in faster non-crypto digest path; `lru_cache`-memoised repeat tokens for 2–5× speedup.
11. [x] **Atomic audit report write** — tempfile + atomic rename.

### Phase 12 — Data Curation Maturity (Tier 1)

1. [x] **MinHash LSH dedup option** — opt-in `--dedup-method minhash --jaccard-threshold 0.85` via `datasketch` (`[ingestion-scale]` extra). Default simhash + LSH banding stays untouched.
2. [x] **Markdown-aware splitter** — `--strategy markdown` preserves heading hierarchy (`# H1` / `## H2`), keeps fenced code blocks atomic, and inlines a heading breadcrumb so SFT loss sees document context.
3. [x] **Code / secrets leakage tagger** — new `secrets_summary` block in audit JSON (nine families per `forgelm.data_audit.SECRET_TYPES`). Ingest gains `--secrets-mask` (mask order: secrets → PII).
4. [x] **Heuristic quality filter** — opt-in `--quality-filter` adds a `quality_summary` block with Gopher / C4 / RefinedWeb-style heuristics.
5. [x] **DOCX / Markdown table preservation** — `_extract_docx` emits markdown table syntax instead of the previous `" | "` flat join.

### Phase 12.5 — Data Curation Polish (backlog items #1–#4)

1. [x] **Presidio adapter (item #1)** — `forgelm audit --pii-ml [--pii-ml-language LANG]` layers Presidio NER on top of the regex detector via the optional `[ingestion-pii-ml]` extra. Adds `person` / `organization` / `location` categories. Pre-flight check covers BOTH the missing-extra branch AND the missing-spaCy-model branch (`presidio-analyzer` does NOT transitively ship `en_core_web_lg`; the install recipe is two lines, raised as `ImportError` before any rows are scanned).
2. [x] **Croissant 1.0 metadata (item #2)** — `forgelm audit --croissant` populates a new `croissant` key in `data_audit_report.json` with a Google Croissant 1.0 dataset card. Card carries `cr:FileObject` per JSONL split, `cr:RecordSet` per split with `cr:Field` entries from column detection. Conformant with `mlcommons.org/croissant/1.0`.
3. [x] **`forgelm ingest --all-mask` (item #3)** — one-flag shorthand for `--secrets-mask --pii-mask` in the documented order. Set-union with explicit flags.
4. [x] **Wizard "audit first" (item #4)** — when the wizard resolves a JSONL (typed or produced by ingest), it offers to run `forgelm audit` inline and prints the verdict. Closes the BYOD audit loop.

### Hardening follow-up (tracked outside this release)

- [#14 — webhook SSRF DNS-rebinding TOCTOU](https://github.com/cemililik/ForgeLM/issues/14): defence-in-depth on top of the existing `allow_private_destinations: false` default. Slated for `v0.5.1`.

---

## v0.5.1 — "Pipeline Chains" (Planned)

**Status:** Planned. Focus: [Phase 14](phase-14-pipeline-chains.md). Multi-stage SFT → DPO → GRPO chained config, pipeline provenance artifacts for EU AI Act Annex IV compliance. Starts after the `v0.5.0` PyPI tag is published. Folds in [#14 webhook SSRF hardening](https://github.com/cemililik/ForgeLM/issues/14) (defence-in-depth on top of the existing `allow_private_destinations: false` default).

---

## v0.6.0-pro — "Pro CLI" (Planned, gated)

Focus: [Phase 13](phase-13-pro-cli.md). Gated on traction validation — do not ship before `v0.5.0` reaches ≥1K monthly PyPI installs and ≥2 paying support contracts.
