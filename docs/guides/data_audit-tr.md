# Veri Seti Denetimi Rehberi

`forgelm audit PATH` bir JSONL veri setini analiz eder ve kalite,
governance ile PII sinyallerini kapsayan bir `data_audit_report.json`
üretir. Faz 11 (`v0.5.0`'da tanıtıldı) altyapıyı, Faz 11.5 (`v0.5.1`)
ise top-level flag'i first-class subcommand'a yükseltti, LSH-banded
near-duplicate tespitini, streaming JSONL okuyucusunu, PII şiddet
katmanlarını, atomik disk yazımı ve verbose-by-default kısaltma
politikasını ekledi.

Trainer'ın `output_dir`'ünde mevcutsa, rapor EU AI Act Madde 10 veri
governance artifact'ına otomatik olarak beslenir.

---

## Çalıştırma

```bash
# Tek split (`train` olarak değerlendirilir)
forgelm audit data/sft.jsonl --output ./audit/

# Çoklu split: train.jsonl / validation.jsonl / test.jsonl içeren dizin
forgelm audit data/ --output ./audit/

# Bulgu olmayan split'leri de göster
forgelm audit data/ --verbose

# Daha geniş / dar near-duplicate eşiği
forgelm audit data/ --near-dup-threshold 5
```

> **Eski alias:** `forgelm --data-audit PATH` deprecation alias'ı
> olarak korunuyor; çalışmaya devam ediyor ama bir uyarı log'lanıyor.
> Yeni script'lerde `audit` subcommand'ını kullanın.

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
      "train__test": {
        "leaked_rows_in_train": 7,
        "leak_rate_train": 0.0056,
        "leaked_rows_in_test": 7,
        "leak_rate_test": 0.7
      }
    }
  }
}
```

Audit leak rate'i **her iki yönde** de raporlar çünkü birbirinden farklı
hikâyeler anlatırlar. 1240 train + 10 test satırında 7'sinin sızdığı bir
durumda `leak_rate_train = 7/1240 = %0.56` önemsiz görünür ama
`leak_rate_test = 7/10 = %70` benchmark güvenirliğini fiilen yok eden
metriktir. Her zaman küçük tarafın oranını okuyun — test bütünlüğünün
sessiz katili odur.

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

### PII şiddet katmanları (Faz 11.5)

Düz `pii_summary` haritası bir compliance reviewer'a *bulgu ne kadar
kötü?* sorusunda sıfır rehberlik veriyor. Faz 11.5 yanına bir
`pii_severity` bloğu ekliyor:

```json
{
  "pii_severity": {
    "total": 25,
    "by_tier": {"critical": 1, "high": 2, "medium": 18, "low": 4},
    "by_type": {
      "credit_card": {"count": 1, "tier": "critical"},
      "tr_id":      {"count": 2, "tier": "high"},
      "email":      {"count": 18, "tier": "medium"},
      "phone":      {"count": 4, "tier": "low"}
    },
    "worst_tier": "critical"
  }
}
```

Tier tablosu konsensüs regülatif ağırlıklandırmadır (finansal
kimlikler için PCI-DSS; devlet kimlikleri için GDPR Md. 9 + ENISA).
PII şiddetine kapılayan pipeline'lar `pii_severity.worst_tier`'i
okumalı ve `critical` / `high`'ta açık bir review olmadan yayınlamayı
reddetmeli.

### Near-duplicate tespiti

Case-fold edilmiş kelime token'ları üzerinde 64-bit simhash, Hamming
mesafe ≤ 3 ile (simhash makalesinin canonical web-page-dedup
kurulumunda kullandığı eşik, bu genişlikte ≈%95 benzerlik). Hem
**split-içi** çiftleri (`near_duplicate_pairs` per split) hem de
yukarıdaki **cross-split** sızıntıyı ortaya çıkarır.

Faz 11.5 alttaki taramayı **LSH banding**'e geçirdi: pigeonhole
prensibi `bands = threshold + 1` seçiyor, aday çiftler herhangi bir
band-bucket'ında çakışan satırlardan ibaret oluyor ve Hamming kontrolü
yalnızca adaylar üzerinde çalışıyor. Recall varsayılan eşikte tam
korunuyor; maliyet `O(n²)`'den ~`O(n × k)`'ye düşüyor (cross-split
`_count_leaked_rows` helper'ı da aynı banded şekli kullanıyor).
Brute-force yolu, eşik bantları 4 bitin altına düşürecek kadar yüksek
olduğunda fallback olarak kalıyor — `find_near_duplicates` her iki
yolda da aynı sonucu döndürüyor.

Faz 11.5 simhash backend'ini de değiştirilebilir hale getirdi:

- **xxhash.xxh3_64** opsiyonel `xxhash` bağımlılığı (artık
  `forgelm[ingestion]`'ın parçası) yüklüyse per-token digest'i bu
  sürüyor; kısa anahtarlarda BLAKE2b'ye göre Python katmanında ~%30
  hızlandırma sağlıyor (lru_cache devreye girince end-to-end kazanç
  daha az; backend swap'i öncelikle ileriye dönük güvence).
- **BLAKE2b** bare install için fallback olarak kalıyor.
- Modül seviyesinde `lru_cache(maxsize=10_000)` digest'i token
  seviyesinde memoize ediyor — Zipfian token frekansı sayesinde küçük
  bir cache bile bir corpus'un trafiğinin çoğunu kapsıyor.

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
forgelm audit data/policies.jsonl --output ./checkpoints/policy-run/

# Eğit (governance artifact denetimi inline edecek)
forgelm --config configs/policy-run.yaml
```

---

## CLI referansı

```text
forgelm audit PATH \
  [--output DIR] \
  [--verbose] \
  [--near-dup-threshold N] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`PATH` bir `.jsonl` dosyası veya bir dizin olabilir. `--output`
varsayılan olarak `./audit/`'tir. `--verbose`, insan-okunabilir özette
bulgu olmayan split'leri de gösterir (varsayılan, çoklu-split
denetimlerini kısa tutmak için tüm temiz split'leri tek bir kuyruk
satırına katlar — diskteki JSON raporu etkilenmez). `--near-dup-threshold`
varsayılan Hamming eşiğini (3, ≈%95 benzerlik) ezer.

Eski `forgelm --data-audit PATH` flag'i deprecation alias olarak
korunuyor; davranış aynı, sadece ek bir uyarı log'lanıyor.

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
| Gerçek bir corpus'ta `near_duplicate_pairs` çok büyük | Gerçekten yüksek near-duplicate oranı (boilerplate / tekrarlayan başlıklar / veri seti kalite sorunu) — Faz 11.5 LSH banding eski O(n²) taramayı O(n × k) ile değiştirdi, dolayısıyla büyük çift sayısı algoritmik gürültü değil sinyaldir | `--near-dup-threshold 1` veya 0 ile yalnızca çok-yakın eşleşmeleri tutun; PDF'lerde header/footer dedup otomatik çalışır (ingestion rehberine bakın); birkaç işaretli çift inceleyip dedupe veya kabul kararı verin |

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
