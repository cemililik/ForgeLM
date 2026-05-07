---
title: Webhook'lar
description: Eğitim olaylarında Slack ve Teams bildirimleri — başlangıç, başarı, hata, otomatik geri alma.
---

# Webhook'lar

ForgeLM eğitim dönüm noktalarında yapılandırılmış webhook fırlatır. Bunları Slack, Teams veya JSON payload kabul eden herhangi bir incident aracına bağlayın — hiç kimsenin log izlemesine gerek kalmadan doğru bağlamı doğru insanlara getirin.

## Hızlı örnek

```yaml
webhook:
  url_env: "SLACK_WEBHOOK"           # URL'yi $SLACK_WEBHOOK'tan runtime'da okur
  notify_on_start: true              # default true
  notify_on_success: true            # default true
  notify_on_failure: true            # default true (training.failure + training.reverted'i kapsar)
```

Notifier generic JSON payload yayar — Slack ve Teams bunu incoming-webhook
uçlarından doğrudan kabul eder. Per-event abonelik şu an konfigüre
edilemiyor; üç `notify_on_*` flag'iyle hangi yaşam-döngüsü olaylarının
fırlatılacağı kaba ayarlanır.

ForgeLM `${SLACK_WEBHOOK}`'u environment variable'dan okur. Yaygın pattern:

```shell
$ export SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../..."
$ forgelm --config configs/run.yaml
```

## Wire-format event'ler

ForgeLM tam **beş** webhook event'i yayar. Aşağıdaki tablo
[`docs/reference/audit_event_catalog.md`](#/reference/audit-event-catalog)
ile aynalanan kanonik yüzeydir:

| Event | Ne zaman fırlar | Gate |
|---|---|---|
| `training.start` | `train()` başlar, model yüklenmeden önce. | `webhook.notify_on_start` |
| `training.success` | Tüm gate'ler geçer; insan-onay gereksinimi yok. | `webhook.notify_on_success` |
| `training.failure` | Eğitim raise ediyor (OOM, dataset hatası, yakalanmamış istisna). | `webhook.notify_on_failure` |
| `training.reverted` | Eğitim-sonrası bir gate (eval / safety / judge / benchmark) koşumu reddetti ve `_revert_model` adapter'ları geri aldı. | `webhook.notify_on_failure` |
| `approval.required` | Koşum başarılı, `evaluation.require_human_approval=true` set, model review için staged (EU AI Act Madde 14). | `webhook.notify_on_success` |

## Payload yapısı

Tek generic JSON şekil — Slack / Teams / Discord hepsi bunu incoming-webhook
uçlarından doğrudan kabul eder; ForgeLM provider'a-özel template'lerle
sarmalama **yapmaz**:

```json
{
  "event": "training.reverted",
  "run_name": "customer-support-v1.2.0",
  "status": "reverted",
  "reason": "safety regression: S5 hate-speech +0.18 over baseline"
}
```

Payload anahtarları event'e göre değişir; tam per-event alan listesi
[`docs/reference/audit_event_catalog.md`](#/reference/audit-event-catalog)
*Webhook lifecycle events* tablosundadır.

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
