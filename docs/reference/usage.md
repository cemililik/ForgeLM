# Usage Guide

ForgeLM is designed to be executed via the command line, making it perfect for both local experimentation and automated CI/CD pipelines.

## Prerequisites

- Python 3.10+
- NVIDIA GPU with CUDA (recommended; CPU mode is very slow)

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -e .
```

### Optional installs

```bash
pip install -e ".[qlora]"        # 4-bit quantization (Linux)
pip install -e ".[unsloth]"      # Unsloth backend (Linux)
pip install -e ".[eval]"         # lm-evaluation-harness
pip install -e ".[tracking]"     # W&B experiment tracking
pip install -e ".[distributed]"  # DeepSpeed multi-GPU
pip install -e ".[merging]"      # mergekit model merging
pip install -e ".[export]"       # GGUF export (llama-cpp-python, non-Windows)
pip install -e ".[chat]"         # Rich rendering in forgelm chat
```

## Authentication

For gated models (Llama, Gemma) or private datasets:

1. **Environment Variable** (recommended): `export HUGGINGFACE_TOKEN="hf_xxxxx"`
2. **Config File**: `auth: { hf_token: "hf_xxxxx" }` in YAML
3. **Local Cache**: `huggingface-cli login`

## CLI Reference

### Core Commands

```bash
# Train a model
forgelm --config my_config.yaml

# Interactive config wizard
forgelm --wizard

# Validate config without training (no GPU needed)
forgelm --config my_config.yaml --dry-run

# Show version
forgelm --version
```

### Output & Logging

```bash
# JSON output for CI/CD pipelines
forgelm --config my_config.yaml --output-format json

# Suppress INFO logs (warnings/errors only)
forgelm --config my_config.yaml --quiet
forgelm --config my_config.yaml -q

# Set log level explicitly
forgelm --config my_config.yaml --log-level DEBUG
```

### Training Modes

```bash
# Resume from latest checkpoint
forgelm --config my_config.yaml --resume

# Resume from specific checkpoint
forgelm --config my_config.yaml --resume ./checkpoints/checkpoint-500

# Air-gapped / offline mode (no HF Hub calls)
forgelm --config my_config.yaml --offline
```

### VRAM Fit Check

Before training, estimate whether your config fits in GPU memory:

```bash
# Text output (human-readable verdict)
forgelm --config my_config.yaml --fit-check

# JSON output (for CI/CD pipelines)
forgelm --config my_config.yaml --fit-check --output-format json
```

Output shows: estimated peak VRAM, available VRAM (if GPU detected), verdict (`FITS` / `TIGHT` / `OOM` / `UNKNOWN`), and ordered recommendations. Falls back to hypothetical mode when no GPU is detected.

### Post-Training: Chat, Export, Deploy

After training, interact with and deploy your fine-tuned model directly from the CLI. These subcommands work without `--config`.

```bash
# Interactive chat REPL (streaming by default)
forgelm chat ./checkpoints/final_model
forgelm chat ./checkpoints/final_model --adapter ./adapter
forgelm chat ./checkpoints/final_model --system "You are a helpful assistant." --temperature 0.8

# Export to GGUF (for Ollama, LM Studio, llama.cpp)
# Requires: pip install forgelm[export]
forgelm export ./checkpoints/final_model --output model.gguf --quant q4_k_m
forgelm export ./checkpoints/final_model --output model.gguf --quant q8_0 --adapter ./adapter

