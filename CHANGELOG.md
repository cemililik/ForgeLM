# Changelog

All notable changes to ForgeLM are documented here.

## [Unreleased]

### Added — Phase 11.5 (Ingestion / Audit Polish, targeting v0.5.1)

Operational polish on top of `v0.5.0`'s ingestion + audit surface — no new training capabilities, but materially better handling for large corpora and a cleaner CLI shape. All 12 follow-ups carved out of Phase 11's review backlog.

- **`forgelm audit PATH` subcommand** — Promotes the `--data-audit` top-level flag to a first-class subcommand with `--verbose`, `--near-dup-threshold`, and its own `--output` default (`./audit/`). The legacy `forgelm --data-audit PATH` flag keeps working as a deprecation alias and logs a one-line notice; existing CI pipelines need no changes. Removal targeted no earlier than `v0.7.0`.
- **LSH-banded near-duplicate detection** (`find_near_duplicates`, `_count_leaked_rows`) — Pigeonhole-banded LSH (default `bands = threshold + 1`) drops within-split + cross-split scans from `O(n²)` to ~`O(n × k)`. Recall stays exact at the default Hamming threshold; brute-force fallback remains for edge thresholds where bands shrink below 4 bits. Unblocks audits on 100K+ row corpora.
- **Streaming `_read_jsonl_split`** — The audit's JSONL reader is now a generator yielding `(row, parse_err, decode_err)`; `_audit_split` consumes it row-by-row via a `_StreamingAggregator` so RAM stays bounded on multi-million-row splits. Per-line tolerance semantics (parse errors, decode errors, non-dict rows) preserved.
- **Token-aware ingestion** (`--chunk-tokens`, `--tokenizer`, `--overlap-tokens`) — Optional flags on `forgelm ingest` size chunks against an HF `AutoTokenizer.encode` instead of raw character counts, so chunks line up with `model.max_length` exactly. `--tokenizer` is required with `--chunk-tokens` (we refuse to default to a hidden vocab because the chunk count would silently differ per-model). `trust_remote_code=False` is hard-pinned for safety.
- **PDF page-level header / footer dedup** (`_strip_repeating_page_lines`) — Lines that recur as the first or last non-empty line on ≥ 70 % of a PDF's pages (company watermarks, page numbers, copyright lines) are stripped automatically before chunking. Reduces audit `near_duplicate_pairs` noise on long policy / book PDFs. Skipped on documents shorter than 3 pages.
- **PII severity tiers** — Audit JSON now carries a `pii_severity` block (`total`, `by_tier`, `by_type`, `worst_tier`) alongside the flat `pii_summary`. Tiers map regulatory weighting: `credit_card` / `iban` → critical (PCI-DSS), national IDs → high (GDPR Art. 9), `email` → medium, `phone` → low. The aggregate notes line leads with the worst tier (`WORST tier: CRITICAL`) so reviewers cannot miss it.
- **`summarize_report` truncation policy** — Default `verbose=False` folds zero-finding splits into a single tail line so multi-split summaries stay short; `--verbose` on the new `audit` subcommand reverses this for full output. Has no effect on the on-disk JSON report.
- **Structured ingestion notes** — `IngestionResult.extra_notes` keeps the human-readable list; new `notes_structured: {key: value}` (and an explicit `pdf_header_footer_lines_stripped` field) carries machine-readable counts for CI/CD consumers. JSON output exposes both.
- **Wizard "ingest first" entry point** — `_offer_ingest_for_directory` + `_prompt_dataset_path_with_ingest_offer`: BYOD quickstart and the full 8-step wizard now offer to run `forgelm ingest` inline when the typed dataset path is a directory of raw documents, then feed the produced JSONL straight back into the BYOD path. Closes the onboarding loop end-to-end.
- **xxhash backend for simhash + token-level memo** — Optional `xxhash.xxh3_64` digest path (added to `forgelm[ingestion]`); BLAKE2b stays as the fallback. The Python-level speedup is modest (~1.3× raw, ~1.05× end-to-end after the cache below absorbs Zipfian repeats — xxhash's "4-10×" figure refers to C-level pure-hash microbenchmarks, not the Python wrapping path). The bigger wall-clock win is the new module-scope `lru_cache(maxsize=10_000)` that memoises the per-token digest — most corpora's token traffic is dominated by a few thousand frequent tokens, so the cache hit rate is very high.
- **Atomic audit-report write** — `data_audit_report.json` is now written via `tempfile.NamedTemporaryFile` + `os.replace` so a crashed audit can never leave a half-written report on disk. `newline="\n"` pinned for byte-exact reproducibility across Windows / Linux / macOS.

### Tests

- `tests/test_data_audit.py` — `TestLshBandedNearDuplicates` (LSH parity vs. brute force + high-threshold fallback), `TestPiiSeverity` (critical-tier verdict + neutral case), `TestSummarizeVerbosePolicy` (clean splits folded vs. expanded), `TestAtomicWrite` (no `.tmp` leftovers), `TestStreamingReader` (per-line tuple yields), `TestTokenCachePerformance` (cross-text cache hits).
- `tests/test_ingestion.py` — `TestPdfHeaderFooterDedup` (multi-page header/footer collapse, short-doc skip, no-repeats pass-through), `TestStructuredIngestionNotes`, `TestTokenAwareCli` (validates the `--chunk-tokens` requires `--tokenizer` rule).
- `tests/test_cli_subcommands.py` — `TestAuditSubcommand` (subcommand happy path, JSON envelope, legacy `--data-audit` alias).
- `tests/test_wizard_byod.py` — refreshed for the new ingest-first wording (empty directory rejection, decline-the-ingest-offer path).

### Changed — Phase 11 (no behavioural delta unless noted)

- `AuditReport` gains a `pii_severity: Dict[str, Any]` field. JSON consumers reading only `pii_summary` continue to work; the new field is additive.
- `find_near_duplicates(fingerprints, *, threshold, bits=64)` accepts a `bits` keyword for adaptive banding (default 64 matches `compute_simhash`).
- `_read_jsonl_split` is now a generator. The legacy buffered tuple return is gone — callers that were materialising rows can wrap with `list(...)`.
- `_audit_split(split_name, path, ...)` now takes a path instead of an in-memory list; `_process_split` calls it directly. Returns `(info, fingerprints, pii_split, parse_errors, decode_errors)` so OSError handling stays in the orchestrator.

### Previously added — Phase 11

**Document Ingestion & Data Audit (Phase 11)** — bridges raw enterprise corpora (legal, medical, policy manuals) to ForgeLM's training data format and surfaces governance signals before training starts.

- **`forgelm/ingestion.py`** + **`forgelm ingest`** subcommand:
  - Multi-format extractors: PDF (`pypdf`), DOCX (`python-docx`), EPUB (`ebooklib` + `beautifulsoup4`), TXT, Markdown.
  - Two chunking strategies: `paragraph` (default; greedy, never splits a paragraph) and `sliding` (fixed window with `--overlap`). `semantic` raises `NotImplementedError` and is reserved for a follow-up phase.
  - Output is `{"text": "..."}` JSONL — recognized as pre-formatted SFT input by `forgelm/data.py` without further preprocessing.
  - `--recursive` walks directory trees; unsupported extensions are skipped silently, supported files with no extractable text skip with a warning.
  - `--pii-mask` redacts detected PII spans before chunks land in the JSONL (shared regex set with the audit module).
  - OCR is intentionally out of scope; scanned PDFs without a text layer warn and produce zero chunks.

- **`forgelm/data_audit.py`** + **`forgelm --data-audit`** top-level flag:
  - Per-split metrics: sample count, column schema, text length distribution (`min/max/mean/p50/p95`), null/empty rate, top-3 language detection (best-effort via `langdetect`).
  - 64-bit simhash near-duplicate detection within each split; Hamming-distance threshold 3 ≈ 95% similarity (canonical web-page-dedup setting).
  - Cross-split overlap report — guards against silent train-test leakage that destroys benchmark fidelity.
  - PII regex set (`email`, `phone`, `credit_card` Luhn-validated, `iban`, `tr_id` checksum-validated, `de_id`, `fr_ssn`, `us_ssn`); per-split + aggregate counts.
  - Layout: single `.jsonl` file → treated as `train`; directory containing `train.jsonl` / `validation.jsonl` / `test.jsonl` (any subset) auto-discovered.
  - Writes `data_audit_report.json` under `--output` (default `./audit/`); `--output-format json` mirrors the report on stdout for CI/CD pipelines.
  - CPU-only; no GPU, no network.

- **EU AI Act Article 10 integration** — `generate_data_governance_report` now inlines `data_audit_report.json` under the `data_audit` key when present in the trainer's `output_dir`. Compliance bundle becomes a single self-contained document instead of a pointer.

- **`pyproject.toml` `[ingestion]` extra** — `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, `langdetect`. Cross-platform, no native compilation.

- **Tests** — `tests/test_ingestion.py` (TXT path + chunking strategies; PDF round-trip skips when `pypdf` missing) and `tests/test_data_audit.py` (PII regex + Luhn / TC Kimlik validators, simhash properties, end-to-end audit on file + split-keyed directory layouts, governance integration). All GPU/network-free.

- **Documentation** — new guides at `docs/guides/ingestion.md` and `docs/guides/data_audit.md`; README feature section, CLI epilog, install matrix, and roadmap status updated.

---

## [0.4.5] — 2026-04-26

### Added

**Quickstart Layer (Phase 10.5)** — One-command bundled templates with opinionated defaults. Primary community-growth driver: closes the gap between "I just installed ForgeLM" and "I have a fine-tuned model running locally."

- **`forgelm/quickstart.py`** — Template registry + orchestrator:
  - `Template` (frozen dataclass) — `name`, `title`, `description`, `primary_model`, `fallback_model`, `trainer_type`, `estimated_minutes`, `min_vram_for_primary_gb`, `bundled_dataset`, `license_note`.
  - `TEMPLATES: Dict[str, Template]` — 5 entries: `customer-support`, `code-assistant`, `domain-expert`, `medical-qa-tr`, `grpo-math`.
  - `auto_select_model(template, available_vram_gb)` — picks primary model when VRAM ≥ threshold (10–12 GB), fallback otherwise; explicit `no-gpu-detected` reason when CUDA is absent.
  - `_detect_available_vram_gb()` — wraps `torch.cuda.mem_get_info()`; returns `None` when no GPU (test mock point).
  - `run_quickstart(template_name, *, model_override, dataset_override, output_path, dry_run, available_vram_gb)` → `QuickstartResult` — copies seed dataset, substitutes `model.name_or_path` and `data.dataset_name_or_path`, writes `configs/<template>-YYYYMMDDHHMMSS.yaml`. Generated YAML is identical in shape to a hand-written one — same trainer, same schema.
  - `format_template_list()`, `summarize_result(result)` — text/JSON renderers for CLI use.

- **`forgelm quickstart <template>` CLI subcommand** (in `forgelm/cli.py`):
  - `--list` — prints the registry; honors top-level `--output-format json` for CI.
  - `--model <id>` — override auto-selected model.
  - `--dataset <path>` — override the bundled seed dataset (required for `domain-expert`).
  - `--output <path>` — custom YAML output path (default: `./configs/<template>-<timestamp>.yaml`).
  - `--dry-run` — generate config only; skip training and chat.
  - `--no-chat` — train but skip the post-training chat REPL.
  - On a successful run, subprocess-invokes `forgelm --config <out>` and then `forgelm chat <output_dir>` (unless `--no-chat`).

- **Wizard integration** — `forgelm --wizard` now opens with "Start from a template?":
  - Yes → routes to the quickstart selector; the wizard becomes a thin shell over `run_quickstart()`.
  - No → falls through to the existing 8-step interactive flow.
  - No bifurcation: identical code paths and YAML schema downstream.

- **5 bundled templates** under `forgelm/templates/`:
  - `customer-support/` — Qwen2.5-7B-Instruct primary, SmolLM2-1.7B-Instruct fallback. SFT trainer. 58-example seed JSONL in `{"messages": [...]}` format.
  - `code-assistant/` — Qwen2.5-Coder-7B-Instruct primary, Qwen2.5-Coder-1.5B-Instruct fallback (code-tuned smaller variant, not generic SmolLM2). SFT. 59-example Python/programming Q&A.
  - `domain-expert/` — Qwen2.5-7B-Instruct primary, SmolLM2-1.7B-Instruct fallback. BYOD; empty data with a README explaining how to pair with `forgelm ingest` (Phase 11) or a custom JSONL.
  - `medical-qa-tr/` — Qwen2.5-7B-Instruct primary, Qwen2.5-1.5B-Instruct fallback (Turkish-capable, not English-only SmolLM2). SFT, 49 Turkish Q&A; every answer ends with "Tıbbi acil durumlarda 112'yi arayın..." (medical-disclaimer guardrail).
  - `grpo-math/` — Qwen2.5-Math-7B-Instruct primary, Qwen2.5-Math-1.5B-Instruct fallback. GRPO trainer (`grpo_num_generations: 4`). 40 grade-school math word problems in prompt-only format, each carrying a `gold_answer` field for the built-in regex correctness reward.

- **Conservative defaults** in every template config:
  - QLoRA 4-bit NF4, LoRA rank=8, `per_device_train_batch_size=1`, gradient checkpointing on, safety eval / compliance artifacts opt-in only.
  - Designed so the smallest fallback model + the bundled seed dataset run end-to-end on a 12 GB consumer GPU.

- **`forgelm/templates/LICENSES.md`** — Full attribution for bundled seed datasets (CC-BY-SA 4.0, author-original); contributing guide for new templates; medical-disclaimer note for `medical-qa-tr`.

- **`pyproject.toml` `[tool.setuptools.package-data]`** — bundles `*.yaml`, `*.jsonl`, `*.md` under `forgelm.templates` into the wheel so `pip install forgelm` users get the templates without a source checkout.

- **GRPO baseline reward** — `forgelm/grpo_rewards.py` ships a default reward bundle so prompt-only datasets don't crash inside `trl.GRPOTrainer`. When `grpo_reward_model` is unset the trainer wires `combined_format_length_reward` (0.8 × format-match + 0.2 × length-shaping); if the dataset additionally carries a `gold_answer` field (the bundled `grpo-math` seed does), `_math_reward_fn` is appended so TRL sums correctness on top of format teaching.

- **Tests** — All GPU-independent via TRL/torch FSDP-aware skip-if pattern:
  - `tests/test_quickstart.py` — registry consistency, bundled-asset shape, `auto_select_model` primary/fallback/no-gpu, end-to-end `run_quickstart`, CLI dispatch, regression test that loads every generated YAML through `load_config` (strongest guard against template drift).
  - `tests/test_quickstart_hardening.py` — PR review hardening (path validation, model override edges, dry-run wiring).
  - `tests/test_grpo_math_reward.py` — pure-Python unit tests for `_normalize_answer`, `_answers_match`, `_math_reward_fn`, `_dataset_has_gold_answers`.
  - `tests/test_grpo_format_reward.py` — `format_match_reward`, `length_shaping_reward`, `combined_format_length_reward`, plus trainer integration.
  - `tests/test_wizard_byod.py` — wizard BYOD dataset path validation (existence, directory, malformed JSONL, valid JSONL, HF Hub IDs, `~` expansion).
  - `tests/test_cli_quickstart_wiring.py` — `--offline` propagation, separate chat inheritance, chat exit-code 0/130 handling.
  - `tests/test_packaging.py` — wheel `package_data` smoke (catches editable-install-only template paths).
  - `tests/test_grpo_reward.py` — extended with no-reward-model + gold-answer wiring assertions.

- **CI** — `.github/workflows/nightly.yml`:
  - Per-template quickstart smoke (4 of 5 — `domain-expert` is BYOD and covered by pytest).
  - New `wheel-install-smoke` job: builds the wheel, installs it into a fresh venv from `/tmp` (so the source tree is off `sys.path`), and reruns `quickstart --list` + `quickstart --dry-run` to catch broken `package_data` globs that editable installs hide.

### Documentation

- New "Option 0: One-Command Quickstart Template" section at the top of `docs/guides/quickstart.md`.
- `docs/roadmap.md`, `docs/roadmap-tr.md`, `docs/roadmap/phase-10-5-quickstart.md`, `docs/roadmap/releases.md` updated to mark Phase 10.5 as Done.
- `README.md` quickstart section updated to lead with `forgelm quickstart`.

---

## [0.4.0] — 2026-04-26

### Added

**Post-Training Completion (Phase 10)**

- **`forgelm/inference.py`** — Shared generation primitives for all post-training features:
  - `load_model(path, adapter, backend, load_in_4bit, load_in_8bit, trust_remote_code)` — loads HF model + tokenizer; optional PEFT adapter merge via `merge_and_unload()`; unsloth backend support
  - `generate(model, tokenizer, prompt, *, messages, system_prompt, history, max_new_tokens, temperature, top_k, top_p, repetition_penalty)` — non-streaming text generation
  - `generate_stream(...)` — streaming via `TextIteratorStreamer` in daemon thread; yields token chunks
  - `logit_stats(logits)` — returns `{entropy, top1_prob, effective_vocab}` for token-level confidence inspection
  - `adaptive_sample(logits, temperature, top_k, top_p, entropy_threshold)` — greedy below entropy threshold, nucleus sampling above
  - `_build_prompt` — uses `tokenizer.apply_chat_template` when available; falls back to `"role: content\n"` join

- **`forgelm/chat.py`** — Interactive terminal REPL (`ChatSession` class + `run_chat()` entry point):
  - Streaming output by default; `--no-stream` flag for non-streaming
  - Slash commands: `/reset`, `/save [file]`, `/temperature N`, `/system [prompt]`, `/help`, `/exit`
  - History management with 50-turn cap (`_MAX_HISTORY_PAIRS`)
  - Optional `rich` rendering via `pip install forgelm[chat]`
  - Optional `--safety` flag routes each response through Llama Guard

- **`forgelm/fit_check.py`** — VRAM pre-flight advisor:
  - `estimate_vram(config)` → `FitCheckResult(verdict, estimated_gb, available_gb, breakdown, recommendations)`
  - Verdicts: `FITS` (< 85% GPU), `TIGHT` (85-95%), `OOM` (> 95%), `UNKNOWN` (no GPU)
  - Architecture loaded via `transformers.AutoConfig`; fallback size-hint dict for 7b/8b/13b/70b families
  - VRAM components: base weights + LoRA adapter + optimizer state (AdamW/8-bit/GaLore-aware) + activations (gradient-checkpointing divides by √layers)
  - `format_fit_check(result)` — human-readable summary; `--output-format json` for CI/CD
  - Hypothetical mode when no CUDA detected — still estimates based on architecture

- **`forgelm/export.py`** — GGUF model export:
  - `export_model(model_path, output_path, *, format, quant, adapter, update_integrity, extra_args)` → `ExportResult`
  - Wraps `llama-cpp-python`'s `convert_hf_to_gguf.py` — no reimplementation of conversion logic
  - Supported quantizations: `q2_k`, `q3_k_m`, `q4_k_m`, `q5_k_m`, `q8_0`, `f16`
  - **K-quant note**: `q2_k`/`q3_k_m`/`q4_k_m`/`q5_k_m` require a two-step flow.
    `forgelm export ... --quant q4_k_m model.gguf` produces an intermediate
    `model.f16.gguf`; run `llama-quantize model.f16.gguf model.gguf Q4_K_M`
    afterward to obtain the K-quant. The `ExportResult.quant` field reflects
    what was actually written (so `model_integrity.json` SHA-256 stays honest)
  - Adapter merge: loads base + PEFT, saves merged fp16 weights before conversion
  - `_sha256_file` — chunked 64 KB reads for large models
  - `_update_integrity_manifest` — appends export artifact (path, quant, sha256, size_bytes) to `model_integrity.json`
  - Optional dependency: `pip install forgelm[export]` (`llama-cpp-python>=0.2.90`)

- **`forgelm/deploy.py`** — Deployment config file generation:
  - `generate_deploy_config(model_path, target, output_path, *, system_prompt, max_length, temperature, top_k, top_p, ...)` → `DeployResult`
  - Target `ollama`: Modelfile with FROM, SYSTEM (double-quote escaped), PARAMETER directives
  - Target `vllm`: YAML engine config with GPU memory utilization, dtype, trust_remote_code
  - Target `tgi`: docker-compose.yaml with GPU resource reservation, port mapping, max-input/total-length
  - Target `hf-endpoints`: JSON spec with model repository, task, compute instance, region, framework
  - Case-insensitive target matching; default output filenames per target

- **CLI subcommands** (`forgelm/cli.py`):
  - `forgelm chat MODEL_PATH [--adapter] [--system] [--temperature] [--max-new-tokens] [--safety] [--no-stream] [--load-in-4bit] [--load-in-8bit] [--trust-remote-code] [--backend]`
  - `forgelm export MODEL_PATH --output FILE [--format gguf] [--quant q4_k_m] [--adapter] [--no-integrity-update]`
  - `forgelm deploy MODEL_PATH --target TARGET [--output FILE] [--system] [--max-length] [--temperature] [--top-k] [--top-p] [--trust-remote-code]`
  - `forgelm --config CONFIG --fit-check [--output-format json]`
  - All subcommands work without `--config`; backward-compatible with existing flat CLI

- **Optional extras** in `pyproject.toml`:
  - `forgelm[export]` — `llama-cpp-python>=0.2.90` (non-Windows)
  - `forgelm[chat]` — `rich>=13.0.0`

- **New test modules**:
  - `tests/test_inference.py` — 16 tests covering `_build_prompt`, `_to_messages`, `logit_stats`, `adaptive_sample`, `load_model`, `generate` with custom torch stub (no GPU required)
  - `tests/test_fit_check.py` — 18 tests covering parameter estimation, VRAM components, GPU scenarios (no CUDA, 4 GB, 80 GB), `format_fit_check`
  - `tests/test_export.py` — 12 tests covering SHA-256, integrity manifest, GGUF export flow with subprocess mock
  - `tests/test_deploy.py` — 21 tests covering all 4 target generators and `generate_deploy_config` integration
  - `tests/test_cli_phase10.py` — 22 tests covering `--fit-check`, all deploy targets, export subcommand, chat subcommand, subcommand routing

### Changed

- **`forgelm/__init__.py`** — version bumped to `0.4.0`
- **`forgelm/cli.py`** — added subparser architecture with `chat`, `export`, `deploy` subcommands; added `--fit-check` flag; `KeyboardInterrupt` caught in chat dispatch for graceful exit
- **`forgelm/wizard.py`** — (no changes needed; Phase 10 features are all CLI-driven, not wizard-driven)

### Breaking

- **`forgelm.compliance.export_compliance_artifacts`** signature changed from
  `(manifest, config, output_dir)` to `(manifest, output_dir)`. The `config`
  argument was unused (the manifest already contains all derived values).
  External callers must drop the second positional argument.
- **`forgelm.export.export_model`** keyword `format=` renamed to
  `output_format=` to avoid shadowing the `format` builtin. Update
  `export_model(..., format="gguf", ...)` → `export_model(...,
  output_format="gguf", ...)`.
- **`forgelm.deploy.generate_deploy_config`** parameter list collapsed from
  18 → 11 args. The HF Endpoints fields (task/instance_size/instance_type/
  region/framework/vendor) are now grouped as
  `hf_endpoints: HFEndpointsOptions = None`; sampling defaults
  (temperature/top_k/top_p) are grouped as
  `sampling: SamplingOptions = None`. Pass instances of those dataclasses
  instead of the individual kwargs.

---

## [0.3.1rc1] — 2026-03-28 (included in v0.4.0 branch)

### Added
- **Engineering standards** (`docs/standards/`) — 9 standard documents: coding, architecture, error-handling, logging-observability, testing, documentation, localization, code-review, release.
- **AI agent skills** (`.claude/skills/`) — 6 task-specific SKILL.md checklists: add-config-field, add-trainer-feature, add-test, sync-bilingual-docs, cut-release, review-pr.
- **CLAUDE.md** — Root-level AI agent guidance file with non-negotiable project principles, skill table, and repo structure map.
- **Phase 10-13 planning docs** (`docs/roadmap/phase-*.md`) — Detailed planning for Post-Training Completion, Data Ingestion, Quickstart Layer, and Pro CLI.

### Changed
- **docs/ reorganization** — Reference docs moved to `docs/reference/`, design specs to `docs/design/`. All internal links updated (29 link fixes).
- **Roadmap refactored** — `docs/roadmap.md` reduced from 910 to 78 lines; phase details moved to `docs/roadmap/` subdirectory.

### Fixed (Security & Config Hardening)
- Webhook URLs excluded from HuggingFace Hub model cards — prevents credential leaks
- User-supplied strings sanitized before Markdown template embedding (content injection prevention)
- All 19 Pydantic sub-models enforce `extra="forbid"` — YAML typos are errors, not silent bugs
- Deprecated `lora.use_dora` / `lora.use_rslora` booleans auto-normalize to `lora.method` with warnings
- Audit log hash chain restores continuity across process restarts
- Compliance manifests correctly report pre-OOM-recovery batch size
- GRPO reward model path correctly wrapped as callable
- Safety classifier receives full `[INST] prompt [/INST] response` context
- Extension-less files raise clear `ValueError` instead of silently loading wrong format
- TIES tie-breaking fixed; DARE now deterministic with `seed=42`

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
