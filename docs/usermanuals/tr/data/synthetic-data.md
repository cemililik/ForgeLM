---
title: Sentetik Veri
description: Teacher-to-student damıtma — daha güçlü bir modelden eğitim verisi üretin.
---

# Sentetik Veri

Gerçek veri kıt veya pahalı olduğunda ek eğitim örneklerini daha güçlü bir modeli prompt'layıp yanıtlarını yakalayarak sentezleyebilirsiniz. ForgeLM'in sentetik-veri pipeline'ı bunu `forgelm --generate-data` ile yapar.

## Yaygın kullanım senaryoları

| Kullanım | Ürettiğiniz |
|---|---|
| **Damıtma** | Teacher (ör. GPT-4o) cevap verir; student bu cevaplarda eğitilir. |
| **Veri augmentasyonu** | Mevcut verinizden parafraz veya varyasyon. |
| **Soğuk başlangıç** | Birkaç seed prompt'tan sentetik örnek. |
| **Self-instruct** | Hem prompt hem yanıt üretilir. |

## Hızlı örnek

```yaml
synthetic:
  enabled: true
  teacher:
    provider: "openai"                  # veya "anthropic", "local"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
  seed_prompts: "data/seeds.jsonl"      # başlangıç prompt'ları
  output: "data/synthetic.jsonl"
  num_samples: 5000
  temperature: 0.7
  prompt_template: "default"            # veya özel template yolu
  budget_usd: 50.0                      # maliyet tavanı

training:
  trainer: "sft"
datasets:
  - path: "data/seeds.jsonl"
  - path: "data/synthetic.jsonl"        # seed + sentetik birleştir
```

```shell
$ forgelm --config configs/distill.yaml --generate-data
[2026-04-29 14:01:32] gpt-4o'dan üretim
[2026-04-29 14:01:35] 100/5000 (şu ana kadar maliyet: $1.20)
[2026-04-29 14:18:55] 5000/5000 (toplam maliyet: $42.30)
✓ data/synthetic.jsonl'a 5000 satır yazıldı
$ forgelm --config configs/distill.yaml          # normal eğit
```

## Sağlayıcı desteği

| Sağlayıcı | Modeller | Auth env var |
|---|---|---|
| `openai` | gpt-4o, gpt-4o-mini, o1, o3-mini | `OPENAI_API_KEY` |
| `anthropic` | claude-opus-4, claude-sonnet-4, claude-haiku-4 | `ANTHROPIC_API_KEY` |
| `local` | Herhangi HuggingFace causal LM | yok — yerel inference |
| `vllm` | vLLM üzerinden servis edilen herhangi model | `VLLM_BASE_URL` |

Yerel üretim için:

```yaml
synthetic:
  teacher:
    provider: "local"
    model: "Qwen/Qwen2.5-72B-Instruct"
    load_in_4bit: true
```

## Maliyet kontrolleri

API tabanlı üretim hızla maliyet biriktirir. ForgeLM sıkı sınırlar yayınlar:

```yaml
synthetic:
  budget_usd: 50.0                      # sıkı tavan — üretim burada durur
  max_tokens_per_response: 1024         # yanıt uzunluğu sınırı
  rate_limit:
    requests_per_minute: 100            # sağlayıcı rate-limit'lerine saygı
    burst: 10
```

Bütçe dolduğunda ForgeLM kısmi dataset ile durur. Audit log harcanan miktarı tam olarak kaydeder.

## Kalite kontrolleri

Sentetik veri sadece iyiyse faydalı. ForgeLM varsayılanları filtreler:

- **Boş veya tek-token yanıtlar** — API üretim ortasında başarısız oldu; satır düşürüldü.
- **Reddetmeler** — "Bunda yardım edemem" ve benzeri pattern'leri eşleştirir; satır taglenir ama tutulur (güvenlik eğitimi için reddetmeleri tutmak isteyebilirsiniz).
- **Format hataları** — yapılandırılmış prompt'lar için çıktının uyduğunu doğrular.

## Model card'da atıf

Sentetik veri üzerinde eğittiğinizde otomatik üretilen model card teacher'ı atıfla anar:

```markdown
## Eğitim verisi

Bu model şunlar üzerinde eğitildi:
- 12,000 satır insan-küratör verisi (data/seeds.jsonl)
- openai:gpt-4o tarafından üretilen 5,000 satır sentetik veri (2026-04-29)
```

Bu lisans ve ticari kullanım için önemli — bazı teacher'ları damıtmak kaynağı kabul etmeyi gerektirir.

:::warn
**Teacher'ın hizmet şartlarını kontrol edin.** Bazı sağlayıcılar (özellikle bazı modeller için OpenAI) çıktıların rakip model eğitimi için kullanımını kısıtlar. Model-card atıfı bir *gerçek-iddiası*, *lisans-vermesi* değildir. Kullanımınızın izinli olduğunu doğrulayın.
:::

## Sık hatalar

:::warn
**Çok daha küçük student'a teacher damıtma.** 7B student nadiren 405B teacher'ın yeteneklerini yakalar. Gerçekçi oranlar: 70B → 7B çalışır (kalite kaybıyla); 405B → 1.3B çalışmaz.
:::

:::warn
**Kalite filtresiz self-instruct.** Kendi eğitim verisini üreten modeller güvenli, generic çıktılara doğru drift eder. Düşük-kaliteli sentetik satırları filtrelemek için LLM-as-judge ([Judge](#/evaluation/judge)) uygulayın.
:::

:::warn
**`temperature`'ı unutmak.** `temperature=0` deterministik yanıt üretir — aynı prompt'a aynı teacher cevabı. Çeşitlilik için `temperature=0.7` veya yüksek kullanın.
:::

## Bkz.

- [LLM-as-Judge](#/evaluation/judge) — sentetik veri kalitesini filtrele.
- [Konfigürasyon Referansı](#/reference/configuration) — tam `synthetic:` bloğu.
- [Doküman Ingest'i](#/data/ingestion) — sentetik-veri araçlarının tüketmek için kullandığı ham metin JSONL'i üretir.
