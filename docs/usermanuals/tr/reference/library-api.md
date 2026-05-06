---
title: Library API
description: ForgeLM'i bir Python kütüphanesi olarak kullanın — public semboller, kararlılık katmanları ve lazy-import kontratı.
---

# Library API

ForgeLM, `forgelm` console script'inin yanında bir Python kütüphane API'si yayınlar. CLI'nin yaptığı her şeyi kütüphane yapabilir — exit-code eşlemesi hariç. Tam referans docs ağacında yaşar; bu sayfa navigasyon giriş noktasıdır.

## Eşit derecede first-class iki giriş noktası

```python
# Kütüphane — programatik kullanım.
from forgelm import ForgeTrainer, audit_dataset, verify_audit_log, load_config
```

```bash
# CLI — shell pipeline'ları + CI/CD.
forgelm --config configs/run.yaml
```

Python'dan orkestre ediyorsanız (Airflow, Prefect, Dagster) veya notebook'lardan çalışıyorsanız library API'yi seçin. Exit-code kontratına bağımlı bir CI pipeline yayınlıyorsanız CLI'yı seçin.

## Kararlılık katmanları

Üç katman semver ağırlığını yönetir:

- **Stable** — semver korumalı. `ForgeTrainer`, `ForgeConfig`, `load_config`, `audit_dataset`, `verify_audit_log`, `AuditLogger`, PII / secret yardımcıları ve verification toolbelt'i içerir.
- **Experimental** — best-effort, minor sürümde değişebilir. `WebhookNotifier`, `run_benchmark`, `SyntheticDataGenerator`, `compute_simhash`, `setup_authentication` içerir.
- **Internal** — `forgelm.__all__` içinde olmayan her şey. Kararlılık garantisi yok.

## Lazy-import kontratı

```python
import sys
import forgelm

assert "torch" not in sys.modules     # tests/test_library_api.py ile pinlenir
```

`import forgelm`, `torch`, `transformers`, `trl` veya `datasets`'i çekmez. Ağır bağımlılıklar yalnızca onlara ihtiyaç duyan bir sembol **çağrıldığında** (sadece referans alındığında değil) yüklenir.

## Daha fazla okumak için nereye

- Her imza ve işlenmiş örnek dahil tam referans docs ağacında:
  [`docs/reference/library_api_reference-tr.md`](../../../reference/library_api_reference-tr.md)
- Uçtan uca üç pipeline deseni ve yaygın tuzaklar dahil derin rehber:
  [`docs/guides/library_api-tr.md`](../../../guides/library_api-tr.md)
- Faz 18 tasarım gerekçesi (kararlılık katmanları, tip kontratı, deprecation cadence):
  [`docs/analysis/code_reviews/library-api-design-202605021414.md`](../../../analysis/code_reviews/library-api-design-202605021414.md)

## Ayrıca bakınız

- [Konfigürasyon](#/reference/configuration) — `ForgeConfig` alan referansı.
- [Audit Event Catalog](#/compliance/audit-log) — `AuditLogger.log_event`'in kabul ettiği olaylar.
- [CI/CD Pipeline'ları](#/operations/cicd) — CLI karşılığı.
