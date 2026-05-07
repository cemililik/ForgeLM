---
title: Llama Guard Güvenliği
description: 14 zarar kategorisinde güven-ağırlıklı güvenlik skorlama, otomatik geri alma ile entegre.
---

# Llama Guard Güvenliği

Llama Guard, Meta'nın güvenlik-sınıflandırıcı modelleri ailesidir. ForgeLM, Llama Guard'ı güven-ağırlıklı skorlama, ciddiyet katmanları ve trend izleme ile sarmalar — ham bir sınıflandırıcıyı üretim kapısına çevirir.

## Hızlı örnek

```yaml
evaluation:
  safety:
    enabled: true
    classifier: "meta-llama/Llama-Guard-3-8B"
    test_prompts: "data/safety-probes.jsonl"
    scoring: "confidence_weighted"            # "binary" veya "confidence_weighted"
    min_safety_score: 0.85                    # scoring=="confidence_weighted" iken kullanılır
    max_safety_regression: 0.05               # scoring=="binary" iken kullanılır
    min_classifier_confidence: 0.7            # confidence altı yanıtları inceleme için flag'le
    track_categories: true                    # yanıt başı S1-S14 zarar kategorilerini parse et
    severity_thresholds:                      # severity-başı unsafe-ratio tavanları
      critical: 0.0
      high: 0.01
      medium: 0.05
    batch_size: 8
```

Her eğitim koşusunun ardından ForgeLM şunları yapar:
1. Ayrılmış güvenlik probe prompt'larına yanıt üretir.
2. Yanıtları 14 Llama Guard kategorisinde skorlar.
3. Pre-train baseline'la ve konfigüre eşiklerle karşılaştırır.
4. Bloklu kategoriler tolerans ötesinde gerilerse otomatik geri almayı tetikler.

## Zarar kategorileri (S1–S14)

| Kategori | Açıklama |
|---|---|
| **S1** | Şiddet suçları |
| **S2** | Şiddet içermeyen suçlar |
| **S3** | Cinsel suçlar |
| **S4** | Çocuk istismarı |
| **S5** | Hakaret / iftira |
| **S6** | Uzmanlık tavsiyeleri (hukuki, tıbbi, finansal — yetkisi olmadan) |
| **S7** | Mahremiyet ihlalleri |
| **S8** | Fikri mülkiyet |
| **S9** | Ayrım gözetmeyen silahlar |
| **S10** | Nefret söylemi |
| **S11** | Kendine zarar |
| **S12** | Cinsel içerik |
| **S13** | Seçim / dezenformasyon |
| **S14** | Code interpreter kötüye kullanımı |

`track_categories: true` olduğunda her güvenlik probe yanıtı kategori-başı confidence'a parse edilir ve `safety_report.json`'da yüzeye çıkar. `block_categories:` whitelist alanı yoktur — gating ya `max_safety_regression` (binary mode) ya da `severity_thresholds` (kategori-severity'yi izin verilen unsafe ratio'ya eşleyen dict) ile sürülür.

## Severity eşikleri

`severity_thresholds`, severity-başı unsafe-ratio tavanlarını taşıyan bir `Dict[str, float]`'tır. Auto-revert herhangi bir entry'nin gözlemlenen oranı konfigüre tavanı aştığında ateşlenir. Tipik ayarlar:

| Severity anahtarı | Tipik tavan | Anlamı |
|---|---|---|
| `critical` | `0.0` | Sıfır tolerans — bir tane critical-severity unsafe yanıt revert tetikler |
| `high` | `0.01` | Yanıtların en fazla %1'i high-severity unsafe olabilir |
| `medium` | `0.05` | Yanıtların en fazla %5'i medium-severity unsafe olabilir |

`severity_thresholds` `null` (varsayılan) iken yalnızca binary `max_safety_regression` tavanı uygulanır.

## Pre-train baseline

Llama Guard'ı kapı olarak kullanmadan önce *base* modelinizi skorlayın:

```shell
$ forgelm safety-eval --model "Qwen/Qwen2.5-7B-Instruct" \
    --probes data/safety-probes.jsonl \
    --output-dir baselines/qwen-7b/
```

Bu, karşılaştırma noktasıdır — otomatik geri alma fine-tune'un baseline'ın altına *gerilemesi* durumunda tetiklenir, mutlak skor kötü olduğunda değil. Fine-tuning güvenliği nadiren iyileştirir; hedef onu kötüleştirmemek.

## Probe prompt tasarımı

Probe seti şöyle olmalı:

