---
title: Annex IV
description: EU AI Act Madde 11 teknik dokümantasyonu, eğitim koşunuzdan otomatik doldurulur.
---

# Annex IV

EU AI Act'in (Tüzük (AB) 2024/1689) Annex IV bölümü, yüksek-riskli AI sistemleri için gereken sekiz bölümlü teknik dokümantasyonu tanımlar. ForgeLM bu artifact'ı otomatik üretir — `compliance.annex_iv: true` olan her koşunun ardından `artifacts/annex_iv.json`.

## Sekiz bölüm

| § | Bölüm | ForgeLM'in otomatik doldurduğu |
|---|---|---|
| 1 | Genel açıklama | Model adı, amaçlanan kullanım, coğrafyalar, sürüm. |
| 2 | Detaylı sistem açıklaması | Base model, trainer (SFT/DPO/...), veri seti özeti. |
| 3 | İzleme | Eval eşikleri, otomatik geri alma tetikleyicileri, trend izleme yapılandırması. |
| 4 | Risk yönetimi | Risk sınıflandırması, uygulanan azaltıcılar, kalıntı riskler. |
| 5 | Yaşam döngüsü | Eğitim zaman damgası, dataset sürümleri, kaynak referansları. |
| 6 | Uyumlaştırılmış standartlar | Listelenen uyumluluk çerçeveleri (EU AI Act, GDPR, ISO 27001). |
| 7 | AB uygunluk beyanı | İskelet; nihai aşamada bir insan tarafından imzalanır. |
| 8 | Pazara-sonrası izleme planı | Deployment surveillance config'ine referans. |

## Konfigürasyon → Annex IV

Annex IV'ün çoğu `compliance:` YAML bloğunuzdan doldurulur. Gerekli alanlar:

```yaml
compliance:
  annex_iv: true                                  # ana anahtar

  # Bölüm 1: Genel açıklama
  intended_purpose: "Çok dilli telekom müşteri-destek asistanı"
  deployment_geographies: ["TR", "EU"]
  responsible_party: "Acme Corp <compliance@acme.example>"
  version: "1.2.0"

  # Bölüm 4: Risk sınıflandırması
  risk_classification: "high-risk"                # veya "minimal", "limited"
  risk_assessment:
    foreseeable_misuse:
      - "Sosyal mühendislikte müşteri kimliği taklidi"
      - "Sahte fatura üretimi"
    mitigations:
      - "Llama Guard S5 (iftira) kapısı zorunlu"
      - "Ingest'te PII maskelenir"
    residual_risks:
      - "System prompt'a karşı adversarial jailbreak'ler"

  # Bölüm 6: Standartlar
  standards: ["EU AI Act", "GDPR", "ISO 27001"]

  # Bölüm 8: Pazara-sonrası plan referansı
  post_market_plan: "https://internal.acme.example/forgelm-monitoring"
```

Audit aşaması ([Veri Seti Denetimi](#/data/audit)) Bölüm 2'nin veri seti özetini ve Bölüm 5'in veri lineage'ını otomatik sağlar.

## Çıktı yapısı

`annex_iv.json` EU AI Act şemasını yakından takip eder:

```json
{
  "schema_version": "annex_iv/1.0",
  "section_1_general_description": {
    "name": "Acme Customer Support v1.2.0",
    "intended_purpose": "...",
    "deployment_geographies": ["TR", "EU"],
    "responsible_party": "Acme Corp <compliance@acme.example>",
    "version": "1.2.0"
  },
  "section_2_detailed_system_description": {
    "base_model": "Qwen/Qwen2.5-7B-Instruct",
    "trainer": "dpo",
    "datasets": [{
      "path": "data/preferences.jsonl",
      "row_count": 12400,
      "audit_report": "audit/data_audit_report.json",
      "source_documents": "data/sources.json"
    }],
    "training_recipe": "configs/customer-support.yaml"
  },
  "section_3_monitoring": {
    "benchmark_floors": {"hellaswag": 0.55, "...": "..."},
    "safety_thresholds": {"S5": 0.30, "...": "..."},
    "trend_tracking": true
  },
  "section_4_risk_management": {
    "classification": "high-risk",
    "foreseeable_misuse": [...],
    "mitigations": [...],
    "residual_risks": [...]
  },
  "section_5_lifecycle": {
    "trained_at": "2026-04-29T14:01:32Z",
    "training_duration_seconds": 1892,
    "config_hash": "sha256:deadbeef...",
    "dataset_hashes": {...}
  },
  "section_6_harmonised_standards": ["EU AI Act", "GDPR", "ISO 27001"],
  "section_7_declaration_of_conformity": {
    "status": "scaffold",
    "signed_by": null,
    "signed_at": null,
    "notes": "Sunulmadan önce insan incelemesi ve imza gerekir."
  },
  "section_8_post_market_plan": "https://internal.acme.example/forgelm-monitoring",
  "manifest_sha256": "..."
}
```

## Tamper-evidence

`annex_iv.json` da `manifest.json`'da hashlenir; pakettin diğer her artifact'ıyla yan yana. Manifest, değişmez paketin kanonik imzasıdır:

```json
{
  "schema": "manifest/1.0",
  "artifacts": {
    "annex_iv.json": "sha256:abc123...",
    "audit_log.jsonl": "sha256:def456...",
    "data_audit_report.json": "sha256:789abc...",
    "safety_report.json": "sha256:fedcba...",
    "benchmark_results.json": "sha256:111222..."
  },
  "generated_at": "2026-04-29T14:33:04Z"
}
```

Gerçek tamper-evidence için `manifest.json`'u ayrı bir write-once depoya gönderin (S3 Object Lock, HSM-imzalı ledger vb.). Toolkit artifact'ı üretir; operasyonel chain-of-custody sizin sorumluluğunuzdadır.

## Annex IV doğrulama

Bir Annex IV'ü "denetlemeye hazır" saymadan önce şemayı doğrulayın:

```shell
$ forgelm verify-annex-iv checkpoints/run/artifacts/annex_iv.json
✓ schema valid
✓ all required fields present
✓ manifest checksums match
⚠ section_7 declaration unsigned (yeni koşular için beklenen)
```

`forgelm verify-annex-iv` komutu manifest hash'lerini de yeniden hesaplar ve üretimden sonra tahrif olup olmadığını kontrol eder.

## Sık hatalar

:::warn
**Bölüm 7'deki insan incelemesi adımını atlamak.** Uygunluk beyanı yasal bir belgedir. Otomatik üretilen iskelet imzasızdır ve yasal bir etkisi yoktur — sunmadan önce bir insan inceleyip imzalamalıdır.
:::

:::warn
**ForgeLM çıktısını sertifikasyon olarak görmek.** ForgeLM kanıt üretir; sertifikasyon notified-body faaliyetidir. Belgelerimizin terminolojisi bunu yansıtır: "Annex-IV-tarzı artifact", "iskelet", "kanıt paketi" — asla "sertifikalı" değil.
:::

:::tip
Yüksek-riskli deployment'larda Annex IV artifact'ını model registry'nizde model sürümleriyle birlikte versiyonlayın. Denetçiler Annex IV'ü release başına görmek ister, eğitim koşusu başına değil.
:::

## Bkz.

- [Uyumluluk Genel Bakış](#/compliance/overview) — paketin geri kalanı için bağlam.
- [Audit Log](#/compliance/audit-log) — append-only event log.
- [İnsan Gözetimi](#/compliance/human-oversight) — Madde 14.
