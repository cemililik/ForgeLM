---
title: YAML Şablonları
description: Yaygın iş akışları için tam çalışan konfigürasyonlar — kopyala, uyarla, koştur.
---

# YAML Şablonları

Bu şablonlar CI'da test ediliyor. Birini kopyalayın, isim ve yolları değiştirin, koşturun.

## Müşteri-destek asistanı (SFT → DPO)

Multi-turn yardımsever + güvenli model — en yaygın üretim pattern'i.

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
  intended_purpose: "Türk telekomu için müşteri-destek asistanı"
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

## PDF'lerden alan uzmanı (sadece SFT)

"İç dokümanlarımız üzerinde fine-tune et" senaryosu için.

```yaml
# Önce çalıştırın:
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
    block_categories: ["S5", "S6"]                 # iftira + uzmanlık tavsiyesi

compliance:
  annex_iv: true
  intended_purpose: "Compliance ekibi için regülasyon Q&A asistanı"
  risk_classification: "high-risk"
  deployment_geographies: ["EU", "TR"]
  responsible_party: "Acme Compliance Team"

output:
  dir: "./checkpoints/regulatory-qa"
```

## GRPO matematik akıl yürütme

```yaml
model:
  name_or_path: "./checkpoints/sft-base"     # önce SFT, sonra GRPO
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

## ZeRO-3 ile çoklu-GPU 70B

8× A100 80GB üzerinde 70B model eğitmek için.

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
  cpu_offload: false                              # 8 A100 yeterli

evaluation:
  benchmark:
    enabled: true
    tasks: ["mmlu"]
    floors: { mmlu: 0.65 }

output:
  dir: "./checkpoints/llama-70b-finetune"
```

Başlatma: `accelerate launch --num_processes 8 -m forgelm --config configs/llama-70b.yaml`

## Sentetik veri + SFT

GPT-4o'yu 7B student'a damıt.

```yaml
model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: true
  max_length: 4096

datasets:
  - path: "data/seed-prompts.jsonl"
    format: "instructions"
  - path: "data/synthetic.jsonl"                  # --generate-data ile üretildi
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

Çalıştır:

```shell
$ forgelm --config configs/distill.yaml --generate-data    # data/synthetic.jsonl üretir
$ forgelm --config configs/distill.yaml                    # seed + sentetik üzerinde eğitir
```

## Model birleştirme

Üç uzman LoRA'yı tek generalist'e birleştir.

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

## Air-gap'e hazır müşteri destek

Müşteri-destek şablonuyla aynı, ama her şey önceden cache'lenmiş ve `--offline` zorlanmış.

```yaml
# configs/customer-support-airgap.yaml
# Ön gereksinim: forgelm cache-models / cache-tasks zaten koşturuldu

model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"      # cache'lenmiş olmalı
  load_in_4bit: true

# ... (müşteri-destek şablonuyla aynı eğitim config'i)

evaluation:
  safety:
    enabled: true
    model: "meta-llama/Llama-Guard-3-8B"        # cache'lenmiş olmalı
  judge:
    enabled: false                               # OpenAI judge offline'da yok
  trend:
    enabled: true                                # yerel

compliance:
  audit_log:
    forward_to:
      - type: "syslog"
        host: "audit.internal:514"               # sadece-iç
        protocol: "tcp"

output:
  webhook:
    url: "https://internal-webhooks.example/forgelm"
    allow_private: true                          # iç IP'ler için gerekli
```

Çalıştır:

```shell
$ HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  forgelm --config configs/customer-support-airgap.yaml --offline
```

## Bkz.

- [Konfigürasyon Referansı](#/reference/configuration) — bu şablonların kullandığı her alan.
- [CLI Referansı](#/reference/cli) — bu şablonların beklediği komutlar.
- [İlk Koşunuz](#/getting-started/first-run) — müşteri-destek şablonu adım adım.
