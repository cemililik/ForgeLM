---
title: Benchmark Entegrasyonu
description: lm-evaluation-harness görevlerini görev başı floor eşikleriyle ve otomatik geri almayla koşturun.
---

# Benchmark Entegrasyonu

ForgeLM, [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) ile entegre — LLM'ler için standart benchmark suite'i — ve üzerine üretim katmanını ekler: görev başı floor eşikleri, regresyonda otomatik geri alma ve compliance paketinize akan yapılandırılmış artifact'lar.

## Hızlı örnek

```yaml
evaluation:
  benchmark:
    enabled: true
    tasks: ["hellaswag", "arc_easy", "truthfulqa", "mmlu"]
    floors:
      hellaswag: 0.55
      arc_easy: 0.70
      truthfulqa: 0.45
    num_fewshot: 0                      # zero-shot eval
    batch_size: 8
    output_dir: "./checkpoints/run/artifacts/"
```

Eğitimden sonra ForgeLM listelenen görevleri koşturur, floor'larla karşılaştırır ve:
- Tüm görevler floor'u geçerse → koşu başarılı (exit 0)
- Herhangi bir görev floor altına düşerse → son-iyi checkpoint'e otomatik geri al, exit 3

## Desteklenen görevler

`lm-evaluation-harness`'taki her şey çalışır. Sık seçimler:

| Görev | Ölçtüğü |
|---|---|
| `hellaswag` | Sağduyu tamamlama |
| `arc_easy`, `arc_challenge` | İlkokul fen bilimleri |
| `truthfulqa` | Yaygın yanılgılara dayanıklılık |
| `mmlu` | Geniş çoklu-görev bilgi |
| `winogrande` | Zamir çözümlemesi |
| `gsm8k` | İlkokul matematiği (CoT ile) |
| `humaneval` | Kod tamamlama |

Türkçe projeler için ForgeLM, Türkçe-özgü görevlere uyarlanmış `mmlu_tr` ve `belebele_tr` şablonları yayınlar.

## Görev başı floor

Floor'lar, görev başına post-train'in geçeceği minimum kabul edilebilir puanı tanımlar. *Her* görev kendi floor'unu geçmeden model terfi etmez.

```yaml
evaluation:
  benchmark:
    floors:
      hellaswag: 0.55
      mmlu: 0.50
      # floor'suz görevler raporlanır ama terfiyi engellemez
      truthfulqa: 0.45
```

`null` floor "raporla ama gating yapma" demek. `0` floor floor olmamasıyla aynı.

:::tip
Floor'ları pre-training baseline'ınızdan biraz altına ayarlayın. Hedef: *iyileştirme* zorunlu kılmak değil, *gerilemeyi* yakalamak. Hedef görevde %5 kazanan ama hellaswag'da %2 kaybeden model genelde iyidir; hellaswag'da %15 kaybeden bozuktur.
:::

## Pre-train baseline

Hangi floor'u koyacağınızı bilmek için bir pre-training baseline lazım:

```shell
$ forgelm benchmark --model "Qwen/Qwen2.5-7B-Instruct" \
    --tasks hellaswag,arc_easy,truthfulqa,mmlu \
    --output baselines/qwen-2.5-7b.json
{"hellaswag": 0.61, "arc_easy": 0.75, "truthfulqa": 0.49, "mmlu": 0.52}
```

Makul bir floor baseline eksi 0.03 (stokastik dalgalanma için %3 pay):

```yaml
evaluation:
  benchmark:
    floors:
      hellaswag: 0.58                   # baseline 0.61 - 0.03
      arc_easy: 0.72
      truthfulqa: 0.46
      mmlu: 0.49
```

## Çıktı artifact'ları

Eval'den sonra ForgeLM şunları yazar:

```text
checkpoints/run/artifacts/
├── benchmark_results.json             ← görev başı puanlar + floor verdict'leri
└── benchmark_run.log                  ← tam lm-eval-harness çıktısı
```

`benchmark_results.json` yapısı:

```json
{
  "tasks": {
    "hellaswag": {
      "score": 0.617, "floor": 0.55, "passed": true,
      "fewshot": 0, "n": 10042
    },
    "truthfulqa": {
      "score": 0.42, "floor": 0.45, "passed": false
    }
  },
  "verdict": "regression",
  "regressed_tasks": ["truthfulqa"]
}
```

CI hatları `verdict`'i parse eder. Gating mantığı için bkz. [Otomatik Geri Alma](#/evaluation/auto-revert).

## Konfigürasyon parametreleri

| Parametre | Tip | Vars. | Açıklama |
|---|---|---|---|
| `enabled` | bool | `false` | Ana anahtar. |
| `tasks` | list | `[]` | lm-eval-harness görev adları. |
| `floors` | dict | `{}` | Görev başı minimum kabul edilebilir puan. |
| `num_fewshot` | int | `0` | Zero-shot için 0, 5-shot için 5. |
| `batch_size` | int | `8` | Eval batch size. |
| `limit` | int | `null` | Görev başı satır sınırı — hızlı smoke test için. |
| `device` | string | `"cuda:0"` | Eval cihazı. |

## Sık hatalar

:::warn
**Pre-train baseline'dan yüksek floor.** Floor'u base modelin geçemediği değere koyarsanız her koşu başarısız olur — otomatik geri alma devreye girer ve hiç checkpoint alamazsınız. Her zaman `baseline - margin` ile başlayın.
:::

:::warn
**Yayınlanan kamuya açık sonuçlarla `num_fewshot` uyuşmazlığı.** Kamuya açık leaderboard'lar belirli shot sayılarında raporlar (ör. MMLU kanonik olarak 5-shot). Sonuçların karşılaştırılabilir olmasını istiyorsanız aynı ayarı kullanın.
:::

:::tip
**`limit` ile iterasyonu hızlandırın.** `limit: 100` ayarlamak görev başına 100 satır koşturur (binlerce yerine) — ~10× hızlı eval. Dev config'lerinde kullanın; üretim için kaldırın.
:::

## Bkz.

- [Otomatik Geri Alma](#/evaluation/auto-revert) — floor'lar başarısız olduğunda ne olur.
- [LLM-as-Judge](#/evaluation/judge) — benchmark ötesi nitel eval.
- [Trend İzleme](#/evaluation/trend-tracking) — koşular arası puanları karşılaştırma.
