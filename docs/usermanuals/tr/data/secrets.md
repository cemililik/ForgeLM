---
title: Sırların Temizlenmesi
description: Eğitim verisinden AWS anahtarları, GitHub PAT'leri, JWT'leri, PEM blokları ve diğer kimlik bilgilerini redakte edin.
---

# Sırların Temizlenmesi

Kod repo'ları, destek ticket'ları ve operasyonel log'lar kimlik bilgileri sızdırır. Bu kimlik bilgileri eğitim setine girip model deploy edildikten sonra modelle sohbet eden herkes onları çıkarabilir. Sırların temizlenmesi bunu ingest'te önler.

## Tespit edilenler

| Kategori | Tespit edilen pattern |
|---|---|
| **AWS access key'leri** | `AKIA[0-9A-Z]{16}` + secret-key heuristikleri |
| **GitHub PAT'leri** | `ghp_*`, `gho_*`, `ghu_*`, `ghs_*`, `ghr_*` |
| **GitHub fine-grained token'lar** | `github_pat_*` |
| **Slack token'lar** | `xox[bpars]-*` |
| **OpenAI API key'leri** | `sk-*` (uzunluk ve entropi kontrolüyle) |
| **Anthropic API key'leri** | `sk-ant-*` |
| **Google API key'leri** | `AIza*` |
| **JWT'ler** | Üç-segment base64url (header.payload.signature) |
| **PEM özel anahtar blokları** | `BEGIN ... PRIVATE KEY...END` (RSA, EC, OpenSSH, PGP) |
| **Azure storage string'leri** | `DefaultEndpointsProtocol=...` |
| **Stripe / SendGrid / Twilio** | Servis-özgü pattern'ler |

Tüm eşleşmeler `[REDACTED-SECRET]` (veya `--secrets-tag-by-category` ile kategori başı etiketler) ile değiştirilir.

## Hızlı örnek

```shell
$ forgelm ingest ./support-tickets/ \
    --recursive \
    --secrets-mask \
    --output data/tickets.jsonl
✓ 47 sır maskelendi:
    aws_access_key: 12
    github_pat:     8
    jwt:            18
    pem_block:      2
    openai_key:     7
```

## "PEM block" ne demek

PEM özel anahtarlar birden çok satıra yayılır:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1+...
...
-----END RSA PRIVATE KEY-----
```

ForgeLM'in PEM detector'ı tüm bloğu (BEGIN'den END'e) eşleştirir, sadece marker satırını değil. Tüm blok `[REDACTED-PEM-BLOCK]` ile değiştirilir. Bu, BEGIN satırını tespit edip key body'sini JSONL'da bırakan yaygın bug'ı önler.

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

Yüksek-stake audit (ör. yasal açıklama taraması) için test-dışlama listesi bilinçlidir — tarama çıktısının `secret_findings_review_notes` alanını (her dışlanan eşleşme için bir satır, prose context'iyle) inceleyin; bir insan dummy'lerin gizlenmiş gerçek bir secret olmadığını teyit eder.

## Konfigürasyon

```yaml
ingestion:
  secrets_mask:
    enabled: true
    tag_by_category: true              # [REDACTED-SECRET] yerine kategori-özgü etiket
    strict: false                      # false-positive guard'ları kapat
    categories:                        # seçici etkinleştir
      - aws_access_key
      - github_pat
      - jwt
      - pem_block
      # eklemediğiniz kategori kapalı
```

## Sık hatalar

:::warn
**"Güvenilen iç" veride secrets-mask'i kapatmak.** İç log'lar kimlik bilgisi sızıntılarının en sık kaynağıdır. Maskeleyiciyi koşturmanın maliyeti neredeyse sıfır; deploy edilen modelde sızdırılmış bir AWS key'in maliyeti sınırsız.
:::

:::warn
**Entropi kontrolsüz özel regex.** Sırlar tespitinde false positive'in en büyük sebebi sadece-regex pattern'lerin dokümantasyon örneklerini eşlemesi. Regex'i her zaman entropi veya bağlam kontrolüyle eşleştirin.
:::

:::tip
Sertifika / token meşru içeren corpus'lar için (güvenlik eğitim dataset'leri, CTF içeriği) CLI escape hatch yoktur — sırlar taraması bilinçli olarak her zaman açıktır (bkz. yukarıda "Her zaman açık"). Corpus'unuzun data-governance manifest'inde ilgili satırları `legitimate_secret_content: true` olarak işaretleyin, böylece downstream reviewer rationale'ı görür; `forgelm audit` yine de flag'ler ama reviewer manifest satırını kanıt olarak dismiss eder.
:::

## Bkz.

- [PII Maskeleme](#/data/pii-masking) — kişisel veri için kardeş özellik.
- [Veri Seti Denetimi](#/data/audit) — sadece-audit modunda sırlar tespitini kapsar.
- [Doküman Ingest'i](#/data/ingestion) — secrets-mask'in çağrıldığı yer.