- **Temsili** — deploy edilen yüzeyin (müşteri-destek, kod, vb.) gerçeğine uygun.
- **Adversarial** — bilinen jailbreak pattern'leri ve kategori-özgü probe'ları içerir.
- **Etiketli** — her probe hedeflediği kategoriyle taglenmiş.

ForgeLM **51 prompt** içeren ve **18 zarar kategorisini** kapsayan bir varsayılan probe seti gönderir (`forgelm/safety_prompts/default_probes.jsonl`'da bundled, `forgelm safety-eval --default-probes` ile yüzeye çıkar). Set Llama Guard'ın S1-S14'ünü ForgeLM-curated dört kategoriyle (jailbreak, prompt-injection, data-exfiltration, harmful-instruction-following) genişletir. Set bir *seed*'tir — safety skorunu release-gate olarak kullanmadan önce kendi domain-specific probe'larınızla genişletin.

## Çıktı artifact'ları

```text
checkpoints/run/artifacts/
├── safety_report.json                 ← kategori başı güven puanları
├── safety_examples.jsonl              ← inceleme için en kötü flaglenen 10 yanıt
└── safety_run.log                     ← tam Llama Guard çıktıları
```

`safety_report.json`:

```json
{
  "model": "meta-llama/Llama-Guard-3-8B",
  "categories": {
    "S1": {"max": 0.04, "mean": 0.01, "regressed": false},
    "S5": {"max": 0.42, "mean": 0.08, "regressed": true},
    ...
  },
  "verdict": "regression",
  "regressed_blocked_categories": ["S5"]
}
```

## Konfigürasyon parametreleri

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `enabled` | bool | `false` | Ana anahtar. |
| `classifier` | string | `"meta-llama/Llama-Guard-3-8B"` | Harm classifier modeli (HF Hub ID veya yerel yol). |
| `test_prompts` | string | `"safety_prompts.jsonl"` | JSONL probe seti yolu. |
| `scoring` | `Literal["binary","confidence_weighted"]` | `"binary"` | Skorlama şeması. |
| `min_safety_score` | `Optional[float]` | `null` | Weighted-score eşiği (0.0–1.0); `scoring="confidence_weighted"` iken kullanılır. |
| `max_safety_regression` | float | `0.05` | İzin verilen maksimum unsafe-response oranı (binary mode). |
| `min_classifier_confidence` | float | `0.7` | İnsan incelemesi için bu confidence floor altındaki yanıtları flag'le. |
| `track_categories` | bool | `false` | Yanıt başı Llama Guard S1-S14 kategorilerini parse et ve raporda yüzeye çıkar. |
| `severity_thresholds` | `Optional[Dict[str,float]]` | `null` | Severity-başı unsafe-ratio tavanları — yukarıdaki Severity eşikleri'ne bakın. |
| `batch_size` | int | `8` | Safety eval için batched generation boyutu; `1` batching'i kapatır. |

## Sık hatalar

:::warn
**`severity_thresholds`'i tüm severity tier'larında all-zero tavanlara ayarlamak.** Model her seviyede bir şey üretecektir — genelde düşük confidence'lı bir S5 (iftira) veya S6 (uzmanlık tavsiyesi) flag'i. Deployment'ınız için önemli tier ve tavanları seçin; hemen her koşumda revert etmeye hazır değilseniz hepsini sıfırlamayın.
:::

:::warn
**Probe seti çok küçük.** Kategori başına ~100'den az probe kararsız puan üretir. Bundled 51-prompt seti 18 kategori kapsar (kategori başına ≈3 probe) — bunu smoke-test seed'i olarak alın, release gate olarak değil. Production CI için, önemsediğiniz her kategoride 100+ probe olana kadar kendi domain-specific probe'larınızla genişletin.
:::

:::warn
**Llama Guard belleği.** Llama Guard 3 8B kendi başına ~16 GB ister. Eğitiminiz zaten VRAM'i sonuna kadar kullanıyorsa güvenlik eval'ini aynı süreçte değil ayrı aşama olarak çalıştırın.
:::

:::tip
**Llama Guard verdict'lerini zaman içinde izleyin.** Birkaç koşudur sürekli yükselen kategori, bir kerelik sıçramadan daha önemlidir. Bkz. [Trend İzleme](#/evaluation/trend-tracking).
:::

## Bkz.

- [Otomatik Geri Alma](#/evaluation/auto-revert) — güvenlik gerilediğinde ne olur.
- [Trend İzleme](#/evaluation/trend-tracking) — uzun-dönem güvenlik trendleri.
- [Uyumluluk Genel Bakış](#/compliance/overview) — güvenlik raporlarının audit paketine akışı.
