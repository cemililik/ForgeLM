---
title: YAML Templates
description: Full working configurations for common workflows — copy, adapt, run.
---

# YAML Templates

These templates are tested as part of CI. Copy any of them, change the names and paths, and run.

## Customer-support assistant (SFT → DPO)

A multi-turn helpful + safe model, the most common production pattern.

```yaml
model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: true
  max_length: 4096

lora:
  r: 16
  alpha: 32
  use_dora: true

datasets:
  - path: "data/customer-support-sft.jsonl"
    format: "messages"
  - path: "data/customer-support-prefs.jsonl"
    format: "preference"
    split: "train"

training:
  trainer: "dpo"
  epochs: 1
  batch_size: 2
  gradient_accumulation_steps: 8
  learning_rate: 5.0e-6
  scheduler: "cosine"
  warmup_ratio: 0.05
  packing: true
  dpo:
    beta: 0.1
    loss_type: "sigmoid"
  report_to: ["tensorboard"]

evaluation:
  benchmark:
    enabled: true
    tasks: ["hellaswag", "arc_easy", "truthfulqa"]
    floors:
      hellaswag: 0.55
      arc_easy: 0.70
      truthfulqa: 0.45
  safety:
    enabled: true
    model: "meta-llama/Llama-Guard-3-8B"
    block_categories: ["S1", "S2", "S5", "S10"]
    severity_threshold: "medium"
  auto_revert:
    enabled: true

compliance:
  annex_iv: true
  data_audit_artifact: "./audit/data_audit_report.json"
  human_approval: true
  intended_purpose: "Customer-support assistant for a Turkish telecom"
  risk_classification: "high-risk"
  deployment_geographies: ["TR", "EU"]
  responsible_party: "Acme Corp <compliance@acme.example>"
  version: "1.2.0"

output:
  dir: "./checkpoints/customer-support-v1.2"
  model_card: true
  webhook:
    url: "${SLACK_WEBHOOK}"
    template: "slack"
    events: ["run_complete", "run_failed", "auto_revert"]
  gguf:
    enabled: true
    quant_levels: ["q4_k_m"]

deployment:
  target: "ollama"
```

## Domain expert from PDFs (SFT only)

For the "fine-tune on our internal documentation" use case.

```yaml
# After running:
#   forgelm ingest ./regulatory-docs/ --recursive --strategy markdown \
#       --pii-mask --secrets-mask --output data/regulatory.jsonl
#   forgelm audit data/regulatory.jsonl

model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: true
  max_length: 8192

lora:
  r: 32
  alpha: 64

datasets:
  - path: "data/regulatory.jsonl"
    format: "instructions"

training:
  trainer: "sft"
  epochs: 3
  batch_size: 2
  gradient_accumulation_steps: 16
  learning_rate: 2.0e-4
  scheduler: "cosine"
  warmup_ratio: 0.03
  packing: true
  neftune_noise_alpha: 5.0

evaluation:
  benchmark:
    enabled: true
    tasks: ["mmlu"]
    floors: { mmlu: 0.48 }
  safety:
    enabled: true
    block_categories: ["S5", "S6"]                 # defamation + specialised advice

compliance:
  annex_iv: true
  intended_purpose: "Regulatory Q&A assistant for compliance team"
  risk_classification: "high-risk"
  deployment_geographies: ["EU", "TR"]
  responsible_party: "Acme Compliance Team"

output:
  dir: "./checkpoints/regulatory-qa"
```

## GRPO math reasoning

```yaml
model:
  name_or_path: "./checkpoints/sft-base"     # SFT first, GRPO second
  max_length: 4096

lora:
  r: 16
  alpha: 32

datasets:
  - path: "data/math-problems.jsonl"
    format: "reward"

training:
  trainer: "grpo"
  epochs: 1
  batch_size: 1
  gradient_accumulation_steps: 4
  learning_rate: 1.0e-6
  scheduler: "constant"
  grpo:
    group_size: 8
    beta: 0.04
    reward_function: "rewards.math_score"
    format_reward: 0.2
    answer_pattern: "\\boxed\\{(.*?)\\}"
    temperature: 0.9

evaluation:
  benchmark:
    enabled: true
    tasks: ["gsm8k"]
    floors: { gsm8k: 0.55 }

output:
  dir: "./checkpoints/math-grpo"
```

