---
title: Webhook'lar
description: Eğitim olaylarında Slack ve Teams bildirimleri — başlangıç, başarı, hata, otomatik geri alma.
---

# Webhook'lar

ForgeLM eğitim dönüm noktalarında yapılandırılmış webhook fırlatır. Bunları Slack, Teams veya JSON payload kabul eden herhangi bir incident aracına bağlayın — hiç kimsenin log izlemesine gerek kalmadan doğru bağlamı doğru insanlara getirin.

## Hızlı örnek

```yaml
output:
  webhook:
    url: "${SLACK_WEBHOOK}"
    events: ["run_start", "auto_revert", "run_complete", "run_failed"]
    template: "slack"                      # veya teams, generic
```

ForgeLM `${SLACK_WEBHOOK}`'u environment variable'dan okur. Yaygın pattern:

```shell
$ export SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../..."
$ forgelm --config configs/run.yaml
```

## Abone olabileceğiniz olaylar

| Olay | Ne zaman |
|---|---|
| `run_start` | Eğitim başlar. |
| `data_audit_complete` | `forgelm audit` sonrası. |
| `training_epoch_complete` | Her epoch sonrası. (gürültülü; genelde atlanır) |
| `benchmark_complete` | Eval suite sonrası. |
| `safety_eval_complete` | Llama Guard skorlama sonrası. |
| `auto_revert` | Otomatik geri alma tetiklendiğinde. |
| `human_approval_request` | `compliance.human_approval` engellediğinde. |
| `human_approval_granted` | Onay imzalandığında. |
| `model_exported` | `forgelm export` sonrası. |
| `run_complete` | Başarılı çıkış. |
| `run_failed` | Sıfır olmayan çıkış. |

Seçici abone olun — çok-sık webhook spam olur.

## Payload yapısı

Generic format (`slack` ve `teams` template'leri bunu kendi formatlarına sarar):

```json
{
  "event": "auto_revert",
  "ts": "2026-04-29T14:33:04Z",
  "run_id": "abc123",
  "config_path": "configs/customer-support.yaml",
  "trigger": "safety_regression",
  "regressed_categories": ["S5"],
  "details": {...},
  "artifacts_url": "https://compliance-store.example/abc123/"
}
```

## Slack template

```yaml
output:
  webhook:
    url: "${SLACK_WEBHOOK}"
    template: "slack"
    events: ["run_complete", "run_failed", "auto_revert"]
    channel: "#ml-training"                 # opsiyonel override
    mention_on_failure: "@ml-oncall"
```

Üretir:

```text
🔥 ForgeLM otomatik geri alma tetiklendi

Koşu: customer-support v1.2.0 (abc123)
Tetikleyici: S5'te safety_regression
Restore: checkpoints/sft-base'den
Audit log: artifacts/audit_log.jsonl

@ml-oncall lütfen incele.
```

## Microsoft Teams template

```yaml
output:
  webhook:
    url: "${TEAMS_WEBHOOK}"
    template: "teams"
    events: ["auto_revert", "human_approval_request"]
```

Aynı veriyi action button'lı Teams MessageCard olarak üretir.

## Generic template (özel entegrasyonlar)

Kendi dashboard'unuz, incident sisteminiz veya pipeline'ınız için:

```yaml
output:
  webhook:
    url: "https://internal.example/forgelm-events"
    template: "generic"
    events: ["run_start", "run_complete", "run_failed", "auto_revert"]
    headers:
      Authorization: "Bearer ${INCIDENT_API_TOKEN}"
    timeout_seconds: 5
    retries: 3
```

Endpoint yukarıdaki ham yapılandırılmış payload'u alır. ForgeLM JSON POST'lar, 2xx bekler, geçici hatalarda yeniden dener.

## Birden çok hedef

Farklı olayları farklı yerlere göndermek için:

```yaml
output:
  webhooks:
    - url: "${SLACK_WEBHOOK}"
      template: "slack"
      events: ["run_complete", "run_failed"]
    - url: "${PAGERDUTY_WEBHOOK}"
      template: "generic"
      events: ["auto_revert"]                # sadece kritik
    - url: "${INTERNAL_DASHBOARD_URL}"
      template: "generic"
      events: ["*"]                          # dashboard için her şey
```

## Güvenlik

- **Sadece TLS.** ForgeLM üretim build'lerinde HTTP webhook URL'lerini reddeder.
- **Hassas veri redaksiyonu.** API key'ler, tam config'ler ve PII payload'larda varsayılan olarak redakte edilir. `webhook.redact: false` sadece her iki uçta da kontrol sahibi olduğunuzda override edin.
- **SSRF guard.** ForgeLM iç IP'lere (RFC 1918, link-local) işaret eden webhook URL'lerini engeller; `webhook.allow_private: true` ile açıkça izin vermediğiniz sürece. Yanlış konfigüre koşuların iç ağınızı sondalamasını önler.

## Sık hatalar

:::warn
**Webhook sessiz başarısız.** Webhook endpoint'inden 4xx yanıtı eğitimi başarısız etmemeli ama ForgeLM hatayı sessizce yutmamalı. `audit_log.jsonl`'da `webhook_failed` olaylarına bakın; endpoint'inizin neden reddettiğini araştırın.
:::

:::warn
**`training_epoch_complete`'a abone olmak.** 50-epoch eğitimde 50 mesaj demek — Slack rate-limit'ler. Uçlar için `run_start` ve `run_complete` kullanın.
:::

:::tip
**Webhook'ları `--webhook-test` ile test edin.** Canlıya geçmeden önce `forgelm --config X.yaml --webhook-test` çalıştırın — webhook'unuza sentetik payload fırlatır, formatlamayı doğrularsınız. Gerçek eğitim olmaz.
:::

## Bkz.

- [CI/CD Hatları](#/operations/cicd) — webhook'ların doğal yuvası.
- [Otomatik Geri Alma](#/evaluation/auto-revert) — en eyleme dönük webhook'u üretir.
- [İnsan Gözetimi](#/compliance/human-oversight) — webhook-tabanlı onay akışı.
