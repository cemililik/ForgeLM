---
title: Sırların Temizlenmesi
description: Eğitim verisinden AWS anahtarları, GitHub PAT'leri, JWT'leri, PEM blokları ve diğer kimlik bilgilerini redakte edin.
---

# Sırların Temizlenmesi

Kod repo'ları, destek ticket'ları ve operasyonel log'lar kimlik bilgileri sızdırır. Bu kimlik bilgileri eğitim setine girip model deploy edildikten sonra modelle sohbet eden herkes onları çıkarabilir. Sırların temizlenmesi bunu ingest'te önler.

## Tespit edilenler

Bundled detector `_SECRET_PATTERNS` (`forgelm/data_audit/_secrets.py::_SECRET_PATTERNS`) altında **9 secret ailesi** ship eder:

| Pattern anahtarı | Anchor |
|---|---|
| `aws_access_key` | `AKIA` / `ASIA` + 16 büyük harf alphanum |
| `github_token` | `ghp_*`, `gho_*`, `ghu_*`, `ghs_*`, `ghr_*`, `github_pat_*` (tek birleşik aile) |
| `slack_token` | `xox[baprs]-*` |
| `openai_api_key` | `sk-*` ve `sk-proj-*` |
| `google_api_key` | `AIza` + 35 karakter |
| `jwt` | Kanonik JWT header anahtarlarıyla üç-segment base64url (`eyJ.eyJ.X`-şekilli prose false-positive'lerine karşı savunma) |
| `openssh_private_key` | `BEGIN OPENSSH/RSA/DSA/EC PRIVATE KEY` … `END …` (tam PEM zarfı) |
| `pgp_private_key` | `BEGIN PGP PRIVATE KEY BLOCK` … `END …` |
| `azure_storage_key` | `DefaultEndpointsProtocol=…AccountKey=…` |

Tüm eşleşmeler `mask_secrets()` (`forgelm/data_audit/_secrets.py::mask_secrets`) tarafından literal `[REDACTED-SECRET]` string'i ile değiştirilir. Detector bugün Anthropic, Stripe, SendGrid ya da Twilio için per-vendor pattern ship **etmez** — bu trafik tipleri olan operatörler regex setini out-of-tree genişletir (Phase 28+ backlog'u bunları opt-in extras olarak ship etmeyi takip ediyor).

## Hızlı örnek

```shell
$ forgelm ingest ./support-tickets/ \
    --recursive \
    --secrets-mask \
    --output data/tickets.jsonl
✓ 47 sır maskelendi:
    aws_access_key:       12
    github_token:          8
    jwt:                  18
    openssh_private_key:   2
    openai_api_key:        7
```

## "PEM block" ne demek

PEM özel anahtarlar birden çok satıra yayılır:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1+...
...
-----END RSA PRIVATE KEY-----
```

ForgeLM'in PEM detector'ı (`openssh_private_key` ailesi — RSA / DSA / EC envelope'larını da kapsar) tüm bloğu (BEGIN'den END'e) eşleştirir, sadece marker satırını değil. Diğer her aile gibi, tüm blok `[REDACTED-SECRET]` ile değiştirilir — per-family token yoktur (`mask_secrets()` tek bir `replacement="[REDACTED-SECRET]"` sabiti ship eder; `forgelm/data_audit/_secrets.py::mask_secrets`). Bu, BEGIN satırını tespit edip key body'sini JSONL'da bırakan yaygın bug'ı önler.

## Sadece-audit modu

```shell
$ forgelm audit data/tickets.jsonl
✓ format: instructions (8,400 satır)
⚠ sırlar: 47 tespit (severity: critical)
   12 AWS access key
   18 JWT
   ...
```

Sırlar taraması her zaman açıktır — CLI yüzeyinden devre dışı bırakılamaz (eğitim verisinde credential sızıntısı, operatörün asla kapatabilmesi gereken bir şey değildir). `critical` severity non-zero exit verir, böylece CI pipeline hızlı fail eder.

## Programatik API

```python
from forgelm.data_audit import detect_secrets, mask_secrets

text = "Şu key'i kullan: AKIAIOSFODNN7EXAMPLE ve JWT eyJhbGc..."
hits = detect_secrets(text)
print(hits)
# [{'category': 'aws_access_key', 'span': (16, 36), 'value': 'AKIAIOSFODNN7EXAMPLE'}]

