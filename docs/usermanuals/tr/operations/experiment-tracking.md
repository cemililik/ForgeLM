---
title: Deney Takibi
description: report_to ayarı üzerinden W&B, MLflow ve TensorBoard entegrasyonu.
---

# Deney Takibi

ForgeLM deney takibini yeniden icat etmez — ekibinizin zaten kullandığı şeye `training.report_to` alanı üzerinden entegre olur. W&B, MLflow, TensorBoard ve Comet ML birinci-sınıf desteklenir.

## Hızlı örnek

```yaml
training:
  trainer: "sft"
  report_to: ["wandb", "tensorboard"]    # aynı anda ikisi
  run_name: "customer-support-v1.2.0"
  tags: ["dpo", "qlora", "tr"]
```

ForgeLM her konfigüre backend'e loss, learning rate, eval metrikleri ve benchmark puanları akıtır.

## Desteklenen backend'ler

### Weights & Biases (W&B)

```yaml
training:
  report_to: ["wandb"]
  wandb:
    project: "forgelm-customer-support"
    entity: "acme-ml"
    api_key: "${WANDB_API_KEY}"
    log_artifacts: true                  # W&B'a checkpoint yükle
```

Auth: `WANDB_API_KEY` environment variable'ını ayarlayın veya eğitim host'unda bir kez `wandb login` çalıştırın.

### MLflow

```yaml
training:
  report_to: ["mlflow"]
  mlflow:
    tracking_uri: "http://mlflow.internal:5000"
    experiment_name: "customer-support"
    registry_uri: "http://mlflow.internal:5000"
    log_model: true                      # MLflow Model Registry'e terfi
```

Auth: standart MLflow env var'ları (`MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` veya token).

### TensorBoard

```yaml
training:
  report_to: ["tensorboard"]
  tensorboard:
    log_dir: "${output.dir}/tensorboard"
```

Dış servis gerekmez — log dosyaları yereldir.

### Comet ML

```yaml
training:
  report_to: ["comet_ml"]
  comet_ml:
    api_key: "${COMET_API_KEY}"
    project_name: "forgelm-customer-support"
```

## Loglanan şeyler

| Metrik | Ne zaman |
|---|---|
| `train/loss` | Her adım |
| `train/lr` | Her adım |
| `train/grad_norm` | Her adım (`log_grad_norm: true` ise) |
| `eval/loss` | Her eval aralığı |
| `benchmark/<görev>` | Koşu başına bir kez (eval sonrası) |
| `safety/<kategori>/max` | Koşu başına bir kez (güvenlik eval sonrası) |
| `safety/<kategori>/mean` | Koşu başına bir kez |
| `system/gpu_utilization` | Her 30s'de örneklenir |
| `system/vram_used_gb` | Her 30s'de örneklenir |

## Koşu adlandırma ve etiketler

```yaml
training:
  run_name: "customer-support-{config_hash}"   # interpolasyon destekli
  tags: ["dpo", "qlora", "tr", "v1.2"]
  notes: "truthfulqa floor'unu yakalamak için beta 0.1'den 0.15'e çıkarıldı"
```

`notes` alanı, prose annotasyonu destekleyen her backend'de kaydedilir.

## Artifact yönetimi

W&B ve MLflow için ForgeLM checkpoint'i ve audit paketini artifact olarak yükleyebilir:

```yaml
training:
  wandb:
    log_artifacts: true                  # tam checkpoint + paket
    artifact_type: "model"
```

Çok büyük checkpoint'ler için W&B/MLflow artifact store'larından çok model registry (HuggingFace Hub) tercih edin. Free tier'lar küçük boyutlarda sınırlanır.

## Koşu karşılaştırma

Her backend'in UI'sı karşılaştırmayı doğal şekilde halleder — karşılaştırılabilir koşular `run_name` öneki, etiketler ve config hash paylaşır. Yerleşik CLI özeti yolda:

> Not: `forgelm compare-runs` subcommand'ı v0.6.0+ Pro CLI seviyesi için planlanmıştır ([Phase 13 yol haritası](#/roadmap/phase-13)). Bugün aynı karşılaştırma tracking backend'inizin UI'sı (W&B / MLflow / Comet) veya her koşunun JSON envelope'una karşı küçük bir `jq` ile koşturulur.

Bugünkü çalışan akış (W&B / MLflow / Comet UI canonical yüzey; aşağıdaki ad-hoc CLI karşılaştırma için `jq` kısayolu):

```shell
$ for v in v1.0 v1.1 v1.2; do
    jq --arg v "$v" '{run: $v, hellaswag: .benchmark.hellaswag, truthfulqa: .benchmark.truthfulqa, S5_max: .safety.S5}' \
       runs/$v/eval.json
  done
```

Özel `forgelm compare-runs` UX'i (planlanan v0.6.0+, BUGÜN runnable DEĞİL):

```text
# preview (planlanan v0.6.0+ Pro CLI — şu anda runnable değil)
forgelm compare-runs runs/v1.0 runs/v1.1 runs/v1.2
                  v1.0    v1.1    v1.2
hellaswag        0.612   0.617   0.621
truthfulqa       0.480   0.482   0.475   ↓
S5_max           0.041   0.038   0.082   ↑↑
loss             1.43    1.39    1.35
```

Oklar otomatik türetilir: anlamlı iyileşme yeşil, regresyon kırmızı.

## Sık hatalar

:::warn
**API key'leri hardcoded yapmak.** W&B / MLflow / Comet key'lerini doğrudan YAML'a koymayın. Her zaman `${ENV_VAR}` interpolasyonu kullanın. Sırların dump'lanmış config'e dahil olmadığını teyit etmek için `audit_log.jsonl`'a bakın.
:::

:::warn
**Erişilemeyen backend'lere raporlama.** `wandb.ai` çalışmıyorsa veya firewall'unuz engelliyorsa ForgeLM uyarı bırakır ama eğitimi başarısız etmez. Uyarıları izleyin; aksi halde hiçbir şeyin loglanmadığını kaçırabilirsiniz.
:::

:::tip
**Birden çok backend paralel kullanın.** Bir koşu sırasında lokal debugging için TensorBoard, sonradan ekipler-arası işbirliği için W&B. İkisini de konfigüre edin — ekstra maliyet yok.
:::

## Bkz.

- [Konfigürasyon Referansı](#/reference/configuration) — tam `report_to` ve backend ayarları.
- [JSON Çıktı Modu](#/operations/cicd) — kendi takibinize log'ları pipe etmek için.