```python
# rewards.py
def math_score(prompt: str, response: str, ground_truth: str) -> float:
    import re
    m = re.search(r'\\boxed\{(.*?)\}', response)
    if not m:
        return -0.5
    try:
        return 1.0 if float(m.group(1)) == float(ground_truth) else -1.0
    except ValueError:
        return -0.5
```

## Multi-GPU 70B with ZeRO-3

For training a 70B model across 8× A100 80GB.

```yaml
model:
  name_or_path: "meta-llama/Llama-3.1-70B-Instruct"
  max_length: 4096
  attention_implementation: "flash_attention_2"

lora:
  r: 32
  alpha: 64

datasets:
  - path: "data/train.jsonl"
    format: "messages"

training:
  trainer: "sft"
  epochs: 2
  batch_size: 1
  gradient_accumulation_steps: 16
  learning_rate: 1.0e-4
  scheduler: "cosine"

distributed:
  strategy: "deepspeed"
  zero_stage: 3
  cpu_offload: false                              # all 8 A100s have plenty

evaluation:
  benchmark:
    enabled: true
    tasks: ["mmlu"]
    floors: { mmlu: 0.65 }

output:
  dir: "./checkpoints/llama-70b-finetune"
```

Launch: `accelerate launch --num_processes 8 -m forgelm --config configs/llama-70b.yaml`

## Synthetic data + SFT

Distil GPT-4o into a 7B student.

```yaml
model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: true
  max_length: 4096

datasets:
  - path: "data/seed-prompts.jsonl"
    format: "instructions"
  - path: "data/synthetic.jsonl"                  # generated by --generate-data
    format: "instructions"

training:
  trainer: "sft"
  epochs: 2
  learning_rate: 2.0e-4

synthetic:
  enabled: true
  teacher:
    provider: "openai"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
  seed_prompts: "data/seed-prompts.jsonl"
  output: "data/synthetic.jsonl"
  num_samples: 5000
  temperature: 0.7
  budget_usd: 50.0

output:
  dir: "./checkpoints/distilled"
```

Run:

```shell
$ forgelm --config configs/distill.yaml --generate-data    # creates data/synthetic.jsonl
$ forgelm --config configs/distill.yaml                    # trains on seeds + synthetic
```

## Model merging

Merge three specialist LoRAs into one generalist.

```yaml
merge:
  enabled: true
  algorithm: "ties"
  base_model: "Qwen/Qwen2.5-7B-Instruct"
  models:
    - { path: "./checkpoints/customer-support", weight: 0.4 }
    - { path: "./checkpoints/code-assistant",    weight: 0.3 }
    - { path: "./checkpoints/math-reasoning",    weight: 0.3 }
  parameters:
    threshold: 0.7
  output:
    dir: "./checkpoints/merged"
    model_card: true
  evaluation:
    benchmark:
      tasks: ["mmlu", "humaneval", "gsm8k"]
      floors: { mmlu: 0.50, humaneval: 0.40, gsm8k: 0.50 }
```

```shell
$ forgelm --merge --config configs/merge.yaml
```

## Air-gap-ready customer support

Same as the customer-support template but with everything pre-cached and `--offline` enforced.

```yaml
# configs/customer-support-airgap.yaml
# Pre-requisites: forgelm cache-models / cache-tasks already run

model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"      # must be cached
  load_in_4bit: true

# ... (same training config as customer-support template)

evaluation:
  safety:
    enabled: true
    model: "meta-llama/Llama-Guard-3-8B"        # must be cached
  judge:
    enabled: false                               # OpenAI judge unavailable offline
  trend:
    enabled: true                                # local

compliance:
  audit_log:
    forward_to:
      - type: "syslog"
        host: "audit.internal:514"               # internal-only
        protocol: "tcp"

output:
  webhook:
    url: "https://internal-webhooks.example/forgelm"
    allow_private: true                          # required for internal IPs
```

Run:

```shell
$ HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  forgelm --config configs/customer-support-airgap.yaml --offline
```

## See also

- [Configuration Reference](#/reference/configuration) — every field these templates use.
- [CLI Reference](#/reference/cli) — commands these templates expect.
- [Your First Run](#/getting-started/first-run) — the customer-support template walkthrough.
