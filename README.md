# ForgeLM

[![PyPI](https://img.shields.io/pypi/v/forgelm.svg)](https://pypi.org/project/forgelm/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/cemililik/ForgeLM/actions/workflows/ci.yml/badge.svg)](https://github.com/cemililik/ForgeLM/actions/workflows/ci.yml)

**Runs on Linux, macOS, and Windows.** The PyPI metadata's `Operating System :: OS Independent` classifier is backed by a release-tag CI matrix that builds the wheel on Linux and re-installs + tests it across **3 operating systems × 4 Python versions = 12 combinations** (Ubuntu, macOS, Windows × Python 3.10, 3.11, 3.12, 3.13) — every combo must pass before PyPI publish runs. See [`.github/workflows/publish.yml`](.github/workflows/publish.yml). Linux-only extras (`qlora`, `unsloth`) are flagged on each `pip install "forgelm[...]"` line below.

**ForgeLM** is a config-driven, enterprise-ready LLM fine-tuning toolkit. It supports the full modern post-training stack — from supervised fine-tuning to preference alignment to reasoning RL — with integrated safety evaluation, EU AI Act compliance, and CI/CD-native design.

## Features

### Training
- **6 Trainer Types**: SFT, DPO, SimPO, KTO, ORPO, GRPO — the complete alignment stack
- **Unsloth & Transformers**: 2-5x faster training with `unsloth` backend, or standard `transformers`
- **4-Bit QLoRA & DoRA**: NF4 quantization with LoRA, DoRA, PiSSA, and rsLoRA support
- **GaLore**: Optimizer-level memory optimization — full-parameter training via gradient low-rank projection (alternative to LoRA)
- **Long-Context Training**: RoPE scaling, NEFTune noise injection, sliding window attention, sample packing
- **Multi-Dataset Training**: Mix multiple datasets with configurable ratios
- **Synthetic Data Pipeline**: Teacher-to-student distillation with `--generate-data` CLI flag
- **DeepSpeed & FSDP**: Multi-GPU distributed training with ZeRO-2/3 presets
- **MoE Support**: Fine-tune Mixture of Experts models (Qwen3, Mixtral, DeepSeek)
- **GPU Cost Estimation**: Auto-detection for 16 GPU models with per-run cost tracking

### Evaluation & Safety
- **Automated Benchmarking**: Post-training evaluation via `lm-evaluation-harness`
- **Safety Evaluation**: Llama Guard classifier with confidence-weighted scoring, S1-S14 harm categories, severity levels, cross-run trend tracking, and auto-revert
- **LLM-as-Judge**: API-based (OpenAI) or local model scoring for quality assessment
- **Auto-Revert**: Opt-in (`evaluation.auto_revert: true`) — automatically discards models that fail loss, benchmark, or safety thresholds before artifacts are written

### Document Ingestion & Data Audit (v0.5.0 — Phases 11 + 11.5 + 12 + 12.5 consolidated)
- **Multi-Format Ingestion**: `forgelm ingest ./policies/ --recursive --output data/policies.jsonl` — turns raw PDF / DOCX / EPUB / TXT / Markdown into the SFT-ready JSONL the trainer accepts. Optional dep: `pip install forgelm[ingestion]`. Includes a **Markdown-aware splitter** (`--strategy markdown`) and DOCX table preservation in Markdown table syntax.
- **Chunking Strategies**: `paragraph` (default; preserves boundaries), `sliding` (fixed window with overlap), or `markdown` (heading-aware splitter that keeps fenced code blocks atomic and inlines a heading breadcrumb at the top of each chunk for SFT context). A `semantic` strategy is reserved for a follow-up phase — the implementation in `forgelm.ingestion` raises `NotImplementedError` today and the CLI hides it from `--strategy` choices. Token-aware mode: `--chunk-tokens 1024 --tokenizer Qwen/Qwen2.5-7B-Instruct` sizes chunks against your model's actual vocabulary.
- **PII Masking on Ingest**: `--pii-mask` redacts emails, phones, credit cards (Luhn-validated), IBAN, and national IDs (TR / DE / FR / US-SSN) before chunks land in the JSONL.
- **PDF Page Header/Footer Dedup**: Lines that recur on ≥ 70 % of PDF pages (watermarks, page numbers, copyright lines) are stripped automatically — the audit's near-duplicate counts stop misfiring on long policy / book PDFs.
- **Dataset Audit**: `forgelm audit data/sft.jsonl --output ./audit/` — produces `data_audit_report.json` with sample count, length distribution, top-3 language detection, LSH-banded near-duplicate rate (`O(n × k)` typical case, exact recall at the default Hamming threshold; optional **MinHash LSH** via `--dedup-method minhash` for >50K-row corpora), cross-split leakage check, null/empty rate, and PII flag counts with **severity tiers** (critical / high / medium / low + worst-tier verdict). Always-on **secrets/credential scan** covers the nine families enumerated in `forgelm.data_audit.SECRET_TYPES` — AWS access keys, GitHub tokens, Slack tokens, OpenAI API keys, Google API keys, JWTs, full OpenSSH private-key blocks, full PGP private-key blocks, and Azure storage connection strings — and an opt-in **heuristic quality filter** (`--quality-filter`). CPU-only; streaming JSONL reader keeps memory bounded on multi-million-row splits; feeds EU AI Act Article 10 governance artifact automatically when present at training time. Legacy `--data-audit` flag still works as a deprecation alias.
- **Secrets-Aware Ingest**: `forgelm ingest … --secrets-mask` scrubs credentials before chunks land in the JSONL — fine-tuning on text containing real API keys memorises them at training time. Pairs with `--pii-mask`; secrets run first so combined detectors don't double-count overlapping spans. `--all-mask` is a one-flag shorthand for both.
- **Optional ML-NER PII**: `forgelm audit --pii-ml [--pii-ml-language LANG]` layers [Presidio](https://github.com/microsoft/presidio) NER on top of the regex detector via the optional `[ingestion-pii-ml]` extra **plus a separate `python -m spacy download en_core_web_lg`** step (or the matching model for the chosen language). Adds `person` / `organization` / `location` categories into the same `pii_summary` / `pii_severity` blocks under disjoint category names.
- **Croissant 1.0 dataset card**: `forgelm audit --croissant` emits a [Google Croissant 1.0](http://mlcommons.org/croissant/) dataset card under the report's `croissant` key so the same JSON file doubles as both the EU AI Act Article 10 governance artifact and a Croissant-consumer dataset card.
- **Wizard "audit first"**: when the wizard resolves a JSONL (typed or produced by `forgelm ingest`) it offers to run `forgelm audit` inline and prints the verdict before continuing — closes the BYOD audit loop end-to-end.

### Quickstart Layer (v0.4.5)
- **One-Command Templates**: `forgelm quickstart customer-support` — 5 bundled templates (SFT customer-support, code-assistant, medical-qa-tr, domain-expert, GRPO grpo-math). Auto-downsizes models on small GPUs.
- **Conservative Defaults**: Every template ships QLoRA 4-bit, rank=8, batch=1, gradient checkpointing on — designed to run on a single 12 GB GPU.
- **Wizard Integration**: `forgelm --wizard` opens with "Start from a template?" — same code paths, same YAML schema as a hand-written config.

### Post-Training (v0.4.0)
- **Interactive Chat**: `forgelm chat ./model` — streaming REPL with `/reset`, `/save`, `/temperature`, `/system` commands; optional Llama Guard safety routing
- **GGUF Export**: `forgelm export ./model --quant q4_k_m` — wraps `llama-cpp-python` converter; 6 quant levels; SHA-256 appended to integrity manifest
- **Deployment Configs**: `forgelm deploy ./model --target ollama|vllm|tgi|hf-endpoints` — generates ready-to-use config files; does not start the server
- **VRAM Fit Check**: `forgelm --config my.yaml --fit-check` — pre-flight memory estimator; `FITS / TIGHT / OOM / UNKNOWN` verdict with recommendations

### Enterprise & MLOps
- **Config-Driven**: Declarative YAML — built for CI/CD pipelines, not notebooks
- **EU AI Act Compliance**: Auto-generated audit trails, data provenance (SHA-256), training manifests
- **ISO 27001 / SOC 2 Type II Alignment**: Software cannot be ISO/SOC 2 *certified* — only organisations can — but ForgeLM produces the audit-trail, change-management, data-lineage, and supply-chain evidence the deployer's auditor explicitly asks for. CycloneDX 1.5 SBOM per release, `pip-audit` nightly, `bandit` CI, append-only HMAC-chained audit log (HMAC integrity is active **only when** `FORGELM_AUDIT_SECRET` is set + KMS-managed + rotated between output-dir lifecycles — see [`docs/qms/access_control.md`](docs/qms/access_control.md) §3.4), Article 14 staging gate, Article 15/17 GDPR tooling. See [`docs/guides/iso_soc2_deployer_guide.md`](docs/guides/iso_soc2_deployer_guide.md) for the deployer audit cookbook + 93-control coverage map.
- **Library API**: `from forgelm import ForgeTrainer, audit_dataset, verify_audit_log, verify_annex_iv_artifact, verify_gguf, mask_pii, mask_secrets, ...` — every CLI surface has a stable Python entry point under `forgelm.__all__`, version-pinned via `forgelm.__api_version__` (decoupled from `__version__`). Run `python -c "import forgelm; print(sorted(forgelm.__all__))"` for the full surface.
- **GDPR Tooling**: `forgelm purge --row-id <id> --corpus <path>` (Article 17 right-to-erasure: redacts data + adapters in place; the audit log itself is append-only — Article 17(3)(b) preservation — and the erasure is recorded by appending six compensating events (`data.erasure_requested`, `data.erasure_completed`, etc.) so the hash chain remains intact) and `forgelm reverse-pii --query <fragment>` (Article 15 right-of-access: locates PII matches across artefacts without re-loading raw data).
- **Operational Subcommands**: `forgelm doctor` (env / GPU / CUDA / extras pre-flight), `forgelm cache-models` + `forgelm cache-tasks` (air-gap pre-cache for HF models + lm-eval tasks), `forgelm safety-eval` (standalone Llama Guard run), `forgelm verify-audit` / `verify-annex-iv` / `verify-gguf` (compliance + artefact verification toolbelt), `forgelm approvals` (list pending Article 14 staging-gate runs).
- **Docker**: Official Dockerfile and docker-compose for portable deployment
- **Offline / Air-Gapped**: Full operation without internet for regulated industries
- **JSON Output**: Machine-readable results with `--output-format json` for pipeline integration; the per-subcommand schema is locked in [`docs/usermanuals/en/reference/json-output.md`](docs/usermanuals/en/reference/json-output.md).
- **Webhook Notifications**: Slack/Teams alerts on training start, success, failure, reverted, or awaiting_approval (5-event vocabulary, paired with audit events)
- **W&B / MLflow / TensorBoard**: Flexible experiment tracking via `report_to`
- **Model Card Generation**: Auto-generated HF-compatible model cards with metrics and benchmarks
- **Model Merging**: TIES, DARE, SLERP, linear merge of multiple adapters via `--merge`
- **Supply-Chain Security**: CycloneDX 1.5 SBOM per release-tag matrix combo (12 SBOMs per tag), `pip-audit` + `bandit` nightly + on-tag, `gitleaks` pre-commit. See [`docs/reference/supply_chain_security.md`](docs/reference/supply_chain_security.md).

---

## Quick Start

```bash
# Install
pip install -e .
pip install -e ".[export]"   # GGUF export (optional, non-Windows)

# Fastest path: pick a bundled template (v0.4.5+)
forgelm quickstart --list
forgelm quickstart customer-support           # render config + train + chat
forgelm quickstart code-assistant --dry-run   # render config only
forgelm quickstart medical-qa-tr --model your-org/your-model  # override

# Have raw docs? Ingest them first (v0.5.0; supports token-aware sizing)
pip install -e ".[ingestion]"
forgelm ingest ./policies/ --recursive --output data/policies.jsonl
forgelm audit data/policies.jsonl --output ./audit/   # `forgelm --data-audit ...` still works as legacy alias

# Or generate config interactively
forgelm --wizard

# Validate without training
forgelm --config my_config.yaml --dry-run

# Check VRAM before a long run
forgelm --config my_config.yaml --fit-check

# Train
forgelm --config my_config.yaml

# After training: chat, export, deploy
forgelm chat ./checkpoints/final_model
forgelm export ./checkpoints/final_model --output model.gguf --quant q4_k_m
forgelm deploy ./checkpoints/final_model --target ollama --output ./Modelfile
```

See the [Quick Start Guide](docs/guides/quickstart.md) for a complete walkthrough.

---

## Guides

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/guides/quickstart.md) | First fine-tuned model in 5 minutes |
| [Document Ingestion](docs/guides/ingestion.md) ([Türkçe](docs/guides/ingestion-tr.md)) | Raw PDF/DOCX/EPUB → SFT-ready JSONL |
| [Dataset Audit](docs/guides/data_audit.md) ([Türkçe](docs/guides/data_audit-tr.md)) | Length, language, dedup, cross-split leakage, PII |
| [Alignment (DPO/SimPO/KTO/GRPO)](docs/guides/alignment.md) | Complete post-training stack |
| [CI/CD Pipeline Integration](docs/guides/cicd_pipeline.md) | GitHub Actions, GitLab CI, Docker |
| [Enterprise Deployment](docs/guides/enterprise_deployment.md) | Docker, air-gapped, multi-GPU |
| [Safety & Compliance](docs/guides/safety_compliance.md) | EU AI Act, safety evaluation |
| [Distributed Training](docs/reference/distributed_training.md) | DeepSpeed ZeRO, FSDP, multi-node |
| [Troubleshooting & FAQ](docs/guides/troubleshooting.md) | Common issues and solutions |

## Reference Documentation

1. [Architecture Overview](docs/reference/architecture.md) ([Türkçe](docs/reference/architecture-tr.md))
2. [Configuration Guide](docs/reference/configuration.md) ([Türkçe](docs/reference/configuration-tr.md))
3. [Usage & Execution](docs/reference/usage.md) ([Türkçe](docs/reference/usage-tr.md))
4. [Data Preparation Format](docs/reference/data_preparation.md) ([Türkçe](docs/reference/data_preparation-tr.md))
5. [Product Strategy](docs/product_strategy.md) ([Türkçe](docs/product_strategy-tr.md))
6. [Roadmap](docs/roadmap.md) ([Türkçe](docs/roadmap-tr.md))

## Notebooks

Each notebook is runnable in Colab with a free T4 GPU. Data preparation runs CPU-only.

**Getting started**
- [Quick Start — SFT Fine-Tuning](notebooks/quickstart_sft.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/quickstart_sft.ipynb)
- [Data Curation — Ingestion + Audit](notebooks/data_curation.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/data_curation.ipynb) — `forgelm ingest` + `forgelm audit` end-to-end (markdown-aware splitter, PII / secrets masking, MinHash LSH, quality filter). **CPU-only**.

**Alignment methods** (post-SFT preference / RL)
- [DPO Preference Alignment](notebooks/dpo_alignment.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/dpo_alignment.ipynb)
- [KTO Binary Feedback](notebooks/kto_binary_feedback.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/kto_binary_feedback.ipynb)
- [GRPO Reasoning RL](notebooks/grpo_reasoning.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/grpo_reasoning.ipynb)

**Advanced training**
- [Multi-Dataset Training](notebooks/multi_dataset.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/multi_dataset.ipynb) — mix multiple datasets with configurable ratios.
- [GaLore Memory Optimization](notebooks/galore_memory_optimization.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/galore_memory_optimization.ipynb) — full-parameter training via gradient low-rank projection (LoRA alternative).
- [Synthetic Data Pipeline](notebooks/synthetic_data_training.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/synthetic_data_training.ipynb) — teacher-to-student distillation (API / local / pre-generated backends).

**Post-training & safety**
- [Post-Training Workflow](notebooks/post_training_workflow.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/post_training_workflow.ipynb) — end-to-end Phase 10 toolchain: `--fit-check` → `chat` → `export` (GGUF) → `deploy`.
- [Safety Evaluation & Red-Teaming](notebooks/safety_evaluation.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/safety_evaluation.ipynb) — 140 adversarial prompts × 6 categories (Llama Guard).

---

## Installation

```bash
# From PyPI
pip install forgelm

# Or from source
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -e .
```

### Optional Dependencies

From PyPI (most users):

```bash
pip install "forgelm[qlora]"             # 4-bit quantization (Linux)
pip install "forgelm[unsloth]"           # Unsloth backend (Linux)
pip install "forgelm[eval]"              # lm-evaluation-harness benchmarks
pip install "forgelm[tracking]"          # W&B experiment tracking
pip install "forgelm[distributed]"       # DeepSpeed multi-GPU
pip install "forgelm[merging]"           # mergekit model merging
pip install "forgelm[ingestion]"         # PDF/DOCX/EPUB/Markdown → JSONL + langdetect + xxhash
pip install "forgelm[ingestion-scale]"   # MinHash LSH dedup (datasketch) for >50K-row corpora
pip install "forgelm[ingestion-pii-ml]"  # Presidio ML-NER for person/organization/location PII (Phase 12.5; ALSO needs `python -m spacy download en_core_web_lg`)
pip install "forgelm[export]"            # GGUF export via llama-cpp-python
pip install "forgelm[chat]"              # Rich terminal rendering for `forgelm chat`
```

From a local clone (contributors):

```bash
pip install -e ".[ingestion,eval,tracking]"  # Editable install, multiple extras
pip install -e ".[dev]"                      # pytest, ruff (development)
```

---

## Docker

```bash
# Build (with benchmarking support)
docker build -t forgelm --build-arg INSTALL_EVAL=true .

# Train
docker run --gpus all \
  -v $(pwd)/my_config.yaml:/workspace/config.yaml \
  -v $(pwd)/output:/workspace/output \
  forgelm --config /workspace/config.yaml

# Multi-GPU
docker run --gpus all --shm-size=16g \
  forgelm:latest \
  torchrun --nproc_per_node=4 -m forgelm.cli --config /workspace/config.yaml
```

---

## CLI

```bash
forgelm --config job.yaml                    # Train
forgelm --config job.yaml --dry-run          # Validate config
forgelm --config job.yaml --output-format json  # JSON output for CI/CD
forgelm --config job.yaml --resume           # Resume from checkpoint
forgelm --config job.yaml --offline          # Air-gapped mode
forgelm --config job.yaml -q                 # Quiet mode (warnings only)
forgelm --config job.yaml --benchmark-only /path/to/model  # Evaluate only
forgelm --config job.yaml --merge            # Merge models
forgelm --config job.yaml --compliance-export ./audit/  # Export audit artifacts
forgelm --wizard                             # Interactive config generator
forgelm --version                            # Show version
```

---

## Project Structure

```
forgelm/
├── cli/              # CLI package (split out of legacy single-file cli.py)
│   ├── __main__.py   # `python -m forgelm.cli` entrypoint
│   ├── _parser.py    # argparse wiring for the top-level + every subcommand
│   ├── _dispatch.py  # subcommand router; one entry per *_subcommand* below
│   ├── _exit_codes.py# 0/1/2/3/4 — public CLI contract
│   └── subcommands/  # _audit, _ingest, _chat, _export, _deploy, _quickstart,
│                     # _doctor, _cache, _purge, _reverse_pii, _approve,
│                     # _approvals, _safety_eval, _verify_audit,
│                     # _verify_annex_iv, _verify_gguf, ...
├── data_audit/       # Audit package (split out of legacy single-file data_audit.py)
│   ├── _orchestrator.py   # `run_audit` entry point + parallel split walker
│   ├── _aggregator.py     # per-split metric aggregator
│   ├── _streaming.py      # streaming JSONL reader
│   ├── _simhash.py        # 64-bit simhash + LSH banding (default dedup)
│   ├── _minhash.py        # MinHash LSH dedup (`[ingestion-scale]` extra)
│   ├── _pii_regex.py      # PII regex engine (Luhn, IBAN, TC Kimlik validators)
│   ├── _pii_ml.py         # Presidio NER adapter (`[ingestion-pii-ml]` extra)
│   ├── _secrets.py        # 9-family credential scan (always-on)
│   ├── _quality.py        # Gopher / C4 / RefinedWeb-style heuristics
│   ├── _croissant.py      # Croissant 1.0 dataset card emitter
│   └── _summary.py        # `summarize_report` truncation policy
├── config.py         # Pydantic config (19 models: training, evaluation, distributed, ...)
├── data.py           # Dataset loading (SFT, DPO, KTO, GRPO formats + multi-dataset)
├── ingestion.py      # Raw docs → SFT JSONL (PDF/DOCX/EPUB/TXT/Markdown + chunking + masking) — `forgelm ingest`
├── model.py          # Model loading (transformers, unsloth, MoE, PEFT)
├── trainer.py        # Training orchestration (6 trainer types via TRL, GaLore, long-context)
├── inference.py      # Shared inference primitives (load, generate, stream, adaptive sampling)
├── chat.py           # Interactive terminal REPL with streaming and slash commands
├── export.py         # GGUF export via llama-cpp-python
├── fit_check.py      # Pre-flight VRAM estimator (FITS / TIGHT / OOM / UNKNOWN)
├── deploy.py         # Deployment config generator (Ollama, vLLM, TGI, HF Endpoints)
├── results.py        # TrainResult dataclass (AuditReport lives in data_audit/, IngestionResult in ingestion.py)
├── benchmark.py      # lm-evaluation-harness integration
├── safety.py         # Post-training safety evaluation (Llama Guard)
├── judge.py          # LLM-as-Judge evaluation (API + local)
├── compliance.py     # EU AI Act compliance export, audit log + HMAC chain, GDPR purge / reverse-pii primitives
├── model_card.py     # Auto-generated HF model cards
├── merging.py        # Model merging (TIES, DARE, SLERP, linear)
├── synthetic.py      # Synthetic data generation (teacher→student distillation)
├── grpo_rewards.py   # Built-in GRPO reward shapers (format / length fallbacks)
├── quickstart.py     # `forgelm quickstart <template>` — bundled SFT / code / domain templates
├── wizard.py         # Interactive configuration wizard (offers `forgelm ingest` for raw-doc dirs)
├── webhook.py        # Slack/Teams webhook notifications (5-event vocabulary)
├── _http.py          # Single chokepoint for outbound HTTP (SSRF guard, timeout floor, secret masking)
├── _version.py       # `__version__` + `__api_version__` constants
└── utils.py          # Authentication & checkpoint management

configs/deepspeed/    # ZeRO-2, ZeRO-3, ZeRO-3+Offload presets
forgelm/safety_prompts/  # 140 adversarial prompts × 6 categories for safety evaluation
forgelm/templates/    # Quickstart templates (SFT, code-assistant, domain-expert, medical-qa-tr, grpo-math)
notebooks/            # Colab-ready Jupyter notebooks (data curation, SFT, DPO, KTO, GRPO, ...)
tests/                # Test suite — run with `pytest tests/` (count grows over time; CI gates on green-on-every-commit)
tools/                # CI guards (check_anchor_resolution, check_bilingual_parity,
                      # check_cli_help_consistency, check_field_descriptions,
                      # check_pip_audit, check_bandit, check_site_claims,
                      # generate_sbom, build_usermanuals)
docs/guides/          # Quickstart, ingestion, audit, alignment, CI/CD, enterprise, safety, ISO/SOC 2 guides
docs/usermanuals/{en,tr}/  # 4-section user manual: training, evaluation, deployment, reference
```

---

## Pro CLI (planned — v0.6.0-pro)

A paid tier built on top of the OSS core. Every Pro feature ships with a documented OSS workaround — Pro is for convenience and scale, not gatekeeping.

- `forgelm pro dashboard` — local-first experiment browser (run list, metric comparisons, config diffs, artifact browser) backed by your existing `checkpoints/` and `audit_log.jsonl`
- HPO via Optuna — `hpo:` config block spawns N subordinate training runs and emits a best-config YAML
- Scheduled training jobs — cron-style `schedule:` field with a daemon runner
- Team config store — `forgelm pro team push/pull` for shared golden-config patterns
- Live GPU cost estimation — real-time spot pricing from RunPod, Lambda Labs, vast.ai

Gated by adoption signal from v0.5.x — will not start before ≥1 K monthly PyPI installs. See [docs/roadmap/phase-13-pro-cli.md](docs/roadmap/phase-13-pro-cli.md).

---

## License

[Apache License 2.0](LICENSE)