# Generate deployment config files
forgelm deploy ./checkpoints/final_model --target ollama --output ./Modelfile
forgelm deploy ./checkpoints/final_model --target vllm --output ./vllm_config.yaml
forgelm deploy ./checkpoints/final_model --target tgi --output ./docker-compose.yaml
forgelm deploy ./checkpoints/final_model --target hf-endpoints --output ./endpoint.json
forgelm deploy ./checkpoints/final_model --target ollama --output ./Modelfile --system "Be concise."
```

**Chat slash commands:** `/reset`, `/save [file]`, `/temperature N`, `/system [prompt]`, `/help`, `/exit`

**Export quantization levels:** `q2_k`, `q3_k_m`, `q4_k_m` (recommended), `q5_k_m`, `q8_0`, `f16`

### Synthetic Data Generation

```bash
# Generate synthetic training data via teacher model distillation
forgelm --config my_config.yaml --generate-data
```

This uses the `synthetic` config section to generate training data from a teacher model before training begins. See the [Configuration Guide](configuration.md) for all synthetic data options.

### Document Ingestion (v0.5.0+; token-aware in v0.5.1; markdown + secrets-mask in v0.5.2)

Convert raw PDF / DOCX / EPUB / TXT / Markdown into SFT-ready JSONL. Optional dep: `pip install forgelm[ingestion]`. See [Ingestion Guide](../guides/ingestion.md).

```bash
# Single file
forgelm ingest ./book.epub --output data/sft.jsonl

# Recursive directory walk + paragraph chunking
forgelm ingest ./policies/ --recursive --output data/policies.jsonl

# Sliding window with overlap (long technical docs)
forgelm ingest ./scan.pdf --strategy sliding --chunk-size 1024 --overlap 128 \
  --output data/scan.jsonl

# Mask PII before writing
forgelm ingest ./customer_emails/ --pii-mask --output data/anon.jsonl

# Token-aware chunking (v0.5.1) — sizes chunks against your model's vocab
forgelm ingest ./policies/ --recursive --output data/policies.jsonl \
  --chunk-tokens 1024 --tokenizer "Qwen/Qwen2.5-7B-Instruct"

# v0.5.2: markdown-aware splitter for technical wikis / READMEs
forgelm ingest ./engineering_wiki/ --recursive --strategy markdown \
  --output data/wiki.jsonl

# v0.5.2: scrub credentials before chunks land in the JSONL
forgelm ingest ./mixed_corpus/ --secrets-mask --output data/clean.jsonl

# v0.5.2: combine secrets + PII masking (secrets first to avoid double-counting)
forgelm ingest ./mixed_corpus/ --secrets-mask --pii-mask --output data/scrubbed.jsonl
```

### Dataset Audit (v0.5.0+; subcommand promoted in v0.5.1; MinHash + quality + secrets in v0.5.2)

CPU-only quality + governance audit. Produces `data_audit_report.json`. See [Audit Guide](../guides/data_audit.md).

```bash
# Single split (v0.5.1 subcommand)
forgelm audit data/sft.jsonl --output ./audit/

# Multi-split directory (train.jsonl / validation.jsonl / test.jsonl)
forgelm audit data/ --output ./audit/

# Show every split (no zero-finding fold)
forgelm audit data/ --verbose

# Custom Hamming threshold for simhash near-duplicate detection
forgelm audit data/ --near-dup-threshold 5

# v0.5.2: MinHash LSH dedup for >50K-row corpora (needs `[ingestion-scale]` extra)
forgelm audit data/large_corpus.jsonl --dedup-method minhash --jaccard-threshold 0.85

# v0.5.2: opt-in heuristic quality filter (Gopher/C4 style)
forgelm audit data/ --quality-filter

# Machine-readable summary on stdout
forgelm audit data/sft.jsonl --output ./audit/ --output-format json

# Legacy alias (kept working; logs a one-line deprecation notice)
forgelm --data-audit data/sft.jsonl --output ./audit/
```

The audit captures: per-split sample count + length distribution, top-3 language detection, **LSH-banded** simhash near-duplicate rate (Phase 11.5; brute-force fallback at edge thresholds; v0.5.2 added optional **MinHash LSH** path), cross-split leakage (silent train-test overlap), PII flag counts with **severity tiers**, **always-on credentials/secrets scan** (`secrets_summary` — AWS / GitHub / Slack / OpenAI / Google / JWT / private-key headers), and an opt-in **heuristic quality filter** (Gopher/C4 style) that adds a `quality_summary` block.

When `data_audit_report.json` is present in the trainer's `output_dir` at training time, its findings are inlined under the `data_audit` key of the EU AI Act Article 10 governance artifact automatically.

### Evaluation & Merging

```bash
# Benchmark an existing model (no training)
forgelm --config my_config.yaml --benchmark-only /path/to/model

