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
  teacher_model: "gpt-4o"               # API model adı VEYA HF Hub ID VEYA yerel yol
  teacher_backend: "api"                # "api" | "local" | "file"
  api_base: "https://api.openai.com/v1" # OpenAI-uyumlu endpoint
  api_key_env: OPENAI_API_KEY           # anahtarı taşıyan env var (tercih edilen)
  api_delay: 0.5                        # çağrılar arası saniye (rate-limit dostluğu)
  api_timeout: 60                       # çağrı başı timeout
  seed_file: "data/seeds.jsonl"         # VEYA seed_prompts: ["...", "..."] inline
  system_prompt: ""                     # opsiyonel — her çağrının başına eklenir
  max_new_tokens: 1024                  # yanıt uzunluğu sınırı
  temperature: 0.7
  output_file: "data/synthetic.jsonl"
  output_format: "messages"             # "messages" | "instruction" | "chatml" | "prompt_response"

# Trainer'ın data bloğu üzerinden seed + sentetik birleştirin:
data:
  dataset_name_or_path: "data/seeds.jsonl"
  extra_datasets: ["data/synthetic.jsonl"]
  mix_ratio: [0.6, 0.4]
training:
  trainer_type: "sft"
```

```shell
$ forgelm --config configs/distill.yaml --generate-data
[2026-04-29 14:01:32] gpt-4o'dan üretim
[2026-04-29 14:01:35] 100/<seeds>
[2026-04-29 14:18:55] <seeds>/<seeds>
✓ data/synthetic.jsonl'a <n> satır yazıldı
$ forgelm --config configs/distill.yaml          # normal eğit
```

## Sağlayıcı desteği

`teacher_backend` literal'ı ForgeLM'in teacher'a nasıl ulaştığını kontrol eder. Sağlayıcı whitelist'i yoktur — API yolu, `api_base` üzerinden pinlenmiş herhangi OpenAI-uyumlu endpoint'i kullanır.

| `teacher_backend` | Beklenen | Auth |
|---|---|---|
| `"api"` | Herhangi OpenAI-uyumlu chat-completions endpoint'i (OpenAI, Azure OpenAI, OpenAI-compat shim üzerinden Anthropic, Together, Groq, `--api-key`'li self-hosted vLLM, vb.) | Runtime'da çözülen `api_key_env` |
| `"local"` | In-process yüklenen herhangi HuggingFace causal LM | Yok — yerel inference |
| `"file"` | Önceden üretilmiş teacher yanıtları JSONL'i (reproducibility için replay modu) | Yok |

Yerel üretim için:

```yaml
synthetic:
  enabled: true
  teacher_backend: "local"
  teacher_model: "Qwen/Qwen2.5-72B-Instruct"
  seed_file: "data/seeds.jsonl"
  output_file: "data/synthetic.jsonl"
```

Student-trainer'ın `model.load_in_4bit` knob'ı sentetik teacher'dan **ayrıdır** — `synthetic.teacher.load_in_4bit` yoktur; teacher'ın quantize edilmesi gerekiyorsa `teacher_model`'da pre-quantized bir HF Hub varyantı pin'leyin.

## Maliyet kontrolleri

ForgeLM runtime USD bütçesi uygulamaz. `synthetic.budget_usd` ve `synthetic.rate_limit` bloğu yoktur. Maliyeti şunlarla yönetin:

- **`api_delay`** — çağrılar arası minimum saniye; rate-limit dostluğu olarak da iş görür.
- **`max_new_tokens`** — yanıt uzunluğu tavanı; tek prompt'un 10k-token completion'a sürüklenmesini engeller.
- **Seed-set boyutu** — her seed prompt bir teacher çağrısı olur. `seed_file` boyutunu bütçenizle orantılı tutun.
- **Sağlayıcı-tarafı cap'ler** — throughput / harcama cap'lerini OpenAI / Anthropic / Together dashboard'unuzda set edin, `forgelm`'in zorlamasını beklemek yerine.

Trainer'ın audit log'u her teacher çağrısını model adı ve timestamp ile kaydeder; koşum sonrası maliyeti yeniden inşa etmek için `audit_log.jsonl`'i kullanın.

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
