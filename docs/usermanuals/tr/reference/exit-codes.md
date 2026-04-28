---
title: Exit Kodları
description: ForgeLM'in exit-kod kontratı — CI/CD hatlarının kamuya açık API'si.
---

# Exit Kodları

ForgeLM'in exit kodları kamuya açık bir kontrattır. CI/CD hatları, scheduler'lar ve dashboard'lar bunlara dayanır. Sürümler arası sessizce değişmez.

## Kontrat

| Exit | İsim | Anlam | Tipik CI aksiyonu |
|---|---|---|---|
| **0** | Başarı | Koşu tamamlandı; tüm kapılar geçti; checkpoint terfi etti. | Hattı sürdür |
| **1** | Config hatası | YAML geçersiz, dosya yok, env var ayarsız veya argüman bozuk. | Hızlı başarısız |
| **2** | Audit uyarıları | Audit `--strict` ile koşturuldu, uyarı seviyesi sorunlar bulundu. | Merge engelle / inceleme iste |
| **3** | Regresyon / otomatik geri alma | Benchmark veya güvenlik kapısı geçemedi; geri alındı. | İncele; terfi ETTİRME |
| **4** | İnsan onayı bekliyor | `compliance.human_approval: true` engelliyor. | Hattı tut; reviewer'ı tetikle |
| **5** | Maliyet tavanı aşıldı | `output.cost_tracking.halt_threshold_usd` aşıldı. | Maliyet aşımını incele |
| **130** | Kesildi | Kullanıcı Ctrl+C bastı. | Manuel karar |

Diğer sıfır olmayan exit beklenmedik hata — issue açın.

## CI pattern'lerine eşleme

### GitHub Actions

```yaml
- name: Train
  id: train
  run: forgelm --config configs/run.yaml
  continue-on-error: true

- name: Block on regression
  if: steps.train.outcome == 'failure'
  run: |
    if [ "${{ steps.train.outputs.exit-code }}" = "3" ]; then
      echo "::error::Regresyon tespit edildi — audit log'u inceleyin"
      exit 1
    fi
```

Çoğu hat için basit pattern yeterli:

```yaml
- name: Train
  run: forgelm --config configs/run.yaml
  # Sıfır olmayan exit step'i fail eder. Artifact upload step'i hâlâ çalışır (if: always()).
```

### GitLab CI

```yaml
train:
  script:
    - forgelm --config configs/run.yaml
  allow_failure:
    exit_codes: [4]                    # exit 4 (onay bekleme) CI'yı fail etmez
```

## Hangi durum hangi exit

| Durum | ForgeLM exit |
|---|---|
| YAML'da typo (ör. `learnng_rate`) | 1 |
| YAML'da `${HF_TOKEN}` ama env var yok | 1 |
| `--config` var olmayan dosyaya işaret ediyor | 1 |
| `--strict` ile audit ve PII flag'leri | 2 |
| `--strict` ile audit ve split-arası sızıntı | 3 (sızıntı uyarı değil hata) |
| DPO koşusu, Llama Guard S5 toleransı aştı | 3 |
| Benchmark hellaswag floor altına düştü | 3 |
| Final loss NaN | 3 |
| `compliance.human_approval: true` ve onay imzalanmamış | 4 |
| Maliyet eşiği eğitim ortasında aşıldı | 5 |
| Kullanıcı Ctrl+C | 130 |

## Programatik tespit

Otomatik parsing için ForgeLM exit kodunu bir sidecar dosyaya da yazar:

```text
checkpoints/run/artifacts/exit_status.txt:

3
trigger=safety_regression
regressed_categories=S5
restored_from=./checkpoints/sft-base
```

Ham exit kodlarını korumayan log aggregator'lara stream eden CI runner'larında yardımcı olur.

## "exit 0" tam olarak ne garanti eder

0 ile çıkan koşu:
- Config'i hatasız doğrulamış.
- Modeli ve dataset'i yüklemiş.
- Tüm konfigüre eğitim adımlarını tamamlamış.
- Her benchmark floor'unu geçmiş.
- Her güvenlik eşiğini geçmiş.
- Model card yazmış.
- Annex IV paketi yazmış (konfigüre ise).
- Manifest.json'u tüm artifact'lar üzerinde SHA-256 ile yazmış.
- Opsiyonel: GGUF, deployment config yazmış.
- Audit log'u `run_complete` ile kapatmış.

Bunlardan biri başarısız olursa exit kod sıfır değildir. Tasarım gereği "kısmi başarı" exit kodu yok.

## Uyumluluk garantisi

Exit kodları 0-5 sürümler arası kararlıdır. Yeni kodlar eklenebilir (6, 7, …) ama mevcutların semantiği değişmez. Yukarıdaki kontrata pinli CI hatları ForgeLM yükseltmelerinde çalışmaya devam eder.

## Bkz.

- [CI/CD Hatları](#/operations/cicd) — bu kontratı kullanan pattern'ler.
- [CLI Referansı](#/reference/cli) — bu kodları üreten tüm komutlar.
- [Otomatik Geri Alma](#/evaluation/auto-revert) — exit 3 üretir.
- [İnsan Gözetimi](#/compliance/human-oversight) — exit 4 üretir.
