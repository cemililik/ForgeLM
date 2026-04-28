---
title: Tekrar Tespiti
description: Eğitim verisinde near-duplicate yakalamak için LSH-banded simhash ve MinHash LSH.
---

# Tekrar Tespiti

Tekrarlar ve near-duplicate'ler eğitim dağılımınızı tekrarlanan şeye doğru şişirir; train/eval split'lerini geçerlerse değerlendirme metriklerinizi anlamsızlaştırır. ForgeLM iki algoritma yayınlar: doğruluk ve küçük-orta corpus için simhash, ölçek için MinHash LSH.

## Algoritma seçimi

| Algoritma | Recall | Hız | En iyi |
|---|---|---|---|
| **LSH-banded simhash** (varsayılan) | Hamming eşiği içinde kesin | ~50K satır/s | Corpus < 50K satır |
| **MinHash LSH** | Yaklaşık (gerçek tekrarların >%95'i) | ~500K satır/s | Corpus > 50K satır |

ForgeLM satır sayısına göre otomatik seçer — küçük için simhash, büyük için MinHash — ama `--dedup-algo` ile override edebilirsiniz.

## Hızlı örnek

```shell
$ forgelm audit data/train.jsonl --dedup-threshold 3
⚠ near-duplicate çift: 47 (LSH-banded simhash, eşik 3)

$ jq '.near_duplicates[]' audit/data_audit_report.json | head
{"row_a": 1240, "row_b": 4521, "hamming": 1, "similarity": 0.984}
{"row_a": 9012, "row_b": 9013, "hamming": 0, "similarity": 1.0}
```

`hamming: 0` *kesin* tekrarlardır (aynı simhash); yüksek değerler giderek daha az benzer.

## Eşik ayarlama

`--dedup-threshold` 64-bit simhash üzerinde Hamming mesafesidir. Varsayılanlar:

| Eşik | Yakalanan | False-positive oranı |
|---|---|---|
| 0 | Sadece kesin tekrarlar | ~0% |
| 1-2 | Trivial-edit tekrarları ("Merhaba!" vs "Merhaba.") | <1% |
| **3** (varsayılan) | Yapı paylaşan parafraz'lar | 1-2% |
| 5+ | Gevşek parafraz'lar; yüksek false-positive | 5-15% |

Çoğu ekip 3'te kalır.

## Near-dup'ın exact-match'in yakalamadığı

```text
Satır A: "Müşteri desteğine hoş geldiniz. Size nasıl yardımcı olabilirim?"
Satır B: "Müşteri desteğine hoş geldiniz — size nasıl yardımcı olabilirim?"
```

Exact-match bunları kaçırır (farklı noktalama). Eşik 3 ile simhash yakalar.

```text
Satır A: "CV'nizi ali@example.com'a gönderin"
Satır B: "CV'nizi ali@example.com'a gönderin veya bizi arayın"
```

Eşik 3 bunları da yakalar (aynı ilk yarı, hafif uzatma).

## Split-arası farkındalık

Audit, near-dup tespitini hem split *içinde* hem *arası* koşturur. Split-arası tekrarlar yüksek-öncelikli bug — benchmark puanlarınızı güvenilmez kılar. Audit'in `cross_split_overlap` alanı kaç train satırının validation veya test'te near-duplicate'i olduğunu raporlar. Bkz. [Split-arası Sızıntı](#/data/leakage).

## Ölçek için MinHash LSH

50K satır üzeri corpus için MinHash'a geçin:

```shell
$ forgelm audit data/large.jsonl --dedup-algo minhash --num-perm 256
✓ near-duplicate çift: 1,247 (MinHash LSH, 256 permutasyon, eşik 0.85)
```

MinHash büyük hız için küçük doğruluk ödünleşir — milyon-satır dataset'lerde simhash'tan 10× hızlı koşarken tipik recall gerçek tekrarların >%95'i.

| MinHash bayrak | Açıklama |
|---|---|
| `--num-perm` | Hash permutasyon sayısı (varsayılan 128). Daha çok = daha doğru, daha çok bellek. |
| `--minhash-threshold` | Jaccard benzerlik eşiği (varsayılan 0.85). |
| `--minhash-bands` | LSH banding parametresi (varsayılan eşikten otomatik türetilir). |

## Streaming davranış

İki algoritma da streaming — tüm dataset'i belleğe yüklemez. 10M-satır corpus laptop CPU'sunda birkaç dakikada deduplike edilir.

## Tekrarları kaldırma

`forgelm audit` tekrarları *tespit eder*; varsayılan kaldırmaz (veri modifikasyonu bilinçli). Deduplike etmek için:

```shell
$ forgelm audit data/train.jsonl --remove-duplicates --output-clean data/train.dedup.jsonl
✓ 47 near-duplicate satır kaldırıldı; data/train.dedup.jsonl yazıldı (12,353 satır)
```

Tekrarlar tek split içindeyken ForgeLM ilk tekrarı tutar. Split arasında varsayılan train tarafını tutar ve validation/test'ten kaldırır (konfigüre edilebilir).

## Sık hatalar

:::warn
**Eşik çok agresif.** Simhash'ta 5+ Hamming eşiği meşru farklı örnekleri tekrar olarak flagler. Spesifik veriniz üzerinde false-positive oranı ölçmediyseniz 3'te kalın.
:::

:::warn
**MinHash permutasyonu çok düşük.** `--num-perm 64` bellek tasarrufu sağlar ama recall ~%85'e düşer. Üretim kullanımı için 128'in üstünde kalın.
:::

:::tip
**Train/val/test'i manuel ayırmadan ÖNCE dedup koşturun.** Split'leriniz yukarıdan üretildi ve sızıntı varsa deduplikasyonla düzeltemezsiniz; yeniden split'lemeniz gerekir. Birleşik dataset üzerinde audit, split öncesi bunu yakalar.
:::

## Bkz.

- [Veri Seti Denetimi](#/data/audit) — standart audit'in parçası olarak dedup koşturur.
- [Split-arası Sızıntı](#/data/leakage) — en yüksek öncelikli deduplikasyon kaygısı.
- [Kalite Filtresi](#/data/quality-filter) — düşük-kaliteli satırları yakalayan kardeş özellik.
