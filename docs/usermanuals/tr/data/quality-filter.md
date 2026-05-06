---
title: Kalite Filtresi
description: Düşük-kaliteli eğitim satırlarını yakalamak için Gopher, C4 ve RefinedWeb'den heuristikler.
---

# Kalite Filtresi

Eğitim verinizdeki tüm satırlar eşit faydalı değildir. Boilerplate, OCR hataları, tekrarlanan satırlar ve saf-simge gürültüsü sinyali sulandırır. ForgeLM'in kalite filtresi Gopher, C4 ve RefinedWeb araştırma soylarından heuristikler uygular — muhafazakar şekilde, sessizce satır düşürmeden.

## Flaglenenler

| Heuristik | Yakaladığı |
|---|---|
| **Düşük alfa oranı** | `<%55` alfabetik karakter — genelde kod dump'ları, log spam veya saf simgeler. |
| **Anormal ortalama kelime uzunluğu** | Ortalama `<3` veya `>10` karakterli kelimeler — sıklıkla OCR çöpü veya sadece-URL satırlar. |
| **Tekrarlayan satır oranı** | Satırların `>%30`'u tekrarlanmış — boilerplate veya çıkarma artifact'ı. |
| **Kısa içerik** | Konfigüre minimum altında toplam uzunluk — sıklıkla çıkarma sonrası boş. |
| **Sadece-bullet satırlar** | Satırların `>%90`'ı bullet işaretiyle başlıyor — genelde çıkarılmış nav menüleri. |
| **Simge yoğunluğu** | Aşırı `_-=#*` yoğunluğu — genelde render edilmiş tablolar veya pre-format metin. |

Her satır audit raporunda `quality_flags` listesi alır. Filtre asla otomatik düşürmez; karar size ait.

## Hızlı örnek

```shell
$ forgelm audit data/ingested.jsonl
⚠ kalite flag'leri:
   short_response: 24
   repeated_lines: 12
   abnormal_word_length: 6
   bullet_only: 3
```

Audit, düşük kaliteli satırları *flagler* ama silmez. Düşürmek için, YAML konfigürasyonunuzdaki `audit.quality_filter.drop_flagged` ve `audit.quality_filter.write_clean_output` knob'larıyla opt-in olun ([Configuration Referansı](#/reference/configuration)) ve audit'i tekrar koşturun:

```yaml
audit:
  quality_filter:
    enabled: true
    drop_flagged: true
    write_clean_output: data/clean.jsonl
```

```shell
$ forgelm audit data/ingested.jsonl --quality-filter
✓ 45 satır düşürüldü; data/clean.jsonl yazıldı (12,355 satır)
```

## Eşik ayarlama

```yaml
audit:
  quality_filter:
    enabled: true
    min_alpha_ratio: 0.55              # varsayılan 0.55
    min_mean_word_length: 3            # varsayılan 3
    max_mean_word_length: 10           # varsayılan 10
    max_repeated_line_ratio: 0.30      # varsayılan 0.30
    min_content_length: 50             # varsayılan 50 karakter
    max_bullet_ratio: 0.90             # varsayılan 0.90
```

Birini meşru ihlal eden corpus'lar (ör. kod-ağırlıklı dataset'ler alfa oranını ihlal eder) için filtre tamamı yerine spesifik kontrolü kapatın:

```yaml
audit:
  quality_filter:
    enabled: true
    skip: ["min_alpha_ratio"]          # kod, matematik, log dataset'leri
```

## Tasarım gereği muhafazakar

Eşikler *flag, düşürme* için ayarlandı. Sebepler:

1. Domain uyumsuzluğu — web crawl'lara ayarlanmış kalite filtresi medikal veya hukuki metinde yanlış yargı verir.
2. Sessiz düşürme kullanıcıya görünmez. Flag göstermek ve insanın karar vermesi daha iyidir.
3. Audit raporları dataset sürümleri arasında karşılaştırılır; flag sayısındaki ani değişim bilgilendiricidir.

Daha sıkı filtreleme isterseniz — örneğin pre-training'e giden kamu web crawl'ında — filtreyi uç durumların manuel incelemesi ile birleştirin.

## Programatik API

```python
from forgelm.data_audit import score_quality

text = "= = = = = = = =\n* * *\n[içerik yok]"
flags = score_quality(text)
print(flags)
# {'low_alpha_ratio': True, 'symbol_density': True, 'short_content': True}
```

## Sık hatalar

:::warn
**İncelemeden otomatik düşürme.** `--drop-quality-flags`'i dikkatli ayarlayın — neyin kaldırıldığını size göstermeden satırları kaldırır. Önce neyin flaglendiğini incelemek için `forgelm audit` koşturun.
:::

:::warn
**Kod dataset'lerini varsayılan eşiklerle filtrelemek.** Kod prose'tan daha çok simge ve daha kısa ortalama kelime uzunluğu içerir. Etkilenen kontrolleri kapatın veya kod-özgü eşikler kullanın.
:::

## Bkz.

- [Veri Seti Denetimi](#/data/audit) — kalite filtresini standart audit'in parçası olarak koşturur.
- [Doküman Ingest'i](#/data/ingestion) — çoğu kalite sorunu çıkarma zamanında doğar.