# Merge models from config
forgelm --config my_config.yaml --merge

# Export compliance artifacts (no GPU needed)
forgelm --config my_config.yaml --compliance-export ./audit/
```

## Exit Codes

| Code | Meaning | CI/CD Action |
|------|---------|-------------|
| `0` | Success | Deploy model |
| `1` | Config error | Fix YAML |
| `2` | Training error | Check GPU/memory/deps |
| `3` | Evaluation failure | Model below threshold — adjust data or thresholds |
| `4` | Awaiting approval | Human review required (`require_human_approval: true`) |

## Training Output

After successful training, ForgeLM produces:

```
checkpoints/
├── final_model/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── README.md                    # Auto-generated model card
│   ├── deployer_instructions.md     # Deployer guide (Art. 13)
│   └── model_integrity.json         # SHA-256 checksums (Art. 15)
├── compliance/
│   ├── compliance_report.json       # Full audit trail
│   ├── training_manifest.yaml       # Human-readable summary
│   ├── data_provenance.json         # Dataset fingerprints
│   ├── risk_assessment.json         # Risk declaration (if configured)
│   └── annex_iv_metadata.json       # EU AI Act Annex IV (if configured)
├── audit_log.jsonl                  # Structured event log (Art. 12)
├── benchmark/                       # Benchmark results (if enabled)
└── safety/                          # Safety results (if enabled)
```

## Logs and Monitoring

ForgeLM logs to stderr with structured format:
```
2026-03-24 10:30:00 [INFO] forgelm.trainer: Starting training...
2026-03-24 11:45:00 [WARNING] forgelm.trainer: eval_steps (200) is larger than dataset (50 samples).
```

### TensorBoard

```bash
tensorboard --logdir=./checkpoints/runs/
```

### GaLore (Memory-Efficient Full-Parameter Training)

GaLore provides optimizer-level memory optimization as an alternative to LoRA, enabling full-parameter training via gradient low-rank projection:

```yaml
training:
  galore_enabled: true
  galore_optim: "galore_adamw_8bit"
  galore_rank: 128
  galore_update_proj_gap: 200
  galore_scale: 0.25
  galore_proj_type: "std"
  galore_target_modules: ["q_proj", "k_proj", "v_proj", "o_proj"]
```

### Long-Context Training

Enable extended context window support with RoPE scaling, NEFTune noise injection, sliding window attention, and sample packing:

```yaml
training:
  rope_scaling: "linear"              # "linear" or "dynamic"
  neftune_noise_alpha: 5.0            # NEFTune noise for better generalization
  sliding_window_attention: 4096      # Sliding window size (tokens)
  sample_packing: true                # Pack short samples into full-length sequences
```

### GPU Cost Estimation

ForgeLM auto-detects your GPU model (18 GPU models supported) and tracks estimated cost per training run. Output is included in JSON results, webhook notifications, and model cards:

```
GPU Cost Estimate:
  GPU Model: NVIDIA A100 80GB
  GPU Hours: 2.4
  Estimated Cost: $7.20 USD
  Peak VRAM: 22.1 GB
```

To set a custom cost rate:

```yaml
training:
  gpu_cost_per_hour: 3.00  # USD per GPU-hour
```

### W&B

```yaml
training:
  report_to: "wandb"
  run_name: "my-experiment"
```

### Webhook Notifications

```yaml
webhook:
  url_env: "FORGELM_WEBHOOK_URL"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Docker

```bash
# Build
docker build -t forgelm --build-arg INSTALL_EVAL=true .

# Train
docker run --gpus all \
  -v $(pwd)/config.yaml:/workspace/config.yaml:ro \
  -v $(pwd)/output:/workspace/output \
  forgelm --config /workspace/config.yaml

# Multi-GPU
docker run --gpus all --shm-size=16g \
  forgelm torchrun --nproc_per_node=4 -m forgelm.cli --config /workspace/config.yaml
```
