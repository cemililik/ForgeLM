# Veri Seti Denetimi Rehberi

`forgelm --data-audit` bir JSONL veri setini analiz eder ve kalite,
governance ile PII sinyallerini kapsayan bir `data_audit_report.json`
üretir. Faz 11; `v0.5.0`'da tanıtıldı. Trainer'ın `output_dir`'ünde
mevcutsa, rapor EU AI Act Madde 10 veri governance artifact'ına
otomatik olarak beslenir.

---

## Çalıştırma

```bash
# Tek split (`train` olarak değerlendirilir)
forgelm --data-audit data/sft.jsonl --output ./audit/

# Çoklu split: train.jsonl / validation.jsonl / test.jsonl içeren dizin
forgelm --data-audit data/ --output ./audit/
```

`--output` varsayılan olarak `./audit/`'tir. Dizin yoksa oluşturulur;
**tam** `data_audit_report.json` her zaman oraya yazılır. Stdout
varsayılan olarak insan-okunabilir özet gösterir; `--output-format json`
geçince stdout'a **özet** JSON zarfı (üst seviye metrikler + rapor yolu
+ notlar) düşer — tam rapor yine `--output` altında diskte kalır. CI/CD
tüketicileri her detayı istediğinde stdout özetini parse etmek yerine
dosyayı `report_path`'tan slurp etmeli.

GPU gerekmiyor. Ağ çağrısı yok. CPU-only.

---

## Ne elde edersin

### Split başına metrikler

```json
{
  "splits": {
    "train": {
      "sample_count": 1240,
      "columns": ["text"],
      "text_length": {"min": 32, "max": 4096, "mean": 1834.2, "p50": 1900, "p95": 3580},
      "null_or_empty_count": 3,
      "null_or_empty_rate": 0.0024,
      "languages_top3": [
        {"code": "tr", "count": 950},
        {"code": "en", "count": 240},
        {"code": "de", "count": 50}
      ],
      "simhash_distinct": 1180,
      "near_duplicate_pairs": 60,
      "pii_counts": {"email": 18, "phone": 4}
    }
  }
}
```

### Cross-split örtüşmesi

```json
{
  "cross_split_overlap": {
    "hamming_threshold": 3,
    "pairs": {
      "train__test": {"leaked_rows_in_train": 7, "leak_rate": 0.0056}
    }
  }
}
```

Train ile test arasında sıfır olmayan leak rate **benchmark
güvenirliğinin sessiz katilidir** — eğitim öncesi split'leri düzeltin.

### PII özeti

```json
{
  "pii_summary": {
    "email": 18,
    "phone": 4,
    "credit_card": 1,
    "tr_id": 2
  }
}
```

Her satırın metin payload'ı regex ile taranır; kredi kartları Luhn
doğrulaması, TR Kimlik No'ları TC Kimlik checksum'ından geçirilir.
Diğer kategoriler regex şekli üzerinden yüzeylenir — false positive'ler
kasıtlıdır. Veri setini paylaşmadan önce `forgelm ingest --pii-mask`
ile (veya kendi ön işlemenizde) maskeleyin.

**Pattern önceliği belgeli.** `_PII_PATTERNS` iter sırası hem tespit
önceliğini hem maskeleme önceliğini yönetir — en spesifik pattern'lar
(`email`, `iban`, `credit_card`, ulusal kimlikler) önce taranır,
ardından gürültülü `phone` pattern'i. Bir span iki kategoriyle
eşleşebileceğinde, ilk / dar olan kazanır ve span sonraki pattern
görmeden değiştirilir. Phone, bare digit run'ları (timestamp, log line
numarası, ISO tarih) flag'lemesin diye kasıtlı olarak `+CC` veya
`(area)` formatına anchored.

### Near-duplicate tespiti

Case-fold edilmiş kelime token'ları üzerinde 64-bit simhash, Hamming
mesafe ≤ 3 ile (simhash makalesinin canonical web-page-dedup
kurulumunda kullandığı eşik, bu genişlikte ≈%95 benzerlik). Hem
**split-içi** çiftleri (`near_duplicate_pairs` per split) hem de
yukarıdaki **cross-split** sızıntıyı ortaya çıkarır.

Satır sayısında karesel; ~50K satıra kadar olan veri setlerinde
audit-zamanı kullanım için uygun. Daha büyük külliyatlar için LSH band
indeksi gerekecek — `v0.5.0` kapsamı dışı.

