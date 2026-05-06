---
title: Tedarik Zinciri
description: ForgeLM SBOM + pip-audit + bandit pipeline'ı için operatör yüzeyi — gecelik ne çalışır, tag başına ne çalışır, artefaktlar nereden alınır.
---

# Tedarik Zinciri

ForgeLM sürüm başına bir CycloneDX 1.5 SBOM yayınlar, gecelik `pip-audit` çalıştırır ve her PR'da `bandit` çalıştırır. Bu sayfa operatörün zihinsel modelidir: ne zaman ne çalışır, artefaktlar nereden alınır ve aynı kontroller lokalde nasıl yansıtılır.

## Ne zaman ne çalışır

| Tetikleyici | Araç | Sonuç | Hata politikası |
|---|---|---|---|
| Sürüm tag'i (`v*`) | `tools/generate_sbom.py` | (OS × Python-sürüm) hücresi başına bir CycloneDX 1.5 JSON, GitHub release'e iliştirilir | SBOM adımı pure-stdlib; yeşil sürüm matrisini sessizce bozamaz |
| Gecelik 03:00 UTC | `pip-audit` (`tools/check_pip_audit.py` üzerinden) | Kurulu bağımlılıklara karşı OSV / GHSA taraması | HIGH/CRITICAL → exit 1 + GitHub issue; MEDIUM → `::warning::`; LOW → sessiz |
| Her PR + main push | `bandit` (`tools/check_bandit.py` üzerinden) | `forgelm/` üzerinde statik güvenlik taraması (`tests/` hariç) | HIGH → exit 1; MEDIUM → `::warning::`; LOW → sessiz |

## SBOM nereden alınır

```bash
# Bir sürüm için tüm SBOM'lar.
gh release download v0.5.5 --pattern 'sbom-*'

# Birini güzel-yazdır.
jq . sbom-ubuntu-latest-py3.11.json | less

# İki sürüm arası diff (eklenen/kaldırılan bağımlılıkları listeler).
diff <(jq -S '.components | sort_by(.purl)' sbom-prev.json) \
     <(jq -S '.components | sort_by(.purl)' sbom.json)

# CVE korelasyonu için Dependency-Track'a yükle.
curl -X POST -H "X-Api-Key: $DT_KEY" -H "Content-Type: application/octet-stream" \
    --data-binary @sbom-ubuntu-latest-py3.11.json \
    https://deptrack.example.com/api/v1/bom
```

SBOM determinizm-pinli — aynı Python ortamında ardışık iki yayın content-identical JSON üretir (CycloneDX semantiği gereği kasıtlı olarak değişen `serialNumber` ve `metadata.timestamp` hariç).

## Gecelik kontrolü lokalde yansıtın

Bir PR push'lamadan önce, ForgeLM'in gecelik dayattığı aynı kontrolü çalıştırın:

```bash
pip install 'forgelm[security]'
pip-audit --strict --format json --output /tmp/pip-audit.json
python3 tools/check_pip_audit.py /tmp/pip-audit.json
```

Exit 0, ForgeLM CI'nın uyguladığı aynı severity politikasının geçtiği anlamına gelir. Exit 1, gecelik ateşlenmeden önce bir HIGH/CRITICAL açığın ele alınması gerektiği anlamına gelir.

## Bandit kontrolünü lokalde yansıtın

```bash
pip install 'forgelm[security]'
bandit -r forgelm/ -f json -o /tmp/bandit.json
python3 tools/check_bandit.py /tmp/bandit.json
```

`tests/` hariçtir çünkü test fixture'ları meşru olarak güvensiz desenler kullanır (`assert`, dummy secret'lar). `forgelm/` altındaki production kod kapsamdır.

## Bir CVE kabul edildiğinde ama henüz düzeltilemediğinde

Upstream henüz düzeltmeyi yayınlamadıysa ve CVE'yi operatör-tarafı risk acceptance log'unuzda belgelediyseniz:

```bash
pip-audit --ignore-vuln <CVE-ID> --strict --format json --output /tmp/pip-audit.json
```

ForgeLM proje-seviyesi bir ignore listesi yayınlamaz **— her suppression operatör-tarafı olmalı ve quarterly-review yapılmalıdır**.

## Daha fazla okumak için nereye

- Tam referans (severity politikası, suppression syntax'ı, ilgili ISO/SOC 2 kontrolleri):
  [`docs/reference/supply_chain_security-tr.md`](../../../reference/supply_chain_security-tr.md)
- Operatör denetim cookbook'u (Q4 SBOM'u yürür, Q5 erişim kontrollerini yürür, Q7 olay müdahalesini yürür):
  [`docs/guides/iso_soc2_deployer_guide-tr.md`](../../../guides/iso_soc2_deployer_guide-tr.md)
- SBOM emitter kaynağı (pure stdlib, sıfır dep):
  [`tools/generate_sbom.py`](../../../../tools/generate_sbom.py)

## Ayrıca bakınız

- [ISO 27001 / SOC 2 Operatörü](#/operations/iso-soc2-deployer) — denetim katı cookbook girişi.
- [CI/CD Pipeline'ları](#/operations/cicd) — gecelik + PR-başına kontrollerin indiği yer.
- [Air-gap Ön-cache](#/operations/air-gap) — SBOM determinizmi için bağımlılıkları ön-cache'leme.
