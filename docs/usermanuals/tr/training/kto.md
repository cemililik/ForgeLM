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

lora:
  r: 16
  alpha: 32
  method: "lora"
  target_modules: ["q_proj", "k_proj", "v_proj", "o_proj"]

data:
  dataset_name_or_path: "data/feedback.jsonl"

training:
  trainer_type: "kto"
  num_train_epochs: 1
  per_device_train_batch_size: 2
  learning_rate: 5.0e-7
  kto_beta: 0.1                  # düz field — KTO'nun tek zorunlu tuning ayarı
  output_dir: "./checkpoints/kto"
```

TRL'in `KTOConfig` `desirable_weight` / `undesirable_weight` ayarları ForgeLM config field'ı olarak yüzeylenmedi; trainer TRL varsayılanlarını (1.0 / 1.0) kullanır. Asimetrik ağırlıklandırmaya ihtiyacı olan operatörler bunu TRL-tarafı bir override script'i ile bağlar (Phase 28+ backlog'u).

## Veri formatı

```json
{"prompt": "Aboneliği nasıl iptal ederim?", "completion": "Sadece ödemeyi durdur.", "label": false}
{"prompt": "Aboneliği nasıl iptal ederim?", "completion": "Ayarlar → Faturalandırma…", "label": true}
```

KTO her iki sınıftan da örnek bekler — minimum %5-10 azınlık sınıfı. Üretim telemetry'si genelde %99 thumbs-up / %1 thumbs-down olduğundan KTO nadir sınıfta sinyal bulmakta zorlanır.

## Parametreler

ForgeLM'de KTO'nun tek yapılandırılabilir knob'u `training.kto_beta`'dır (flat field, nested `training.kto:` bloğu yok):

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `training.kto_beta` | float | `0.1` | KL gücü, DPO'nun `dpo_beta`'sı ile aynı rol. |
| `training.trainer_type` | string | `"sft"` | KTO eğitim yolunu açmak için `"kto"` olarak set edin. |

`desirable_weight`, `undesirable_weight` ve `loss_type` ForgeLM config field'ı olarak sunulmaz. TRL'in `KTOTrainer`'ı kütüphane varsayılanlarıyla çalışır (1.0 / 1.0 ağırlıklar, sigmoid loss). Dengesiz veri için, JSONL'de azınlık sınıfını oversample edin veya TRL-tarafı bir override script'i kullanın — loss-weight knob'u Phase 28+ backlog'unda.

:::tip
**Dengesiz veri?** Per-class weighting yüzeylenene kadar JSONL'inizde azınlık sınıfını oversample edin (ör. thumbs-down satırlarını veri setinin %30-40'ına ulaşacak şekilde çoğaltın). `undesirable_weight` knob'unun var olmasını beklemeyin.
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
