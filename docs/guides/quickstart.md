# Quick Start Guide

Get your first fine-tuned model in 5 minutes.

---

## Prerequisites

- Python 3.10+
- NVIDIA GPU with CUDA (recommended; CPU works but is very slow)

## 1. Install

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -e .

# Recommended: enable 4-bit quantization (Linux)
pip install -e ".[qlora]"
```

## 2. Generate Config

### Option A: Interactive Wizard

```bash
forgelm --wizard
```

The wizard walks you through model selection, LoRA strategy, dataset, and hyperparameters. It generates a ready-to-use YAML config.

### Option B: Copy Template

```bash
cp config_template.yaml my_config.yaml
```

Edit `my_config.yaml` — at minimum set:
```yaml
model:
  name_or_path: "HuggingFaceTB/SmolLM2-1.7B-Instruct"  # or your model

data:
  dataset_name_or_path: "timdettmers/openassistant-guanaco"  # or your dataset
```

## 3. Validate (Dry Run)

```bash
forgelm --config my_config.yaml --dry-run
```

This validates your config, checks model/dataset accessibility, and shows all resolved parameters — without downloading anything heavy.

For machine-readable output:
```bash
forgelm --config my_config.yaml --dry-run --output-format json
```

## 4. Train

```bash
forgelm --config my_config.yaml
```

That's it. ForgeLM handles:
- Model download and quantization
- Dataset formatting with chat templates
- LoRA adapter setup
- Training with early stopping
- Evaluation and model saving
- Model card generation

## 5. Find Your Model

After training, your adapter is saved to:
```
./checkpoints/final_model/
├── adapter_config.json
├── adapter_model.safetensors
├── tokenizer.json
├── tokenizer_config.json
└── README.md  (auto-generated model card)
```

## 5.5 Check GPU Memory Before Training

Before starting a long run, estimate if your config fits in GPU memory:

```bash
forgelm --config my_config.yaml --fit-check
# GPU: RTX 3060 12GB — Estimated peak: 10.8 GB — Verdict: FITS
# Or: Verdict: TIGHT — Enable gradient checkpointing and reduce batch size
# Or: Verdict: UNKNOWN — No GPU detected (hypothetical estimate)
```

Output includes a breakdown (base weights, LoRA adapter, optimizer state, activations) and ordered recommendations when memory is tight. Use `--output-format json` for CI/CD integration.

If you hit OOM during training, the [Troubleshooting guide](troubleshooting.md) has detailed solutions.

## 6. Use Your Model

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained("HuggingFaceTB/SmolLM2-1.7B-Instruct")
model = PeftModel.from_pretrained(base, "./checkpoints/final_model")
tokenizer = AutoTokenizer.from_pretrained("./checkpoints/final_model")

inputs = tokenizer("What is ForgeLM?", return_tensors="pt")
output = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

### Using Your Model (v0.4.0+)

Interact with and deploy your trained model directly:

```bash
# Chat with your fine-tuned model (streaming by default)
forgelm chat ./checkpoints/final_model

# Export to GGUF (for Ollama, LM Studio, llama.cpp)
# Requires: pip install forgelm[export]
forgelm export ./checkpoints/final_model --output model.gguf --quant q4_k_m

# Generate deployment configs (no server is started)
forgelm deploy ./checkpoints/final_model --target ollama --output ./Modelfile
forgelm deploy ./checkpoints/final_model --target vllm --output ./vllm_config.yaml
```

---

## Common Config Tweaks

### Use Unsloth for 2-5x faster training (Linux only)

```bash
pip install -e ".[unsloth]"
```

```yaml
model:
  backend: "unsloth"
```

### Enable DoRA for better quality at same rank

```yaml
lora:
  method: "dora"  # DoRA adapter (better quality than standard LoRA at same rank)
  # Note: lora.use_dora is deprecated; use method: "dora" instead
```

### Add webhook notifications (Slack/Teams)

```yaml
webhook:
  url_env: "FORGELM_WEBHOOK_URL"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

```bash
export FORGELM_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../xxx"
forgelm --config my_config.yaml
```

### Enable OOM recovery (automatic batch size reduction)

```yaml
training:
  per_device_train_batch_size: 8
  gradient_accumulation_steps: 2
  oom_recovery: true
  oom_recovery_min_batch_size: 1
```

### Auto-revert bad models

```yaml
evaluation:
  auto_revert: true
  max_acceptable_loss: 2.0
```

If the fine-tuned model's eval loss exceeds the threshold, ForgeLM automatically deletes the adapter and exits with code 3.

---

### Enable GaLore for memory-efficient full-parameter training

GaLore is an alternative to LoRA that enables full-parameter training via gradient low-rank projection, using significantly less memory:

```yaml
training:
  galore_enabled: true
  galore_optim: "galore_adamw_8bit"
  galore_rank: 128
```

### Generate synthetic training data

Use a teacher model to generate training data before fine-tuning:

```bash
forgelm --config my_config.yaml --generate-data
```

```yaml
synthetic:
  enabled: true
  teacher_model: "gpt-4o"
  teacher_backend: "api"
  teacher_api_key_env: "OPENAI_API_KEY"
  seed_file: "seed_prompts.jsonl"
  output_file: "synthetic_data.jsonl"
  num_samples: 500
```

---

## Next Steps

- [CI/CD Pipeline Integration](cicd_pipeline.md) — automate training in your pipeline
- [Alignment Guide](alignment.md) — DPO, SimPO, KTO, GRPO
- [Enterprise Deployment](enterprise_deployment.md) — Docker, offline, multi-GPU
- [Safety & Compliance](safety_compliance.md) — EU AI Act, safety evaluation
- [Troubleshooting](troubleshooting.md) — common issues and solutions
