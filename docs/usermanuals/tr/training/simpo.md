---
title: Simple Preference Optimization (SimPO)
description: Referans modelsiz tercih öğrenmesi — bellekte ikinci model olmadan DPO.
---

# Simple Preference Optimization (SimPO)

SimPO, DPO'nun sadeleştirilmiş kuzenidir; referans modeli denklemden çıkarır. Ödünleşim: yaklaşık yarı VRAM, biraz daha az kararlılık.

## Ne zaman SimPO

| SimPO kullan: | DPO tercih et: |
|---|---|
| VRAM bütçesi dar (ör. tek 24 GB GPU'da 13B+). | İkinci modeli bellekte tutabiliyorsanız. |
| Temiz referans checkpoint'iniz yok. | SFT checkpoint'iniz yüksek kalite ve güvenilir. |
| Daha basit eğitim dinamiği istiyorsanız. | Kararlılık VRAM'den önemliyse. |

:::tip
Pratik kural: [`--fit-check`](#/operations/vram-fit-check) DPO için `OOM` raporlarsa, daha küçük model veya kısa context düşünmeden önce SimPO'ya geçin. Standart benchmark'larda kalite farkı genelde %5'in altındadır.
:::

## Hızlı örnek

```yaml
model:
  name_or_path: "./checkpoints/sft-base"
  max_length: 4096

datasets:
  - path: "data/preferences.jsonl"
    format: "preference"

training:
  trainer: "simpo"
  epochs: 1
  learning_rate: 8.0e-7
  simpo:
    beta: 2.0                # DPO'nun 0.1'inden farklı
    gamma: 1.0               # margin terimi
    loss_type: "sigmoid"

output:
  dir: "./checkpoints/simpo"
```

## Veri formatı

DPO ile aynı — `prompt`, `chosen`, `rejected` taşıyan `preference` formatı.
Bkz. [Veri Formatları](#/concepts/data-formats).

## Parametreler

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `beta` | float | `2.0` | Uzunluk-normalize ödül ölçeği. Yüksek = güçlü tercih kayması. **DPO beta ile aynı ölçek değil.** |
| `gamma` | float | `1.0` | Margin — chosen ve rejected log-likelihood arasında SimPO'nun korumaya çalıştığı boşluk. |
| `loss_type` | string | `"sigmoid"` | `sigmoid` veya `hinge`. |
| `length_normalize` | bool | `true` | Log-prob'ları dizi uzunluğuna normalize et. SimPO'nun imza özelliği. |
| `label_smoothing` | float | `0.0` | Gürültülü veride yumuşatma. |

## Bellek

~1.2× SFT belleği — DPO'nun 2×'inden çok daha hafif.

| Model | LoRA rank | `max_length` | VRAM (QLoRA 4-bit) |
|---|---|---|---|
| 7B | 16 | 4096 | 9 GB |
| 13B | 16 | 4096 | 16 GB |

## `beta` ve `gamma`

| Kombinasyon | Davranış |
|---|---|
| `beta=2.0`, `gamma=1.0` | Varsayılan. Dengeli. |
| `beta=2.5`, `gamma=1.4` | Daha agresif tercih kayması. |
| `beta=1.5`, `gamma=0.5` | Daha yumuşak, orijinal SFT çıktılarına yakın. |

:::warn
SimPO'nun `beta`'sı DPO'nun `beta`'sından farklı ölçekte. DPO hyperparam'larını kopyalamayın — SimPO varsayılanlarından başlayın.
:::

## Sık hatalar

:::warn
**Beta'da aşırıya kaçma.** SimPO DPO'dan daha duyarlıdır; yüksek `beta` + küçük dataset chosen'ı agresif tercih eden ama genel yetenek kaybeden model üretir. Eğitim sırasında benchmark puanlarınızı izleyin.
:::

:::warn
**SFT'siz SimPO.** DPO ile aynı uyarı — kaliteli SFT checkpoint'ten başlayın, ham base modelden değil.
:::

## Bkz.

- [DPO](#/training/dpo) — referans-tabanlı kuzen.
- [ORPO](#/training/orpo) — SFT ve tercih kaybını tek aşamada.
- [Konfigürasyon Referansı](#/reference/configuration).
