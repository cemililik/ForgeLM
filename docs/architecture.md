# ForgeLM Architecture

ForgeLM is designed with modularity and extensibility in mind. The workflow is broken down into distinct stages, each handled by a dedicated module.

## System Overview

```
forgelm --config job.yaml
    │
    ├── cli.py          → Parse args, load config, orchestrate
    ├── config.py       → Pydantic validation (19 config models)
    ├── utils.py        → HF authentication
    ├── model.py        → Load model + tokenizer + LoRA/PEFT
    ├── data.py         → Load + format dataset
    ├── trainer.py      → Train (6 trainer types via TRL)
    │   ├── benchmark.py    → lm-eval-harness evaluation
    │   ├── safety.py       → Llama Guard safety check
    │   ├── judge.py        → LLM-as-Judge scoring
    │   ├── model_card.py   → Auto-generate HF model card
    │   ├── compliance.py   → EU AI Act audit artifacts
    │   └── webhook.py      → Slack/Teams notifications
    ├── merging.py      → TIES/DARE/SLERP model merge (--merge)
    └── wizard.py       → Interactive config generator (--wizard)
```

## Directory Layout

```
ForgeLM/
├── forgelm/                # Core Python Package (16 modules)
│   ├── __init__.py         # Lazy imports for fast CLI startup
│   ├── cli.py              # CLI with 13 flags and 6 modes
│   ├── config.py           # 19 Pydantic config models
│   ├── data.py             # Dataset loading (SFT/DPO/KTO/GRPO/multimodal)
│   ├── model.py            # Model + LoRA/DoRA/PiSSA + MoE detection
│   ├── trainer.py          # Training orchestration (6 trainer types)
│   ├── results.py          # TrainResult dataclass (no heavy deps)
│   ├── benchmark.py        # lm-evaluation-harness integration
│   ├── safety.py           # Post-training safety evaluation
│   ├── judge.py            # LLM-as-Judge (API + local)
│   ├── compliance.py       # EU AI Act compliance + audit log + provenance
│   ├── model_card.py       # HF-compatible model card generation
│   ├── merging.py          # Model merging (TIES/DARE/SLERP/linear)
│   ├── wizard.py           # Interactive configuration wizard
│   ├── webhook.py          # Webhook notifications
│   └── utils.py            # Authentication + checkpoint management
├── configs/deepspeed/      # ZeRO-2, ZeRO-3, ZeRO-3+Offload presets
├── notebooks/              # 5 Colab-ready Jupyter notebooks
├── tests/                  # 200+ unit tests across 18 test files
├── docs/                   # Guides, reference docs, QMS templates
│   ├── guides/             # 6 user guides
│   └── qms/                # EU AI Act QMS SOP templates
├── Dockerfile              # Multi-stage Docker build
├── docker-compose.yaml     # Train + TensorBoard services
├── config_template.yaml    # Annotated config example
└── CONTRIBUTING.md         # Contributor guide
```

## Component Details

### `cli.py`
The orchestrator. Parses 13 CLI flags and routes to the appropriate mode: training, dry-run, wizard, merge, benchmark-only, or compliance export. Manages exit codes (0-4), logging setup, and JSON/text output formatting.

### `config.py`
19 Pydantic v2 models providing strict validation for all YAML configuration. Includes cross-field validation (e.g., high-risk classification enforces safety evaluation). Config models cover: model, LoRA, training, data, evaluation, safety, benchmark, judge, webhook, distributed, merge, compliance, risk assessment, monitoring, MoE, multimodal, and data governance.

### `data.py`
Interfaces with HuggingFace `datasets` library. Auto-detects dataset format (SFT, DPO, KTO, GRPO, multimodal) and validates against `trainer_type`. Handles multi-dataset mixing with configurable ratios. Applies chat templates via `tokenizer.apply_chat_template()` with fallback formatting.

### `model.py`
Loads models via HuggingFace Transformers or Unsloth backend. Configures QLoRA (4-bit NF4), PEFT adapters (LoRA, DoRA, PiSSA, rsLoRA), and MoE expert quantization/selection. Distributed-aware: skips `device_map="auto"` when DeepSpeed/FSDP is active. Multimodal-aware: loads `AutoProcessor` instead of `AutoTokenizer` for VLM models.

### `trainer.py`
Wraps TRL's trainers (SFTTrainer, DPOTrainer, KTOTrainer, ORPOTrainer, CPOTrainer/SimPO, GRPOTrainer) with ForgeLM's pipeline: baseline evaluation → training → post-training evaluation chain (loss → benchmark → safety → LLM-judge) → model save → model card → compliance artifacts → webhook notification. Includes auto-revert, human approval gate, audit logging, and resource tracking.

### `results.py`
Lightweight `TrainResult` dataclass — importable without torch/transformers. Carries success status, metrics, benchmark scores, resource usage, safety pass/fail, and judge scores.

### `benchmark.py`
Wraps EleutherAI `lm-evaluation-harness`. Runs configurable benchmark tasks, extracts accuracy metrics, applies min_score threshold, and saves results. Optional dependency: `pip install forgelm[eval]`.

### `safety.py`
Runs a configurable safety classifier (Llama Guard, ShieldGemma) on adversarial test prompts. Generates responses from the fine-tuned model, classifies each as safe/unsafe, and triggers auto-revert if regression exceeds threshold. Errors are treated as unsafe (fail-safe principle).

### `judge.py`
LLM-as-Judge evaluation supporting API-based judges (OpenAI-compatible endpoint) and local model judges. Includes robust JSON parsing with markdown code block extraction. Scores on 1-10 scale with configurable minimum threshold.

### `compliance.py`
EU AI Act compliance engine covering Articles 9-17:
- `AuditLogger`: Append-only JSON Lines event log with unique run IDs
- `generate_training_manifest()`: Annex IV technical documentation
- `generate_data_governance_report()`: Data quality statistics
- `generate_model_integrity()`: SHA-256 checksums of output artifacts
- `generate_deployer_instructions()`: Art. 13 deployer document
- `export_compliance_artifacts()`: All artifacts to directory
- `export_evidence_bundle()`: ZIP archive for auditors

### `model_card.py`
Generates HuggingFace-compatible README.md with YAML front matter, training parameters table, metrics, benchmark results, config snippet, and usage example. Excludes auth tokens from exported config.

### `merging.py`
Model merging with 4 strategies: linear interpolation, TIES-Merging (trim + sign election + merge), DARE (random drop + rescale), and SLERP (spherical interpolation for 2 models). Operates on state dicts — no mergekit dependency required.

### `wizard.py`
Interactive CLI wizard for generating valid YAML configs. Detects GPU hardware, suggests backend, offers model presets, guides through LoRA strategy and training objective selection (6 trainer types with format hints), and optionally starts training immediately.

### `webhook.py`
Sends structured JSON payloads to Slack/Teams/generic webhooks on training start, success, and failure. Supports URL from config or environment variable. Graceful error handling with configurable timeout.

### `utils.py`
HuggingFace authentication (token from config, env var, or local cache with modern XDG path support) and checkpoint management (keep, delete, compress with UUID-suffixed archives).
