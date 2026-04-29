---
title: Birleşik Maskeleme (--all-mask)
description: Ingest sırasında PII + secrets temizlemesini birlikte çalıştıran tek-flag kısayolu.
---

# Birleşik Maskeleme — `--all-mask`

`--all-mask`, [Sırların Temizlenmesi](#/data/secrets) ve [PII Maskeleme](#/data/pii-masking) detector'larını aynı ingest pass'inde belgelenen sırayla (önce secrets, sonra PII) çalıştıran bir CLI kısayoludur. Yeni bir detector, yeni bir davranış getirmez — sadece ergonomi.

## Niye var

"Paylaşılan korpusta eğitime başlamadan tespit edilebilir her şeyi temizle" iş akışı, operatörlerin her seferinde iki flag'i birden yazması yetecek kadar yaygındı:

```shell
$ forgelm ingest ./mixed_corpus/ --secrets-mask --pii-mask --output data/clean.jsonl
```

`--all-mask` bunu tek flag'e indirir:

```shell
$ forgelm ingest ./mixed_corpus/ --all-mask --output data/clean.jsonl
```

İki form byte-eşdeğer çıktı üretir. Kısayol tamamen UX'tir.

## Nasıl birleşir

`--all-mask`, açık flag'lerle **additive**'tir. Aşağıdaki üç çağrı da aynı iki detector'ı çalıştırır:

```shell
$ forgelm ingest ./input/ --all-mask                    --output out.jsonl
$ forgelm ingest ./input/ --all-mask --pii-mask         --output out.jsonl
$ forgelm ingest ./input/ --all-mask --secrets-mask     --output out.jsonl
$ forgelm ingest ./input/ --all-mask --pii-mask --secrets-mask --output out.jsonl
```

Bu bilinçli bir tasarım kararı — set-union semantiği, alışkanlıkla `--pii-mask`'i her zaman geçen eski bir scriptin `--all-mask` eklendiğinde kırılmamasını sağlar. Hata yok, çelişki yok; iki flag de True kalır.

## Mask sırası

İki alt sistem birden çalıştığında **önce secrets** maskelenir, sonra PII. Bu sıra önemli çünkü:

1. Bazı credential şekilleri (örn. JWT'ler) email-benzeri substring'lerle çakışır; secrets'ı önce çalıştırmak email regex'inin bir JWT'nin ortasını yememesini sağlar.
2. `[REDACTED-SECRET]` placeholder'ı, `[REDACTED]`'ten yapısal olarak farklı — downstream auditor hangi span'in nasıl yeniden yazıldığını ayırt edebilir.

Sıra ingest pipeline'ının iç meselesidir; `--all-mask` kullanırken düşünmeniz gerekmez.

## JSONL'a inen şey

Her iki detector aynı JSONL'ı paylaşır — secrets `[REDACTED-SECRET]` olur, PII `[REDACTED]`:

```text
Önce: "Bana alice@example.com'dan ulaşın veya AKIAIOSFODNN7EXAMPLE kullanın."
Sonra: "Bana [REDACTED]'dan ulaşın veya [REDACTED-SECRET] kullanın."
```

## `--all-mask`'i NE zaman kullanmamalı

- **Yalnızca birini istiyorsan.** Açık flag'i kullan.
- **Farklı bir mask token'ı istiyorsan.** İki detector kendi placeholder'larını taşır; farklı bir şema lazımsa programatik olarak `forgelm.data_audit.mask_pii` / `mask_secrets` çağır.
- **Modifiye etmeden audit ediyorsan.** [`forgelm audit`](#/data/audit) kullan — aynı pattern'leri tarar ama yeniden yazmadan sayılarını raporlar.

## Yaygın tuzaklar

:::warn
**`--all-mask` bir compliance sertifikası değildir.** Defence-in-depth bir önlemdir. Yüksek-riskli korpuslar (hukuk, sağlık) için manuel review ve audit adımıyla eşleştirin.
:::

:::tip
Meşru olarak credential içeren (güvenlik eğitimi, CTF verileri) veya PII içeren (anonimleştirme araştırması) korpuslarda `--all-mask`'e uzanmayın. İstisna durumu dataset card'ınıza yazıp ingest maskelemesini tamamen atlayın.
:::

## Bakınız

- [PII Maskeleme](#/data/pii-masking) — alttaki personal-data detector'ı.
- [Sırların Temizlenmesi](#/data/secrets) — alttaki credentials detector'ı.
- [Doküman Ingest'i](#/data/ingestion) — `--all-mask`'in çağrıldığı yer.
- [Veri Seti Denetimi](#/data/audit) — yeniden yazmadan tespit eden audit-only karşılığı.
