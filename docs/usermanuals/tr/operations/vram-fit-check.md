---
title: VRAM Fit-Check
description: Uçuş öncesi bellek tahmini — uzun bir iş başlatmadan önce fits, tight, OOM veya unknown.
---

# VRAM Fit-Check

`--fit-check` config'inizin statik analizini yapar ve peak VRAM'in mevcut GPU'ya sığıp sığmayacağını raporlar. Eğitim olmaz, veri yüklenmez — sadece "OOM olur mu?" sorusunu saniyeler içinde cevaplar.

## Hızlı örnek

```shell
$ forgelm --config configs/customer-support.yaml --fit-check
FITS  est. peak 11.4 GB / 12 GB available

Bileşenler:
  Model ağırlıkları (4-bit):     3.8 GB
  KV cache (max_length=4096):    1.4 GB
  Activations (batch=2):         2.6 GB
  Optimizer state (LoRA):        1.3 GB
  Referans model (DPO):          1.9 GB  ← QLoRA olmadan OOM olurdu
  Buffer (%10):                  0.4 GB
                                 -------
  Toplam tahmini peak:          11.4 GB

Öneriler: yok — bu konfigürasyon sığar.
```

## Verdict'ler

| Verdict | Anlamı | Aksiyon |
|---|---|---|
| `FITS` | VRAM rahat içinde. | Devam edin. |
| `TIGHT` | VRAM içinde ama activation patlamaları için pay yok. | `max_length`'i veya batch size'ı düşürün. |
| `OOM` | Sığmayacak. | Önerilen düzeltmeleri uygulayın. |
| `UNKNOWN` | GPU profil veritabanında değil. | Muhafazakar koşun; GitHub Issues'a bildirin. |

## `OOM` neye benzer

```text
$ forgelm --config configs/large-context.yaml --fit-check
OOM   est. peak 32.4 GB / 24 GB available

Bileşenler:
  Model ağırlıkları (full prec): 14.2 GB
  KV cache (max_length=32768):    6.8 GB     ← en büyük katkı
  ...

Önerilen düzeltmeler (genelde herhangi biri çözer):
  1. QLoRA aç: model.load_in_4bit: true   (~10 GB tasarruf)
  2. max_length düşür: 32768 → 8192       (~5 GB tasarruf)
  3. batch_size düşür: 4 → 2              (~2 GB tasarruf)
  4. DPO yerine SimPO (referans yok)      (~10 GB tasarruf)
  5. distributed.zero_stage: 2 aç         (multi-GPU)
```

## Tahmin edilen bileşenler

| Bileşen | Bağımlı |
|---|---|
| Model ağırlıkları | Model boyutu + precision (full / 8-bit / 4-bit) |
| KV cache | `max_length` × hidden dim × layer × head |
| Activations | `batch_size` × `max_length` × hidden dim |
| Gradients | Model boyutu × precision (veya PEFT ise LoRA rank) |
| Optimizer state | Adam: 2× model boyutu × precision; LoRA: 2× rank × ... |
| Referans model | Sadece DPO/KTO — modelin tam kopyası |
| Reward model | Sadece GRPO |
| Activation peak | Mimari-özgü pattern'lerden tahmin |
| Buffer | %10 güvenlik payı |

## Ne kadar doğru

Empirik olarak, `--fit-check` zamanın ~%95'inde doğru. %5 başarısızlık genelde:

- Olağandışı model mimarileri (sparse expert routing'li MoE).
- Çok yüksek token verimliliğiyle sample packing (beklenenden iyi).
- DeepSpeed offload konfigürasyonları (beklenenden düşük).

Sınırda durumlarda gönül rahatlığı için verdict güven aralığıyla tahmin gösterir:

```text
TIGHT  est. peak 21.8 GB / 24 GB (%95 güven: 19.4 - 23.9 GB)
```

Güven aralığının üst sınırı mevcut VRAM'i aşıyorsa OOM-olası muamelesi yapın.

## Çoklu-GPU

Dağıtık eğitim için fit-check sharding'i hesaba katar:

```shell
$ forgelm --config configs/zero3.yaml --fit-check --gpus 4
FITS  est. peak 14.2 GB / 80 GB GPU başına (4'e shardlı)

ZeRO-3 sharding:
  Optimizer state: GPU başına 1/4
  Gradients: GPU başına 1/4
  Parameters: GPU başına 1/4
```

## Programatik API

Dashboard veya otomasyon için:

```python
from forgelm.fit_check import estimate_peak_memory, available_memory

estimate = estimate_peak_memory(config_path="configs/run.yaml")
available = available_memory()
print(f"Verdict: {estimate.verdict}")
print(f"Peak: {estimate.peak_gb:.1f} GB / {available.total_gb:.1f} GB available")
```

## --fit-check'in yanıldığı yerler

Uç durumlar:

- **Olağandışı MoE routing.** Bazı MoE modellerinin yük desenleri tahminci tarafından modellenmiyor. Kısa kalibrasyon eğitimi koşturup gerçek peak'i karşılaştırın.
- **CPU offload.** `offload_param: cpu` ile ZeRO-3 VRAM'i öngörülemeyecek şekilde düşürür; tahmin muhafazakar (VRAM kullanımını fazla tahmin eder).
- **Çok uzun diziler** (>64K). `O(N²)` attention terimi baskın; uygulamadaki küçük farklar önemli.

Bu durumlar için `--fit-check-strict` kullanın; en kötü durum tahminini kullanır ve median tahmin `FITS` derken bile `TIGHT` raporlar.

## Sık hatalar

:::warn
**"Sanırım sığar" koşularda fit-check'i atlamak.** 5 dakikalık fit-check, eğitime 6 saat kala 6 saatlik OOM'dan sizi kurtarır. Her zaman koşturun.
:::

:::warn
**`TIGHT` verdict'iyle koşturmak.** Tight koşular aralıklı OOM verir — ilk birkaç epoch sığar, sonra özellikle uzun bir dizi activation patlaması tetikler. Ya bir şeyi düşürün ya da çökme için hazır olun.
:::

:::tip
**--dry-run'dan önce fit-check.** Sıra önemli: dry-run modeli indirir (yavaş); fit-check statik analiz (hızlı). Fit-check OOM derse indirmeden tasarruf etmiş olursunuz. Her zaman önce fit-check.
:::

## Bkz.

- [GPU Maliyet Tahmini](#/operations/gpu-cost) — kardeş uçuş öncesi kontrol.
- [Dağıtık Eğitim](#/training/distributed) — tek GPU OOM olduğunda.
- [LoRA, QLoRA, DoRA](#/training/lora) — yaygın OOM çaresi.
