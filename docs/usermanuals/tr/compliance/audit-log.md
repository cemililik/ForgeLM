---
title: Audit Log
description: Eğitim, değerlendirme ve geri alma kararlarını append-only event log olarak tutar — Madde 12.
---

# Audit Log

EU AI Act Madde 12, yüksek-riskli AI sistemlerinin operasyonel olarak ilgili olayların log'unu tutmasını gerektirir. ForgeLM'in `audit_log.jsonl` dosyası; eğitim başlangıcı, eval kapıları, otomatik geri alma kararları ve model export'unu kapsayan, append-only ve SHA-256-anchored bir olay dizisidir.

## Format

Satır başına bir JSON nesnesi:

```jsonl
{"ts":"2026-04-29T14:01:32Z","seq":1,"event":"run_start","run_id":"abc123","config_hash":"sha256:dead..."}
{"ts":"2026-04-29T14:01:35Z","seq":2,"event":"data_audit_complete","verdict":"clean","..."}
{"ts":"2026-04-29T14:18:55Z","seq":3,"event":"training_epoch_complete","epoch":1,"loss":1.42}
{"ts":"2026-04-29T14:33:04Z","seq":4,"event":"benchmark_complete","verdict":"pass"}
{"ts":"2026-04-29T14:33:08Z","seq":5,"event":"safety_eval_complete","verdict":"pass"}
{"ts":"2026-04-29T14:33:10Z","seq":6,"event":"run_complete","exit_code":0,"prev_hash":"sha256:beef..."}
```

Her kayıtta:
- **`ts`** — ISO-8601 UTC zaman damgası.
- **`seq`** — koşu içinde monotonik sıra numarası (her koşuda sıfırlanır).
- **`event`** — olay tipi (aşağıda).
- **`prev_hash`** — önceki kaydın SHA-256'sı (tamper-evidence için zincirleme).
- Olaya özgü alanlar.

## Olay tipleri

| Olay | Ne zaman |
|---|---|
| `run_start` | Her `forgelm` çağrısının başında. |
| `config_validated` | `--dry-run` geçtikten sonra. |
| `data_audit_complete` | `forgelm audit` koşturulduktan sonra. |
| `training_epoch_complete` | Her eğitim epoch'undan sonra. |
| `training_step_milestone` | Konfigüre adım aralıklarında (varsayılan 1000). |
| `benchmark_complete` | Benchmark suite koşturulduktan sonra. |
| `safety_eval_complete` | Llama Guard skorlamasından sonra. |
| `auto_revert` | Otomatik geri alma tetiklendiğinde. |
| `human_approval_request` | `compliance.human_approval` engellediğinde. |
| `human_approval_granted` | Onay imzalandığında. |
| `model_exported` | `forgelm export` deploy edilebilir artifact yazdığında. |
| `run_complete` | Başarılı çıkışta. |
| `run_failed` | Sıfır olmayan çıkışta. |

## Tasarım gereği append-only

ForgeLM önceki log kayıtlarını asla yeniden yazmaz. Yeni olaylar sona eklenir. Zincirlenen `prev_hash` modifikasyonu tespit edilebilir kılar: N. kaydı değiştirirseniz N+1'den itibaren her kaydın `prev_hash` referansı yanlış olur.

:::warn
**Konvansiyon, zorlama değil.** Toolkit append-only yazar ve zinciri hashler ama dosya filesystem'inizde — yazma erişimi olan herkes düzenleyebilir. Gerçek tamper-evidence için log'u ayrı bir write-once depoya gönderin (S3 Object Lock, ledger DB, HSM). Bu sizin operasyonel sorumluluğunuzdur.
:::

## Bütünlük doğrulama

```shell
$ forgelm verify-log checkpoints/run/artifacts/audit_log.jsonl
✓ 87 kayıt, tüm zaman damgaları monotonik
✓ tüm prev_hash zincirleri geçerli
✓ seq numaralarında boşluk yok
```

`verify-log` zincir kırığı raporlarsa, log üretimden sonra değiştirilmiş demektir. Kanıt olarak işlem görmeden önce araştırın.

## Koşu başı vs proje başı

Her eğitim koşusu kendi `audit_log.jsonl`'ını o koşunun `artifacts/` dizininde üretir. Proje başı geçmiş için ForgeLM proje kökünde `.forgelm/global-audit-log.jsonl`'ı da tutar (varsayılan gitignore'da — commit'e karar siz verin).

Global log *koşular-arası* olayları kaydeder:

- Projedeki her koşu için `run_start` ve `run_complete`.
- Manuel model terfi ve geri alma.
- Yapılandırma değişiklikleri (ForgeLM yeni YAML sürümlerini tespit ettiğinde).

## Konfigürasyon

```yaml
compliance:
  audit_log:
    enabled: true
    path: "${output.dir}/artifacts/audit_log.jsonl"
    step_milestone_interval: 1000             # her N adımda step olayı
    include_config_dump: true                  # run_start olayında tam config
    redact_secrets: true                       # dump'lanmış config'te api key'leri maskele
```

## Dış depolara yönlendirme

Üretimde tamper-evidence için log kayıtlarını ayrı bir write-once veya append-only depoya yönlendirin:

```yaml
compliance:
  audit_log:
    forward_to:
      - type: "s3"
        bucket: "compliance-audit-logs"
        prefix: "forgelm/{run_id}/"
        object_lock: true
      - type: "syslog"
        host: "audit.internal:514"
        protocol: "tcp"
```

ForgeLM her yayınlanan olayı konfigüre hedeflere yansıtır. Dış depo erişilemezse koşu başarısız olur (audit olaylarını sessizce düşürmemek için).

## Log'u okuma

İnsan incelemesi için:

```shell
$ jq -r '.event + "\t" + .ts' checkpoints/run/artifacts/audit_log.jsonl
run_start                  2026-04-29T14:01:32Z
config_validated           2026-04-29T14:01:33Z
data_audit_complete        2026-04-29T14:01:35Z
training_epoch_complete    2026-04-29T14:18:55Z
...
run_complete               2026-04-29T14:33:10Z
```

Dashboard için JSONL doğal olarak Loki, OpenSearch veya herhangi bir log-aggregation aracına akar.

## Sık hatalar

:::warn
**"Bir typo'yu düzeltmek için" log'u editlemek.** Yapmayın. Kozmetik düzenlemeler bile zincir hash'ini bozar ve audit değerini düşürür. Gerçekten bilgi düzeltmek gerekirse `corrects_seq` referansıyla yeni bir `correction` olayı ekleyin.
:::

:::warn
**Log'u sadece eğitim host disklerinde tutmak.** Disk arızası = kaybedilen audit kanıtı. Her zaman dayanıklı depolamaya yönlendirin (versiyonlu + Object Lock'lu S3, ledger DB).
:::

:::tip
**Üretimde koşular arası log zincirleyin.** Bir checkpoint'i üretime terfi ettirdiğinizde önceki sürümü referans alan `model_promoted` olayı ekleyin. Denetçiler eğitimden deployment'a kesintisiz chain-of-custody görmeyi sever.
:::

## Bkz.

- [Annex IV](#/compliance/annex-iv) — audit log'a işaret eden teknik doküman.
- [Otomatik Geri Alma](#/evaluation/auto-revert) — `auto_revert` olaylarını üretir.
- [İnsan Gözetimi](#/compliance/human-oversight) — onay olaylarını üretir.
