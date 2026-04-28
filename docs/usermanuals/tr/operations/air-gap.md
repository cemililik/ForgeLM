---
title: Air-Gap Operasyonu
description: İnternet olmadan eğitim ve değerlendirme — her şeyi önceden cache'leyin, izole ağlarda koşturun.
---

# Air-Gap Operasyonu

Regülasyonlu sektörler (savunma, sağlık, bazı finans) ve yüksek-güvenlikli müşteri ortamları için eğitim, internet erişimi olmayan ağlarda gerçekleşmelidir. ForgeLM tamamen air-gap çalışmak üzere tasarlanmıştır: her internet'e dokunan adımın offline eşdeğeri vardır.

## Online olması gereken (tek sefer)

Air-gap'e geçmeden önce şunları önceden cache'leyin:

| Kaynak | Cache yeri |
|---|---|
| Base model | `~/.cache/huggingface/hub/` |
| Tokenizer | (aynı — modelle birlikte) |
| Llama Guard | `~/.cache/huggingface/hub/` |
| `lm-evaluation-harness` görev tanımları | `~/.cache/lm-evaluation-harness/` |
| Python paketleri (`forgelm` + extra'lar) | yerel pip wheel cache |

Bağlı bir makineden önceden cache'leyin:

```shell
$ forgelm cache-models \
    --model "Qwen/Qwen2.5-7B-Instruct" \
    --safety "meta-llama/Llama-Guard-3-8B" \
    --output ./airgap-bundle/

$ forgelm cache-tasks \
    --tasks hellaswag,arc_easy,truthfulqa,mmlu \
    --output ./airgap-bundle/
```

`airgap-bundle/`'i offline host'a aktarın (USB, scp, ne tür güvenlik politikanız izin veriyorsa).

## Air-gap host üzerinde

Yerel cache'i göstermek ve ağ çağrılarını kapatmak için environment variable'lar:

```shell
$ export HF_HOME="$(pwd)/airgap-bundle/huggingface"
$ export TRANSFORMERS_OFFLINE=1
$ export HF_HUB_OFFLINE=1
$ export HF_DATASETS_OFFLINE=1

$ forgelm --config configs/run.yaml --offline
```

`--offline` bayrağı ForgeLM'e ağ çağrısı yapmamasını söyler. Config'iniz cache'lenmemiş bir modele referans verirse eğitim açık bir hata mesajıyla başarısız olur:

```text
ERROR: model "meta-llama/Llama-Guard-3-8B" not in local cache.
       Bağlı bir makineden önceden cache'leyin: forgelm cache-models --safety meta-llama/Llama-Guard-3-8B
```

## `--offline`'ın zorladığı

| Alt sistem | `--offline` ile davranış |
|---|---|
| HuggingFace Hub indirmeleri | Devre dışı. Model/tokenizer cache'de yoksa hızlı başarısız. |
| W&B / MLflow / Comet | Devre dışı (veya MLflow için file URI ile sadece-yerel). |
| OpenAI / Anthropic judge'lar | Devre dışı. Yerel judge model kullanın. |
| Webhook'lar | Devre dışı (veya `webhook.allow_private` ile iç host'larla sınırlı). |
| Runtime'da pip install | Devre dışı. |
| Telemetry | Yok — ForgeLM zaten asla eve telefon etmez. |

## Yerel sentetik veri

Air-gap'te sentetik veri üretimi gerekirse yerel teacher kullanın:

```yaml
synthetic:
  enabled: true
  teacher:
    provider: "local"
    model: "Qwen/Qwen2.5-72B-Instruct"  # cache'lenmiş olmalı
    load_in_4bit: true
```

OpenAI / Anthropic sağlayıcıları `--offline`'da başarısız olur.

## Yerel LLM-as-judge

```yaml
evaluation:
  judge:
    enabled: true
    judge_model:
      provider: "local"
      model: "Qwen/Qwen2.5-72B-Instruct"
```

72B yerel judge `gpt-4o-mini`'den yavaş ama kalite tipik kullanım için karşılaştırılabilir. Bkz. [LLM-as-Judge](#/evaluation/judge).

## Air-gap'te değerlendirme

`lm-evaluation-harness` genelde görev tanımlarını ve dataset'leri runtime'da indirir. Önceden cache'leyin:

```shell
$ forgelm cache-tasks --tasks hellaswag,arc_easy,truthfulqa,mmlu
```

ForgeLM'i cache kullanacak şekilde konfigüre edin:

```yaml
evaluation:
  benchmark:
    tasks_dir: "${HF_HOME}/lm-evaluation-harness/"
```

## Air-gap modu doğrulama

```shell
$ forgelm doctor --offline
ForgeLM 0.5.2 (offline mod doğrulandı)
✓ HF_HUB_OFFLINE ayarlı
✓ TRANSFORMERS_OFFLINE ayarlı
✓ Yerel cache: airgap-bundle/huggingface (3.4 GB cache'li model)
✓ Llama Guard 3 8B yerel olarak mevcut
✓ lm-evaluation-harness: 4 görev cache'li
```

`forgelm doctor --offline` herhangi bir şeyin erişilemediğini raporlarsa, air-gap operatörünün vaktini boşa harcamadan *önce* düzeltin.

## Paket boyutu tahmini

Tipik bir fine-tuning projesi için:

| Kaynak | Yaklaşık boyut |
|---|---|
| Base model (7B) safetensors | 14 GB |
| Llama Guard 3 8B | 16 GB |
| Tokenizer + config | <100 MB |
| Eval görev tanımları + cache'li dataset'ler | 500 MB - 2 GB |
| Python wheel'ler (forgelm + extra'lar) | 1-2 GB |
| **Toplam** | **~32-34 GB** |

Depolamayı buna göre planlayın.

## Sık hatalar

:::warn
**Environment variable'ları ayarlamayı unutmak.** `HF_HUB_OFFLINE=1` olmadan HuggingFace kütüphaneleri sessizce eve telefon etmeye çalışıp yerel cache'e fallback yapar. Fallback iyi çalışır ama dışarıya bağlantı yapmış olursunuz — bazı ortamlarda compliance ihlali.
:::

:::warn
**Önceden cache'lemeden `--offline` kullanmak.** İlk model yüklemesinde eğitim başarısız olur. Eksik kaynakları önden yakalamak için eğitim başlatmadan önce `forgelm doctor --offline` çalıştırın.
:::

:::tip
**Her şeyi önceden cache'lenmiş bir CI imajı kurun.** Air-gap CI için önceden-cache'li paketi Docker imajına paketleyin. Her CI koşusu cache'lenmiş durumdan başlar. Bkz. [Docker](#/operations/docker).
:::

## Bkz.

- [Docker](#/operations/docker) — önceden-cache'li imaj kurma.
- [Kurulum](#/getting-started/installation) — temel kurulum.
- [LLM-as-Judge](#/evaluation/judge) — yerel judge model.
