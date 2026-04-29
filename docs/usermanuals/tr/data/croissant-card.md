---
title: Croissant 1.0 Dataset Kartı
description: Audit raporunun yanında yayınlanan opsiyonel Google Croissant 1.0 metadata — aynı JSON dosyasını hem EU AI Act Madde 10 artifact'ı hem de Croissant tüketicisi dataset card'ı haline getirir.
---

# Croissant 1.0 Dataset Kartı — `--croissant`

Audit raporu (`data_audit_report.json`) bir EU AI Act Madde 10 reviewer'ının ihtiyacı olan her sinyali zaten taşır: PII sayıları, secrets özeti, near-duplicate çiftleri, cross-split sızıntı, dil dağılımı. `--croissant` ile aynı dosya, [Google Croissant 1.0](http://mlcommons.org/croissant/) spec'ine uyan top-level bir `croissant` bloğu kazanır. Tek dosya, iki tüketici.

## Niye uğraşalım?

Croissant, ML dataset card'ları için ortaya çıkan standart (Hugging Face dataset sayfaları, MLCommons referans loader'ları, Croissant validator'ı bunu tüketir). Audit'in yanında bir card yayınlamak şu anlama gelir:

- Dataset metadata bloğu önceden hazır halde HuggingFace / MLCommons'a yayınlanabilir.
- Croissant farkındalıklı bir loader, alttaki JSONL split'lerini doğrudan card'dan bulabilir.
- Compliance reviewer'ları ve veri bilimciler aynı kaynak gerçeği okur.

`--croissant` kapalıyken audit raporundaki `croissant` anahtarı boş bir dict (`{}`) olur. Bilinmeyen anahtarları ignore eden mevcut audit tüketicileri davranış değişikliği görmez.

## Hızlı örnek

```shell
$ forgelm audit data/policies/ --output ./audit/ --croissant
✓ format: instructions (12.400 satır, 3 split)
✓ croissant card yayınlandı
   distribution: 3 file object (train.jsonl, validation.jsonl, test.jsonl)
   record sets: 3
```

Card `croissant` anahtarının altında oluşur:

```json
{
  "croissant": {
    "@context": { "@vocab": "https://schema.org/", "sc": "https://schema.org/", "cr": "http://mlcommons.org/croissant/", ... },
    "@type": "sc:Dataset",
    "conformsTo": "http://mlcommons.org/croissant/1.0",
    "name": "policies",
    "description": "ForgeLM audit-generated dataset card. 12400 sample(s) across 3 split(s). ...",
    "url": "data/policies/",
    "datePublished": "2026-04-29T...",
    "distribution": [
      { "@type": "cr:FileObject", "@id": "train.jsonl",      "name": "train.jsonl",      "contentUrl": "train.jsonl",      "encodingFormat": "application/jsonlines", "description": "..." },
      { "@type": "cr:FileObject", "@id": "validation.jsonl", "name": "validation.jsonl", "contentUrl": "validation.jsonl", "encodingFormat": "application/jsonlines", "description": "..." },
      { "@type": "cr:FileObject", "@id": "test.jsonl",       "name": "test.jsonl",       "contentUrl": "test.jsonl",       "encodingFormat": "application/jsonlines", "description": "..." }
    ],
    "recordSet": [
      { "@type": "cr:RecordSet", "@id": "train",      "name": "train",      "field": [...] },
      { "@type": "cr:RecordSet", "@id": "validation", "name": "validation", "field": [...] },
      { "@type": "cr:RecordSet", "@id": "test",       "name": "test",       "field": [...] }
    ]
  }
}
```

## Card neyi taşır

| Alan | Kaynak |
|---|---|
| `@context` | Kanonik Croissant 1.0 context bloğu (vocabulary). |
| `@type` | `sc:Dataset` — Croissant validator'lar için zorunlu. |
| `conformsTo` | `http://mlcommons.org/croissant/1.0` — vocab declaration. |
| `name` | Kaynak path'inden türetilir (dosya stem'i veya dizin adı). |
| `description` | Sample sayısı + split sayısı için otomatik özet. |
| `url` | As-typed input path'i (HF Hub ID, relative path, vb.) — resolve edilmiş absolute filesystem path değil; HuggingFace / MLCommons'a yayınlanan card'lar auditor'ın yerel layout'unu sızdırmaz. |
| `datePublished` | Audit çalışmasının ISO 8601 timestamp'i. |
| `distribution` | Her JSONL split'i için bir `cr:FileObject`. `contentUrl` relative file_id'dir (aynı anti-leakage gerekçesi). |
| `recordSet` | Her split için audit'in column-detection katmanından türetilen `cr:Field` girdileriyle bir `cr:RecordSet`. |

