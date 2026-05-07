---
title: Group Relative Policy Optimization (GRPO)
description: Akıl yürütme için reinforcement learning — yerleşik shaping ile reward fonksiyonuna karşı eğit.
---

# Group Relative Policy Optimization (GRPO)

GRPO, ForgeLM'in reinforcement-learning trainer'ıdır. Model her prompt için birkaç yanıt üretir, reward fonksiyonunuz onları skorlar, GRPO yüksek-reward çıktıları desteklemek için policy'i günceller. Doğrulanabilir doğruluğu olan görevler (matematik, kod) veya programatik kalite sinyalleri için doğru seçim.

## Ne zaman GRPO

| GRPO kullan: | DPO/SimPO kullan: |
|---|---|
| Reward fonksiyonu yazabiliyorsunuz (math grader, test runner). | Kalite sinyali sadece insan tercihleri. |
| Görevlerin doğrulanabilir doğru cevabı var. | Açık uçlu görevler ("pazarlama maili yaz"). |
| Doğruluk dışında format-shaping reward istiyorsunuz. | Kararlı, çalışılmış eğitim dinamiği. |
| Reasoning model kuruyorsunuz. | Chat asistanı kuruyorsunuz. |

```mermaid
flowchart LR
    A[Prompt] --> B[N yanıt örnekle]
    B --> C[Her birini reward<br/>fn ile skorla]
    C --> D[Group-relative<br/>advantage hesapla]
    D --> E[Policy güncelle]
    E --> A
    classDef step fill:#1c2030,stroke:#f97316,color:#e6e7ec
    classDef io fill:#161a24,stroke:#0ea5e9,color:#e6e7ec
    class A,E io
    class B,C,D step
```

## Hızlı örnek

```yaml
model:
  name_or_path: "./checkpoints/sft-base"
  max_length: 4096

lora:
  r: 16
  alpha: 32
  method: "lora"
  target_modules: ["q_proj", "k_proj", "v_proj", "o_proj"]

data:
  dataset_name_or_path: "data/math-prompts.jsonl"

training:
  trainer_type: "grpo"
  num_train_epochs: 1
  per_device_train_batch_size: 1
  learning_rate: 1.0e-6
  grpo_num_generations: 8         # prompt başına örnek — düz field
  grpo_max_completion_length: 512 # üretim başına üst sınır
  grpo_reward_model: "my_reward.score"  # import edilebilir callable; ForgeLM yerleşik format/length fallback'i ship eder
  output_dir: "./checkpoints/grpo"
```

Yerleşik format/length reward shaping fallback olarak her zaman aktiftir (`forgelm/grpo_rewards.py`); `grpo_reward_model`'i yalnızca domain-spesifik bir scorer'ınız varsa set edin. TRL-tarafı `beta` (KL gücü) TRL varsayılanlarına bağlı — Phase 28+ backlog'u bunu düz field olarak yüzeylemeyi takip ediyor.

```python
# my_reward.py
def score(prompt: str, response: str, ground_truth: str) -> float:
    answer = parse_number(response)
    if answer is None:
        return -0.5
    return 1.0 if abs(answer - float(ground_truth)) < 1e-6 else -1.0
```

## Yerleşik format shaping

ForgeLM şunları ödüllendiren varsayılan reward shaper ile gelir:
- **Format uyumu** — çıktı beklenen formatla biten net cevapla bitiyor (ör. matematik için `\boxed{...}`).
- **Uzunluk uyumu** — ne çok kısa ne dağılarak uzun.
- **Akıl yürütme yapısı** — son cevaptan önce chain-of-thought.

```yaml
training:
  grpo:
    reward_function: "my_reward.score"   # %80 ağırlık
    format_reward: 0.2                   # %20 shaper
    answer_pattern: '\\boxed\\{(.*?)\\}' # "son cevap" regex'i
```

## Parametreler

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `group_size` | int | `8` | Prompt başına örneklenen yanıt. Yüksek = kararlı advantage, çok compute. |
| `beta` | float | `0.04` | KL düzenlemesi. GRPO'nunki DPO'dan çok küçük çünkü gradient sinyali güçlü. |
| `reward_function` | string | `null` | Reward fonksiyonunuza dotted path. |
| `format_reward` | float | `0.0` | Yerleşik format shaper ağırlığı. `0.2` mantıklı. |
| `answer_pattern` | string | `null` | "Son cevap"ı çıkarmak için regex. |
| `temperature` | float | `0.9` | Sampling sıcaklığı. Yüksek = çeşitli yanıtlar. |
| `max_completion_length` | int | `2048` | Üretilen yanıt uzunluğu sınırı. |

## Bellek

GRPO en ağır trainer:
- Prompt başına `group_size` yanıt üretir (varsayılan 8) — DPO'nun 8× inference maliyeti.
- Bellekte referans model tutar.
- Reward computation ek model yükleyebilir.

| Model | LoRA | `group_size` | VRAM (QLoRA) |
|---|---|---|---|
| 7B | evet | 8 | 18 GB |
| 13B | evet | 8 | 28 GB (40 GB gerekir) |
| 7B | hayır | 8 | ZeRO-3 gerekir |

## Sık hatalar

:::warn
**Yanlış ölçekte reward.** `[0, 1]` (veya `[-1, 1]`) en iyi çalışır. Sınırsız reward (ör. `correct ? 1000 : 0`) gradient patlamasına yol açar. Mantıklı sınırlı aralığa normalize edin.
:::

:::warn
**Çok küçük `group_size`.** `group_size=2` ile GRPO'nun group-relative advantage tahmininin istatistiksel gücü yok. En az 4, kararlılık için 8+.
:::

:::warn
**Önce SFT yok.** Base modelde GRPO nadir yararlı sonuç verir — model formatı bile çıkaramaz, neredeyse her örnek minimum reward alır. Önce format için SFT, sonra doğruluk için GRPO.
:::

:::danger
**Reward hacking.** Model reward fonksiyonunuzdaki istem dışı pattern'leri sömürür. Sık vakalar:
- Chain-of-thought uzunluğunu ödüllendirme → model sonsuz yazar.
- Son cevabın tam-string eşleşmesini ödüllendirme → model başka şey çıkarmaz.
- "Sözdizim hatası yok"u ödüllendirme → model problemi çözmeyen trivial kod çıkarır.

Eğitimden *önce* reward fonksiyonunuzu adversarial çıktılara karşı test edin. Format shaper yardımcı olur ama tam savunma değildir.
:::

## Bkz.

- [Trainer Seçimi](#/concepts/choosing-trainer) — GRPO ne zaman DPO'yu yener.
- [Otomatik Geri Alma](#/evaluation/auto-revert) — reward-hacking regresyonlarını yakala.
- [Konfigürasyon Referansı](#/reference/configuration).
