---
title: GaLore
description: LoRA seviyesinde bellek maliyetiyle full-parametre eğitim — gradient'i düşük-rank uzaya projekte ederek.
---

# GaLore

GaLore (**G**radient **L**ow-**R**ank Projection) bir modelin *tüm* parametrelerini eğitir — ama LoRA seviyesindeki bellek maliyetiyle. Optimizer state'in tamamını saklamak yerine GaLore gradient'leri düşük-rank bir alt uzaya projekte eder ve eğitim ilerledikçe bu projeksiyonu periyodik olarak yeniler.

Sonuç: full fine-tune kalitesi, LoRA'ya yakın bellek.

## Ne zaman GaLore

| GaLore tercih edin | LoRA / QLoRA tercih edin |
|---|---|
| Full-parametre eğitim istiyorsunuz ama VRAM dar. | Küçük bir adapter ihtiyacınızı karşılıyor. |
| LoRA yetersiz kalıyor — yakınsamadan önce kalite plato yapıyor. | Rank 32-64 LoRA çıtanızı geçiyor. |
| Adım başına ~%15-20 daha yavaş eğitime razısınız. | Wall-clock hızı ham kaliteden önemli. |
| Her ağırlığın önemli olduğu matematik veya akıl yürütme modeli. | Talimat ayarı yapıyorsunuz. |

## Hızlı örnek

```yaml
model:
  name_or_path: "Qwen/Qwen2.5-7B-Instruct"
  load_in_4bit: false                  # GaLore full precision'ı tercih eder
  max_length: 4096

galore:
  enabled: true
  rank: 256                            # LoRA'dan yüksek — projeksiyon rank'i
  update_proj_gap: 200                 # her N adımda bir yeniden projekte et
  scale: 0.25
  proj_type: "std"                     # std (varsayılan), reverse_std, right, left

training:
  trainer: "sft"
  learning_rate: 1.0e-5                # full-FT learning rate, LoRA'nınki değil
  optimizer: "galore_adamw_8bit"

output:
  dir: "./checkpoints/galore"
```

`galore.enabled: true` iken ForgeLM otomatik olarak GaLore-uyumlu optimizer'ı kullanır; aynı koşuda `lora` blok'unu konfigüre etmeyin.

## Parametreler

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `enabled` | bool | `false` | Ana anahtar. |
| `rank` | int | `256` | Gradient projeksiyon rank'i. Yüksek = full-FT'ye yakın, daha çok bellek. |
| `update_proj_gap` | int | `200` | Yeniden projeksiyon adım aralığı. Düşük = değişen gradient'lere hızlı uyum. |
| `scale` | float | `0.25` | Projekte edilmiş gradient'lerin ölçeği. |
| `proj_type` | string | `"std"` | Projeksiyon yönü. Yakınsama tıkanırsa deneyin. |
| `target_modules` | list | `["attn", "mlp"]` | Hangi modüllerin gradient'leri projekte edilecek. |

## Bellek karşılaştırması

7B model, `max_length: 4096`, batch size 1 için:

| Yöntem | Eğitilebilir param | VRAM (full precision) | VRAM (4-bit base) |
|---|---|---|---|
| Full FT | %100 | 56 GB | yok |
| LoRA r=16 | %0.2 | 18 GB | 9 GB (QLoRA) |
| **GaLore r=256** | **%100** | **22 GB** | yok |

Yani GaLore r=256 ile 7B modeli tek 24 GB GPU'da full fine-tune edebilirsiniz — kabaca full-precision LoRA ile aynı VRAM, ama her ağırlığa erişimle.

## Compute

GaLore adım başına LoRA'dan ~%15-20 daha yavaştır; projeksiyon ve yeniden projeksiyon overhead'i yüzünden. Uçtan uca fark genelde kapanır: GaLore tüm parametre uzayına erişimi olduğundan sıklıkla daha az adımda yakınsar.

## Sık hatalar

:::warn
**GaLore'u LoRA ile birleştirmeye çalışmak.** Bunlar alternatiftir, tamamlayıcı değil. ForgeLM şeması aynı anda `lora.r` ve `galore.enabled` ayarlamayı reddeder.
:::

:::warn
**LoRA learning rate'i kullanmak.** GaLore full-parametre — full-FT learning rate'leri kullanın (1e-5 - 5e-5), LoRA'nınkiler değil (1e-4 - 5e-4). Yanlış LR'da eğitim sapar.
:::

:::warn
**`update_proj_gap`'i çok yüksek ayarlamak.** Seyrek yeniden projeksiyon, gradient alt uzayının optimizasyon yörüngesini takip edememesi anlamına gelir. Varsayılan 200 makul; 500'ün üzerine çıkmayın.
:::

## Bkz.

- [LoRA, QLoRA, DoRA](#/training/lora) — daha sık tercih edilen alternatif.
- [Dağıtık Eğitim](#/training/distributed) — tek GPU'dan büyük modeller için.
- [Konfigürasyon Referansı](#/reference/configuration) — tüm GaLore parametre listesi.