cleaned = mask_secrets(text)
# "Şu key'i kullan: [REDACTED-SECRET] ve JWT [REDACTED-SECRET]..."
```

## False-positive guard'ları

ForgeLM tipik "git-secrets" tarzı araçlardan daha sıkı false-positive guard'larıyla sırlar tespiti yayınlar; çünkü:

1. Eğitim verisinde false positive örnekleri bozar (gerçek string'leri değiştirir).
2. Çoğu sadece-regex pattern `EXAMPLEKEY` veya test fixture'ları flagler; audit raporlarını kullanışsız kılar.

Spesifik guard'lar:
- OpenAI / Anthropic key'leri için **entropi eşiği** (insan-okunur değil, rastgele görünüm).
- **Bağlam pencere kontrolü** — `AKIA*` sadece secret-key-şeklinde komşu veya 100 karakter içinde "aws" bağlamı varsa tetiklenir.
- **Test/örnek dışlama listesi** — yaygın dummy değerler (`AKIAIOSFODNN7EXAMPLE`, `xxx`, `your_key_here`) tespiti atlar.

Yüksek-stake audit (ör. yasal açıklama taraması) için test-dışlama listesi bilinçlidir — `forgelm audit` hayatta kalan bulguları `AuditReport.secrets_summary` altında kaydeder (pattern türü başına bir sayım) ve prose-seviyesinde inceleme için kanonik yüzey satır başına JSON çıktısıdır (`--output-format json`, opsiyonel `--output-jsonl`). Yüksek-stake audit'inizde sayımı > 0 olan herhangi bir pattern türü için bu JSON'u dolaşın; bir insan dummy'lerin gizlenmiş gerçek bir secret olmadığını teyit etsin. (Özel `secret_findings_review_notes` zarfı v0.6+ yol haritasında.)

## Konfigürasyon

Secrets scanner **`forgelm audit` içinde her zaman açıktır** — enable/disable knob'u ve per-family allow/deny listesi yoktur. Mask-on-emit `audit_dataset()` üzerindeki `secrets_mask: bool` argümanıyla (ve `forgelm ingest` üzerindeki `--secrets-mask` flag'iyle) kontrol edilir; replacement string'i `mask_secrets()` içindeki tek sabit `[REDACTED-SECRET]` constant'ıdır. `ingestion.secrets_mask:` YAML bloğu, `enabled` / `tag_by_category` / `strict` / `categories` alt-alanları **yoktur** — bu adlar eski doc taslaklarında geçiyordu ama hiç ship olmadı. Family setini genişletmek/kısıtlamak için `forgelm/data_audit/_secrets.py::_SECRET_PATTERNS`'i fork edin.

## Sık hatalar

:::warn
**"Güvenilen iç" veride secrets-mask'i kapatmak.** İç log'lar kimlik bilgisi sızıntılarının en sık kaynağıdır. Maskeleyiciyi koşturmanın maliyeti neredeyse sıfır; deploy edilen modelde sızdırılmış bir AWS key'in maliyeti sınırsız.
:::

:::warn
**Entropi kontrolsüz özel regex.** Sırlar tespitinde false positive'in en büyük sebebi sadece-regex pattern'lerin dokümantasyon örneklerini eşlemesi. Regex'i her zaman entropi veya bağlam kontrolüyle eşleştirin.
:::

:::tip
Sertifika / token meşru içeren corpus'lar için (güvenlik eğitim dataset'leri, CTF içeriği) CLI escape hatch yoktur — sırlar taraması bilinçli olarak her zaman açıktır (`--no-secrets` / `--skip-secrets` flag'i yoktur ve `forgelm audit` taramayı her çağrıda koşulsuz koşturur; temel scan-mode semantiği için yukarıdaki [Sadece-audit modu](#sadece-audit-modu) bölümüne bkz.). Corpus'unuzun data-governance manifest'inde ilgili satırları `legitimate_secret_content: true` olarak işaretleyin, böylece downstream reviewer rationale'ı görür; `forgelm audit` yine de flag'ler ama reviewer manifest satırını kanıt olarak dismiss eder.
:::

## Bkz.

- [PII Maskeleme](#/data/pii-masking) — kişisel veri için kardeş özellik.
- [Veri Seti Denetimi](#/data/audit) — sadece-audit modunda sırlar tespitini kapsar.
- [Doküman Ingest'i](#/data/ingestion) — secrets-mask'in çağrıldığı yer.
