# ForgeLM

[![PyPI](https://img.shields.io/pypi/v/forgelm.svg)](https://pypi.org/project/forgelm/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/cemililik/ForgeLM/actions/workflows/ci.yml/badge.svg)](https://github.com/cemililik/ForgeLM/actions/workflows/ci.yml)

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
- **GPU Cost Estimation**: Auto-detection for 18 GPU models with per-run cost tracking

### Evaluation & Safety
- **Automated Benchmarking**: Post-training evaluation via `lm-evaluation-harness`
- **Safety Evaluation**: Llama Guard classifier with confidence-weighted scoring, S1-S14 harm categories, severity levels, cross-run trend tracking, and auto-revert
- **LLM-as-Judge**: API-based (OpenAI) or local model scoring for quality assessment
- **Auto-Revert**: Automatically discard models that fail loss, benchmark, or safety thresholds

### Quickstart Layer (v0.4.5)
- **One-Command Templates**: `forgelm quickstart customer-support` — bundled templates for SFT, code, BYOD domain expert, Turkish medical Q&A, and GRPO math reasoning. Auto-downsizes models on small GPUs.
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
- **Docker**: Official Dockerfile and docker-compose for portable deployment
- **Offline / Air-Gapped**: Full operation without internet for regulated industries
- **JSON Output**: Machine-readable results with `--output-format json` for pipeline integration
- **Webhook Notifications**: Slack/Teams alerts on training start, success, or failure
- **W&B / MLflow / TensorBoard**: Flexible experiment tracking via `report_to`
- **Model Card Generation**: Auto-generated HF-compatible model cards with metrics and benchmarks
- **Model Merging**: TIES, DARE, SLERP, linear merge of multiple adapters via `--merge`

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

Each notebook is runnable in Colab with a free T4 GPU.

**Getting started**
- [Quick Start — SFT Fine-Tuning](notebooks/quickstart_sft.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/cemililik/ForgeLM/blob/main/notebooks/quickstart_sft.ipynb)

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

```bash
pip install -e ".[qlora]"        # 4-bit quantization (Linux)
pip install -e ".[unsloth]"      # Unsloth backend (Linux)
pip install -e ".[eval]"         # lm-evaluation-harness benchmarks
pip install -e ".[tracking]"     # W&B experiment tracking
pip install -e ".[distributed]"  # DeepSpeed multi-GPU
pip install -e ".[merging]"      # mergekit model merging
pip install -e ".[dev]"          # pytest, ruff (development)
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
├── cli.py           # CLI with 10+ modes (train, dry-run, merge, benchmark, wizard...)
├── config.py        # Pydantic config (19 models: training, evaluation, distributed...)
├── data.py          # Dataset loading (SFT, DPO, KTO, GRPO formats + multi-dataset)
├── model.py         # Model loading (transformers, unsloth, MoE, PEFT)
├── trainer.py       # Training orchestration (6 trainer types via TRL, GaLore, long-context)
├── inference.py     # Shared inference primitives (load, generate, stream, adaptive sampling)
├── chat.py          # Interactive terminal REPL with streaming and slash commands
├── export.py        # GGUF export via llama-cpp-python
├── fit_check.py     # Pre-flight VRAM estimator (FITS / TIGHT / OOM / UNKNOWN)
├── deploy.py        # Deployment config generator (Ollama, vLLM, TGI, HF Endpoints)
├── results.py       # TrainResult dataclass
├── benchmark.py     # lm-evaluation-harness integration
├── safety.py        # Post-training safety evaluation (Llama Guard)
├── judge.py         # LLM-as-Judge evaluation (API + local)
├── compliance.py    # EU AI Act compliance export & data provenance
├── model_card.py    # Auto-generated HF model cards
├── merging.py       # Model merging (TIES, DARE, SLERP, linear)
├── synthetic.py     # Synthetic data generation (teacher→student distillation)
├── wizard.py        # Interactive configuration wizard
├── webhook.py       # Slack/Teams webhook notifications
└── utils.py         # Authentication & checkpoint management

configs/deepspeed/   # ZeRO-2, ZeRO-3, ZeRO-3+Offload presets
notebooks/           # Colab-ready Jupyter notebooks
tests/               # 430 passed (+34 skipped) across 30 test files
docs/guides/         # Quickstart, alignment, CI/CD, enterprise, safety guides
```

---

## License

[Apache License 2.0](LICENSE)
