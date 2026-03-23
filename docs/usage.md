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