## Bilinçli olarak EMIT EDİLMEYEN şeyler

Audit'in şu Croissant alanları için birinci sınıf delili yok, bu yüzden tahmin etmek yerine atlanırlar:

- `version` (`sc:version`) — dataset versiyonu. Yayınlayan operatörler diğer publish-only alanları nasıl elle düzenliyorlarsa bunu da publish anında elle düzenler.
- `license` — aynı; audit keyfi bir korpusun lisansını çıkaramaz.
- `citeAs` — citation string; publisher'a kalmış.
- `creator` / `keywords` — publish bağlamına bağlı.

Bu alanların doldurulmasını istiyorsanız, publish öncesi audit-sonrası JSON'u düzenleyin. Audit'in compliance rolünü değiştirmezler.

## Conformance

Yayınlanan card kanonik [Croissant 1.0 spec](http://mlcommons.org/croissant/1.0)'ine uyumludur. Şunlara karşı doğrulanmıştır:

- [Croissant validator](https://github.com/mlcommons/croissant) (`mlcroissant validate`).
- HuggingFace'in dataset card parser'ı (`datasets` kütüphanesi dataset dizininde varsa Croissant'ı okur).

Doğrulama minimum-viable subset üzerinde çalışır; tooling'iniz bu listede olmayan opsiyonel alanlar bekliyorsa publish öncesi elle düzenleyin.

## Ne zaman kullanılır

- **Dataset'i yayınlarken.** Card audit ile aynı JSON dosyasında yaşar; publish adımı tek bir artefakt olur.
- **Ekipler arası handoff.** Veri mühendisleri ve ML mühendisleri aynı dosyayı tüketebilir.
- **Compliance bundle'ları.** EU AI Act Madde 10 governance bundle'ları Croissant card'ını dataset-identity katmanı olarak içerebilir.

## Ne zaman kullanılmaz

- **Ekibin bucket'ından çıkmayan iç audit'ler.** Card zararsızdır ama gerek de yoktur.
- **Standart-olmayan dosya layout'ları olan dataset'ler** (alakasız `.jsonl` dosyalarının bir dizinde unsupervised cluster'lanması). Croissant splits-per-file conventionunu varsayar; keyfi layout'lar için card'ı elle yazın.

## Programatik API

Card `forgelm.data_audit._build_croissant_metadata` (private helper) tarafından inşa edilir ve `audit_dataset(emit_croissant=True)` çağrıldığında `AuditReport.croissant`'a doldurulur:

```python
from forgelm.data_audit import audit_dataset

report = audit_dataset(
    "data/policies/",
    output_dir="./audit/",
    emit_croissant=True,
)
print(report.croissant["@type"])           # "sc:Dataset"
print(report.croissant["conformsTo"])      # "http://mlcommons.org/croissant/1.0"
print(len(report.croissant["distribution"]))  # 3 (her JSONL split başına bir)
```

## Yaygın tuzaklar

:::warn
**Card'ı düzenleyip sonra audit'i yeniden çalıştırma.** `forgelm audit`'i yeniden çalıştırmak dosyanın üzerine yazar. Ya son audit *sonrası* düzenleyin ya da düzenlenmiş card'ı kendi publish-step script'inizle ileri besleyin.
:::

:::tip
Hugging Face yayını için card'ı dataset repo'sunda `croissant.json` olarak kaydedin (HF orada bekler). Basit bir `jq '.croissant' data_audit_report.json > croissant.json` işi görür.
:::

## Bakınız

- [Veri Seti Denetimi](#/data/audit) — `--croissant`'ın çağrıldığı yer.
- [Annex IV](#/compliance/annex-iv) — audit'in beslediği EU AI Act Madde 11 artefaktı.
- [GDPR / KVKK](#/compliance/gdpr) — daha geniş düzenleyici bağlam.
