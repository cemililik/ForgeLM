---
title: Denetimli Fine-Tuning (SFT)
description: Her alignment hattının temeli — base modeli talimat çiftleri üzerinde eğitin.
---

# Denetimli Fine-Tuning (SFT)

SFT, post-training'in iş atıdır. Modele doğru çıktıların örneklerini verirsiniz, deseni öğrenir. Neredeyse her proje burada başlar; sonu DPO veya GRPO olsa bile.

## Ne zaman SFT

| SFT kullan: | SFT kullanma: |
|---|---|
| Prompt-completion çifti var (en sık şekil). | Sadece tercih çifti var. Doğrudan [DPO](#/training/dpo) (ama aşağıdaki uyarı). |
| Base modelden başlıyorsunuz, format öğretmek gerek. | Zaten SFT eğittiniz; sadece tercih hizalaması gerekli. |
| Basit, kararlı, iyi anlaşılan dinamik istiyorsunuz. | RL stili reward optimizasyonu gerek. [GRPO](#/training/grpo). |

:::tip
Önce SFT, neredeyse her zaman. Zengin tercih verisi olan ekipler bile DPO/SimPO/KTO'dan önce SFT yapar — base modele direkt tercih öğrenme kararsız, formatı bozuk çıktı üretir.
:::

## Hızlı örnek

```yaml
model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: true
  max_length: 4096

lora:
  r: 16
  alpha: 32

datasets:
  - path: "data/train.jsonl"
    format: "messages"

training:
  trainer: "sft"
  epochs: 3
  batch_size: 4
  learning_rate: 2.0e-4
  warmup_ratio: 0.03
  scheduler: "cosine"

output:
  dir: "./checkpoints/sft"
```

```shell
$ forgelm --config configs/sft.yaml --dry-run
$ forgelm --config configs/sft.yaml
```

## Veri formatı

İki format desteklenir. Detay için bkz. [Dataset Formatları](#/concepts/data-formats).

**Tek-tur `instructions`:**
```json
{"prompt": "Fransızcaya çevir: 'Good morning'.", "completion": "Bonjour."}
```

**Multi-turn `messages`:**
```json
{"messages": [
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

## Konfigürasyon parametreleri

SFT-özgü ayarlar standart `training` bloğuyla yan yanadır.

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `learning_rate` | float | `2e-4` | LoRA: 1e-4 - 5e-4. Full-parametre: 1e-5 - 5e-5. |
| `epochs` | int | `3` | Daha çok = daha çok ezberleme, daha az genelleme. |
| `batch_size` | int | `4` | Cihaz başına. Etkili batch için gradient accumulation ile çarpın. |
| `max_length` | int | `4096` | Eğitimdeki context. Uzun = çok VRAM. |
| `packing` | bool | `false` | Kısa dizileri throughput için paketle. %30-50 hız. |
| `neftune_noise_alpha` | float | `null` | Embedding-noise regülarizasyonu. Küçük dataset'lerde `5.0` iyileştirir. |
| `loss_on_completions_only` | bool | `true` | Sadece assistant token'larında loss hesapla. Önerilir. |

Tam parametre listesi: [Konfigürasyon Referansı](#/reference/configuration).

## Compute ve bellek

SFT bellek olarak en hafif post-training paradigmasıdır:

| Model | LoRA rank | `max_length` | Yaklaşık VRAM (QLoRA 4-bit) |
|---|---|---|---|
| 7B | 16 | 4096 | 8 GB |
| 13B | 16 | 4096 | 14 GB |
| 8B Llama 3 | 32 | 8192 | 16 GB |
| 70B | 16 | 2048 | 2× A100 + ZeRO gerekir |

Her zaman göndermeden önce `--fit-check` koşturun.

## Sık yapılan hatalar

:::warn
**Full fine-tune için çok yüksek learning rate.** 2e-4 LoRA'da çalışır ama full-parametre koşusunu eritir. Full FT için 1e-5 - 5e-5'e düşürün.
:::

:::warn
**Loss düşmek yerine artıyor.** Muhtemelen tokenizer uyuşmazlığı — veriniz modelin tokenizer'ındaki chat template'tan farklı format için. `forgelm audit` koşturun ve audit raporundaki render edilmiş örnekleri kontrol edin.
:::

:::warn
**`loss_on_completions_only` etkinleştirmeyi unutmak.** Devre dışıyken model kapasiteyi prompt'u tekrarlamayı öğrenmekle harcar. Varsayılan `true`; sadece olağandışı eğitim-objesi deneyleri için kapatın.
:::

:::tip
**Sample packing dramatik hızlandırır.** Ortalama örneğiniz `max_length`'ten çok kısaysa `packing: true` ayarlayın — kısa örnekleri tek diziye paketler, %30-50 throughput. Talimat ayarı için kalite farkı yok.
:::

## Diskte ne elde edersiniz

Eğitim sonrası:

```text
checkpoints/sft/
├── adapter_model.safetensors      ← LoRA ağırlıkları (LoRA kullanılmıyorsa merged checkpoint)
├── README.md                      ← model kartı
├── config_snapshot.yaml           ← kullanılan tam config
└── artifacts/                     ← uyumluluk kanıtı (compliance.annex_iv etkinse)
```

## Bkz.

- [DPO](#/training/dpo) — SFT'den sonra olağan adım.
- [LoRA, QLoRA, DoRA](#/training/lora) — parametre-verimli SFT.
- [Veri Seti Denetimi](#/data/audit) — SFT'den önce daima.
- [Konfigürasyon Referansı](#/reference/configuration) — tüm eğitim parametreleri.
