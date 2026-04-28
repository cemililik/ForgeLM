---
title: LLM-as-Judge
description: OpenAI veya yerel judge modeliyle kalite skorlama — pairwise, single-rubric veya ELO.
---

# LLM-as-Judge

Standart benchmark'lar dar yetenekleri ölçer; "bu yanıt gerçekten iyi mi?" sorusunu yakalamaz. LLM-as-judge bu boşluğu, daha güçlü bir modeli sizinkini değerlendirmek için kullanarak doldurur. ForgeLM üç mod destekler: pairwise karşılaştırma, single-rubric skorlama ve ELO sıralaması.

## Ne zaman kullan

| LLM-as-judge: | Benchmark: |
|---|---|
| Çıktı kalitesi öznel (yardımsever, kibar, marka-uyumlu). | Görevin doğrulanabilir cevabı var. |
| Ground truth yok. | Ground truth var. |
| İki modelin nitel çıktısını karşılaştırıyorsunuz. | Mutlak performansı zaman içinde izliyorsunuz. |
| Maliyet kabul edilebilir (GPT-4o-mini ile ~$1-5 / 1K judgement). | Ücretsiz, yerel eval gerek. |

## Hızlı örnek

```yaml
evaluation:
  judge:
    enabled: true
    mode: "pairwise"                    # veya single-rubric, elo
    judge_model:
      provider: "openai"
      model: "gpt-4o-mini"               # gpt-4o'dan ucuz, judging için neredeyse aynı kalitede
      api_key: "${OPENAI_API_KEY}"
    baseline_model: "./checkpoints/sft-base"
    test_prompts: "data/eval-prompts.jsonl"
    num_samples: 200
    rubric: "default"                   # veya özel rubric yolu
```

## Pairwise mod

Judge'a sorar: "Yanıt A mı yanıt B mi — hangisi daha iyi, neden?" Win-rate'leri toplar.

```json
{
  "pairwise_results": {
    "wins": 124,
    "losses": 56,
    "ties": 20,
    "win_rate": 0.62,
    "judge_explanations_sample": [...]
  }
}
```

200+ örnekle 0.55 üstü win rate istatistiksel olarak anlamlıdır. Altında daha çok örnek koşturun veya farkın gürültü olduğunu kabul edin.

## Single-rubric mod

Judge'dan her yanıtı bir rubric üzerinde puanlamasını ister (kriter başına 1-5 yıldız).

```yaml
evaluation:
  judge:
    mode: "single-rubric"
    rubric:
      criteria:
        - name: "yardımseverlik"
          description: "Yanıt kullanıcının problemini çözüyor mu?"
          scale: 5
        - name: "ton"
          description: "Müşteri destek için ton uygun mu?"
          scale: 5
        - name: "doğruluk"
          description: "İddialar doğru mu?"
          scale: 5
```

Çıktı:

```json
{
  "rubric_means": {
    "yardımseverlik": 4.2,
    "ton": 4.7,
    "doğruluk": 3.8
  }
}
```

## ELO mod

Birden çok model sürümü arasında round-robin pairwise karşılaştırmalar koşturur, ELO puanları hesaplar.

```yaml
evaluation:
  judge:
    mode: "elo"
    candidates:
      - { name: "v1", path: "./checkpoints/v1" }
      - { name: "v2", path: "./checkpoints/v2" }
      - { name: "v3-current", path: "./checkpoints/v3" }
    rounds: 50
```

Çıktı: aday başına ELO puanları. Çok koşu arası karşılaştırma için faydalı (ör. hyperparameter sweep).

## Judge model seçimi

| Judge | Maliyet / 1K judgement | Kalite |
|---|---|---|
| `openai:gpt-4o` | ~$5 | En yüksek. Üretim için varsayılan. |
| `openai:gpt-4o-mini` | ~$1 | gpt-4o'nun %90 kalitesi. **Önerilir.** |
| `anthropic:claude-haiku-4` | ~$1.50 | gpt-4o-mini ile karşılaştırılabilir. |
| `local:Qwen2.5-72B-Instruct` | $0 (kendi GPU zamanınız) | Makul; ince yargı çağrılarında daha zayıf. |
| `local:Llama-3.1-70B-Instruct` | $0 | Judging için Qwen 72B'den biraz kötü. |

## Varyansı azaltma

Tek judge koşuları gürültülü. ForgeLM standart varyans-azaltma yayınlar:

- **Self-consistency** — `--num-judgements 3` her karşılaştırmayı üç kez koşturur, çoğunluk alır.
- **Pozisyon swap** — pozisyon önyargısını tespit etmek için A/B'yi değiştirir.
- **Çoklu rubric** — kriterler arası ortalama alır.

```yaml
evaluation:
  judge:
    self_consistency: 3                 # karşılaştırma başına 3 oy
    swap_positions: true                # pozisyon önyargısı tespit
```

## Maliyet kontrolleri

```yaml
evaluation:
  judge:
    budget_usd: 20.0                    # $20'da dur
    rate_limit:
      requests_per_minute: 60
```

Bütçe dolduğunda judge kısmi sonuçlarla durur.

## Sık hatalar

:::warn
**Aynı modeli judge ve student olarak kullanmak.** 7B modelin başka 7B çıktılarını yargılaması ince kalite sorunlarını yakalamaz. Daha güçlü judge kullanın.
:::

:::warn
**Pozisyon önyargısı.** Judge'lar genelde ilk yanıtı biraz tercih eder. Pairwise karşılaştırmalarda her zaman `swap_positions: true`.
:::

:::warn
**Çok küçük örneklem.** İki modeli 20 prompt'la karşılaştırmak istatistiksel gürültüdür. Anlamlı win-rate için 200+ kullanın.
:::

:::tip
**Judge'ı benchmark'la birleştirin.** Judge'da kazanıp benchmark'larda gerileyen model, judge'ın tercih ettiği şeyi over-fit ediyor demektir. Her iki sinyal de önemli.
:::

## Bkz.

- [Benchmark Entegrasyonu](#/evaluation/benchmarks) — nicel eval eşi.
- [Sentetik Veri](#/data/synthetic-data) — aynı sağlayıcı soyutlaması.
- [Otomatik Geri Alma](#/evaluation/auto-revert) — judge gating sinyali olabilir.