---

## Layout gereksinimleri

| Girdi şekli | Ne elde edersin |
|---|---|
| `*.jsonl` dosyası | `train` adlı tek split |
| `train.jsonl`, `validation.jsonl`, `test.jsonl`'in herhangi birini içeren `dir/` | Her mevcut dosya kendi split'i olur |
| Yaygın alias'ları (`dev`, `val`, `valid`, `eval`, `holdout`) içeren `dir/` | Canonical split adlarına katlanır — `dev.jsonl` → `validation`, `eval.jsonl` → `test`, vb. |
| Yalnızca canonical olmayan `*.jsonl` içeren `dir/` | Pseudo-split fallback: her `*.jsonl` kendi split'i olur VE cross-split leakage analizi gerçek bir partition olmadan anlamsızdır uyarısı yayılır |

Auditor şu öncelik sırasıyla bulduğu ilk metin-taşıyan sütunu okur:
`text` → `content` → `completion` → `prompt`. `messages` formatlı chat
verisinde rol etiketli içerikler birleştirilir.

**Şema kaymaları yüzeye çıkarılır.** Heterojen JSONL (opsiyonel
alanları olan satırlar) izinlidir — sütun şeması satırlar arası
anahtarların union'ı olarak hesaplanır; satır 0'dan sonra ortaya çıkan
herhangi bir sütun `schema_drift_columns` altında raporlanır, böylece
operatörler kaymanın kasıtlı olup olmadığına karar verebilir.

---

## Madde 10 governance entegrasyonu

`data_audit_report.json` trainer'ın `training.output_dir`'ünde eğitim
zamanında mevcut olduğunda,
[`generate_data_governance_report`](../../forgelm/compliance.py)
bulguları governance artifact'ının `data_audit` anahtarı altında
otomatik olarak inline eder. Compliance bundle'ınız ayrı dosyaya
işaret eden bir pointer yerine tek başına okunabilir bir doküman olur.

Önerilen iş akışı:

```bash
# Önce denetim — uzun bir eğitim koşusuna girmeden sorunları yüzeye çıkar
forgelm --data-audit data/policies.jsonl --output ./checkpoints/policy-run/

# Eğit (governance artifact denetimi inline edecek)
forgelm --config configs/policy-run.yaml
```

---

## CLI referansı

```text
forgelm --data-audit PATH \
  [--output DIR] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`PATH` bir `.jsonl` dosyası veya bir dizin olabilir. `--output`
varsayılan olarak `./audit/`'tir.

Üst düzey flag'tir (subcommand değil) — trainer'a dokunmadan çıkar.

> **Not:** Bu davranış kılavuzun başındaki özetle eşleşir:
> `--output-format json` stdout'a küçük bir zarf (success flag, üst
> seviye metrikler, rapor yolu) yazar. Tam `data_audit_report.json`
> her zaman `--output` altına yazılır. Her detayı istiyorsanız
> diskten okuyun.

---

## Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| `Audit failed: ... not found or empty` | Yol mevcut değil veya `.jsonl` yok | Yolu doğrulayın; dosya veya `train.jsonl` dizin layout'u verin |
| Dil istatistiklerinde `"unknown (install forgelm[ingestion])"` | `langdetect` yüklü değil | `pip install 'forgelm[ingestion]'` |
| Cross-split leakage tüm satırların %100'ünü flag'liyor | Tüm split'ler aynı içeriği barındırıyor | Yeniden karıştırın; muhtemelen aynı JSONL'i her split'e kopyaladınız |
| Büyük veri setinde `near_duplicate_pairs` çok büyük | Simhash karesel on-binlerce satırda koştu | Önce örnekleyin; LSH index desteği takip edecek |

---

## Programmatic API

```python
from dataclasses import asdict
from forgelm.data_audit import audit_dataset

report = audit_dataset("data/sft.jsonl", output_dir="./audit/")
print(report.total_samples, report.pii_summary)

# Veya manuel serileştir:
import json
json.dump(asdict(report), open("custom_path.json", "w"), indent=2)
```

`AuditReport` düz bir dataclass'tır — `dataclasses.asdict()` size
JSON-hazır bir dict verir. PII regex helper'ları (`detect_pii`,
`mask_pii`) ve simhash fonksiyonu (`compute_simhash`) da public
API'nin parçası.
