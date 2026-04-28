---
title: Kahneman-Tversky Optimization (KTO)
description: Eşli karşılaştırma değil ikili thumbs-up/down geri bildiriminden tercih hizalaması.
---

# Kahneman-Tversky Optimization (KTO)

KTO, modeli ikili geri bildirim üzerinde eğitir — eşli chosen/rejected karşılaştırmaları yerine tek yanıta thumbs-up/down. Geri bildirim toplamanız tek-yanıt yargıları üretiyorsa kullanın; bu, üretimde A/B karşılaştırmasından çok daha yaygındır.

## Ne zaman KTO

| KTO kullan: | DPO/SimPO kullan: |
|---|---|
| Tek yanıtlara kullanıcı thumbs-up/down. | Yan yana `(chosen, rejected)` çiftleri. |
| Annotasyon bütçeniz eşli karşılaştırmaya yetmez. | Annotatörler çiftleri yan yana puanlıyor. |
| Geri bildirim üretim telemetry'sinden geliyor. | Geri bildirim labelling oturumlarından. |

KTO'nun loss'u prospect theory üzerine kurulu — Kahneman-Tversky'nin orijinal psikoloji çalışmasının arkasındaki teori. Model, istenen yanıtların utility'sini maksimize, istenmeyenlerinkini minimize eder; eşli görmeden.

## Hızlı örnek

```yaml
model:
  name_or_path: "./checkpoints/sft-base"
  max_length: 4096

datasets:
  - path: "data/feedback.jsonl"
    format: "binary"

training:
  trainer: "kto"
  epochs: 1
  learning_rate: 5.0e-7
  kto:
    beta: 0.1
    desirable_weight: 1.0
    undesirable_weight: 1.0
```

## Veri formatı

```json
{"prompt": "Aboneliği nasıl iptal ederim?", "response": "Sadece ödemeyi durdur.", "label": false}
{"prompt": "Aboneliği nasıl iptal ederim?", "response": "Ayarlar → Faturalandırma…", "label": true}
```

KTO her iki sınıftan da örnek bekler — minimum %5-10 azınlık sınıfı. Üretim telemetry'si genelde %99 thumbs-up / %1 thumbs-down olduğundan KTO nadir sınıfta sinyal bulmakta zorlanır.

## Parametreler

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `beta` | float | `0.1` | KL gücü, DPO ile aynı rol. |
| `desirable_weight` | float | `1.0` | Thumbs-up satırlarını loss'ta yukarı ağırla. |
| `undesirable_weight` | float | `1.0` | Thumbs-down satırlarını yukarı ağırla. |
| `loss_type` | string | `"sigmoid"` | `sigmoid` veya `kto-pair`. |

:::tip
**Dengesiz veri?** `undesirable_weight: 5.0` (veya dengesizliğinize uyacak oranı) ayarlayarak nadir sınıf sinyalini güçlendirin. JSONL'i over-sample etmeyin — loss ağırlıkları yapsın.
:::

## Bellek

~1.5× SFT belleği — DPO gibi referans tutar ama tek satırları işler.

## KTO'nun şaşırttığı yerler

KTO genelde gerçek-dünya thumbs-up/down telemetry'sinde DPO'dan *daha iyi* yapar; aynı veri eşlere yeniden şekillendirilmiş olsa bile. İki neden:

1. Zorla eşleştirme spurious karşılaştırmalar yaratır — bir prompt'ta thumbs-up, farklı prompt'ta thumbs-down aynı şeyin "tercih edilen vs reddedilen"i değil.
2. Üretim telemetry'si dengesiz; KTO'nun sınıf-başı ağırlıkları bunu daha doğal işler.

## Sık hatalar

:::warn
**`label: 1/0`'ı `true/false` gibi muamele.** Integer değil, JSON booleanları (`true`/`false`) kullanın. KTO için integer label reddedilir.
:::

:::warn
**Tek-sınıf veri.** Satırlarınızın %100'ü `label: true` ise KTO'nun karşı koyacak bir şey yok. Eğitim koşar ama neredeyse aynı modeli üretir.
:::

## Bkz.

- [DPO](#/training/dpo) — eşli tercih kuzen.
- [Dataset Formatları](#/concepts/data-formats) — `binary` formatı.
- [Trainer Seçimi](#/concepts/choosing-trainer) — karar ağacı.
