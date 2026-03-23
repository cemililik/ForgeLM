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
  use_dora: true
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

### Auto-revert bad models

```yaml
evaluation:
  auto_revert: true
  max_acceptable_loss: 2.0
```

If the fine-tuned model's eval loss exceeds the threshold, ForgeLM automatically deletes the adapter and exits with code 3.

---

## Next Steps

- [CI/CD Pipeline Integration](cicd_pipeline.md) — automate training in your pipeline
- [Alignment Guide](alignment.md) — DPO, SimPO, KTO, GRPO
- [Enterprise Deployment](enterprise_deployment.md) — Docker, offline, multi-GPU
- [Safety & Compliance](safety_compliance.md) — EU AI Act, safety evaluation
- [Troubleshooting](troubleshooting.md) — common issues and solutions
