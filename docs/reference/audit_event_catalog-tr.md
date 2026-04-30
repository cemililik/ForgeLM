# Audit Event Kataloğu

> **Hedef kitle:** EU AI Act Madde 12 kayıt-tutma artefaktlarını inceleyen ForgeLM operatörleri, denetçiler ve aşağı akış doğrulayıcıları.
> **Ayna:** [audit_event_catalog.md](audit_event_catalog.md)

Bu katalog, ForgeLM'in EU AI Act Madde 12 tarafından zorunlu kılınan, append-only ve hash-zincirli kayıt-tutma artefaktı olan `audit_log.jsonl`'a yazabileceği tüm event'leri sıralar. Her satır ortak bir zarf paylaşır; aşağıdaki satırlardan birini `event` alanı seçer.

## Ortak zarf

Her satır, en azından aşağıdaki alanları içeren tek bir JSON nesnesidir:

| Alan          | Tip     | Açıklama                                                                                                  |
|---------------|---------|-----------------------------------------------------------------------------------------------------------|
| `timestamp`   | string  | ISO-8601 UTC zaman damgası (`datetime.now(timezone.utc).isoformat()`).                                    |
| `run_id`      | string  | Eğitim koşusu başına stabil tanımlayıcı (`fg-<uuid12>`).                                                  |
| `operator`    | string  | İnsan-atfedilebilir kimlik. `$FORGELM_OPERATOR` ya da `<getpass.getuser()>@<hostname>` üzerinden.         |
| `event`       | string  | Bu kataloğa ait noktalı event adı.                                                                        |
| `prev_hash`   | string  | Önceki satırın SHA-256'sı (ilk girdi için `"genesis"`). Tampering-evident hash zincirini oluşturur.       |
| `_hmac`       | string? | Sadece `FORGELM_AUDIT_SECRET` set edildiğinde mevcut. `_hmac` olmadan satırın HMAC-SHA-256'sı.            |
| _payload_     | değişir | Her satırda ayrı listelenen, event'e özel anahtarlar.                                                     |

Hash zinciri, satır diske düştükten (`flush` + `fsync`) sonra ilerler; kirli bir kapanış zinciri resume için bütün bırakır.

## Event sözlüğü

### Pipeline yaşam döngüsü

| Event                      | Ne zaman emit edilir                                                            | Payload (zarfa ek olarak)                                                          | Madde |
|----------------------------|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|-------|
| `training.started`         | Trainer fine-tuning koşusunu başlatır.                                          | `trainer_type`, `model`, `dataset`, `config_path`                                  | 12    |
| `training.completed`       | Fine-tuning başarıyla tamamlanır (değerlendirme kapıları sonrası).              | `eval_loss`, `safety_passed`, `judge_score`                                        | 12    |
| `training.failed`          | Trainer tamamlanmadan bir hata ile iptal olur.                                  | `failure_reason`, `stage`                                                          | 12    |
| `pipeline.completed`       | Uçtan uca CLI koşusu (eğitim + değerlendirme + dışa aktarma) 0 koduyla biter.   | `exit_code`, `duration_seconds`                                                    | 12    |

### Madde 14 — İnsan Gözetimi

| Event                        | Ne zaman emit edilir                                                                                             | Payload                                              | Madde |
|------------------------------|-------------------------------------------------------------------------------------------------------------------|------------------------------------------------------|-------|
| `human_approval.required`    | `requires_human_approval: true` işaretli bir kapı pipeline'ı duraklatıp operatör kararını bekler.                | `gate`, `reason`, `metrics`                          | 14    |
| `human_approval.granted`     | Operatör duraklatılan kapıyı onayladı. _(Faz 9 — placeholder; henüz emit edilmiyor.)_                            | `gate`, `approver`, `comment`                        | 14    |
| `human_approval.rejected`    | Operatör duraklatılan kapıyı reddetti. _(Faz 9 — placeholder; henüz emit edilmiyor.)_                            | `gate`, `approver`, `comment`                        | 14    |

### Madde 15 — Model Bütünlüğü (auto-revert + güvenlik)

| Event                          | Ne zaman emit edilir                                                                                              | Payload                                                       | Madde |
|--------------------------------|--------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------|-------|
| `model.reverted`               | Auto-revert kalite regresyonu sonrası önceki bir checkpoint'i geri yükledi. _(Faz 8 — webhook bağlantılı.)_       | `from_checkpoint`, `to_checkpoint`, `reason`, `metrics_delta` | 15    |
| `audit.classifier_load_failed` | Güvenlik sınıflandırıcısı (örn. Llama Guard) yüklenemedi. Koşu yine `passed=False` kaydeder.                       | `classifier`, `reason`                                        | 15    |

### Madde 11 + Ek IV — Uyumluluk artefaktları

| Event                            | Ne zaman emit edilir                                                          | Payload                                          | Madde         |
|----------------------------------|-------------------------------------------------------------------------------|--------------------------------------------------|---------------|
| `compliance.governance_exported` | Madde 10 veri yönetişim raporu diske yazıldı.                                 | `output_path`, `dataset_count`                   | 10            |
| `compliance.governance_failed`   | Yönetişim raporu üretimi iptal edildi (örn. şema uyumsuzluğu).                | `failure_reason`                                 | 10            |
| `compliance.artifacts_exported`  | Ek IV teknik dokümantasyon paketi (manifest, model card, audit zip) yazıldı.  | `output_dir`, `files`                            | 11, Ek IV     |

### CLI / göç

| Event                       | Ne zaman emit edilir                                                                                  | Payload                          | Madde |
|-----------------------------|--------------------------------------------------------------------------------------------------------|----------------------------------|-------|
| `cli.legacy_flag_invoked`   | Deprecated bir CLI flag'i kullanıldı. _(Faz 13 — placeholder; henüz emit edilmiyor.)_                  | `flag`, `replacement`, `version` | 12    |

### Audit-sistem event'leri (meta)

| Event                          | Ne zaman emit edilir                                                                                      | Payload                              | Madde |
|--------------------------------|------------------------------------------------------------------------------------------------------------|--------------------------------------|-------|
| `audit.classifier_load_failed` | _(Yukarıdaki Madde 15 satırına bakın.)_                                                                    | `classifier`, `reason`               | 15    |
| `audit.cross_run_continuity`   | Mevcut bir log dizinine işaret eden ikinci-veya-sonraki AuditLogger örneğinin ilk yazımı.                  | `previous_chain_head`                | 12    |

## Yeni bir event eklemek

1. Mevcut isim alanlarını (`training.*`, `compliance.*`, `audit.*`, `human_approval.*`, `model.*`, `cli.*`) takip eden noktalı bir ad seçin.
2. Yukarıdaki tabloya, payload anahtarları ve desteklediği Madde dahil olmak üzere bir satır ekleyin.
3. Satırı [audit_event_catalog.md](audit_event_catalog.md)'ye yansıtın.
4. `AuditLogger.log_event(event, **payload)` üzerinden emit edin. `audit_log.jsonl`'a doğrudan `json.dump` çağırmayın; hash zinciri kanonik yazıcıya bağımlıdır.

## Tampering-evidence özeti

| Mekanizma                | Şuna karşı koruma sağlar                                                          | Her zaman açık mı?                                |
|--------------------------|-----------------------------------------------------------------------------------|---------------------------------------------------|
| SHA-256 hash zinciri     | Tek-satır düzenlemeler, silmeler, sıralama değişiklikleri.                        | Evet.                                             |
| Genesis manifest sidecar | Tüm log'un "genesis"'e geri kesilmesi.                                            | Evet (ilk event'te bir kez yazılır).              |
| `flock(LOCK_EX)`         | Aynı dizini paylaşan eşzamanlı trainer'lardan iç içe yazımlar.                    | Evet (Unix); Windows'ta no-op.                    |
| `flush` + `fsync`        | Buffer yazımı ile zincir ilerleme arasında güç-kesme / kernel-panic kaybı.        | Evet.                                             |
| Satır başına HMAC-SHA-256| Log yeniden yazımı sonrası sahte yeniden imzalama.                                | Sadece `FORGELM_AUDIT_SECRET` set olduğunda.      |

## Webhook olayları

Webhook payload'ları (Slack / Teams / jenerik HTTP) operatör bildirimlerine kapsamlanmış ayrı bir sözlüktür, regülasyon kaydı değil. Webhook olayları `audit_log.jsonl`'a **eklenmez**; yan-kanal bildirim bus'ı üzerinde gider. Kanonik yaşam döngüsü sözlüğü ayrıca [logging-observability.md](../standards/logging-observability.md)'da da belgelenmiştir.

Bu beş yaşam döngüsü olayı, webhook alıcılarının `WebhookNotifier`'dan
beklemesi gereken **tek** olaylardır. Her biri, karşılık gelen bir
denetim günlüğü olayını yansıtır; böylece aşağı akıştaki bir operatör
webhook ping → denetim girdisi korelasyonunu `run_name` + zaman
damgasıyla kurabilir. Uygulama: `forgelm/webhook.py`.

| Webhook `event` | Denetim günlüğü karşılığı | Tetikleyici | Kapı (gate) | Zorunlu payload alanları |
|---|---|---|---|---|
| `training.start` | `training.started` | `train()` çağrıldı, model yüklenmeden önce. | `webhook.notify_on_start` | `run_name`, `status="started"` |
| `training.success` | `pipeline.completed` | Tüm kapılar geçildi, insan onayı gerekmiyor. | `webhook.notify_on_success` | `run_name`, `status="succeeded"`, `metrics` |
| `training.failure` | `pipeline.failed` | Eğitim sürecinin kendisi hata fırlattı (OOM, veri seti hatası, yakalanmayan istisna). | `webhook.notify_on_failure` | `run_name`, `status="failed"`, `reason` (maskelenmiş, ≤2048 karakter) |
| `training.reverted` | `model.reverted` | Eğitim sonrası bir kapı (değerlendirme, güvenlik, hakem, benchmark) çalışmayı reddetti ve `_revert_model` adaptörleri sildi. | `webhook.notify_on_failure` | `run_name`, `status="reverted"`, `reason` (maskelenmiş, ≤2048 karakter) |
| `approval.required` | `human_approval.required` | Çalışma başarılı oldu, `evaluation.require_human_approval=true`, model insan incelemesi için staging'de (EU AI Act Madde 14). | `webhook.notify_on_success` | `run_name`, `status="awaiting_approval"`, `model_path` |

### Bu yaşam döngüsü durumlarından ikisinin neden ayrıldığı

- **`training.failure` vs `training.reverted`** — dashboard'ların
  "trainer çöktü" ile "trainer başarılı oldu fakat kalite / güvenlik /
  hakem kapısı reddetti" durumlarını ayırt etmesi gerekir. Her ikisi
  de operasyonel olarak eyleme dönüşürdür, ancak farklı runbook'lar
  gerektirir. Faz 8, bir Slack kanalının iki vakayı farklı renk
  kodlayabilmesi için (`#ff0000` ve `#ff9900`) tam da bu nedenle
  `notify_reverted`'i tanıttı.
- **`approval.required`** — çalışma başarılı olduktan *sonra*, fakat
  operatör dağıtımı onaylamadan *önce* yayılır. Bu bir başarısızlık
  değil; bir duraklamadır. `training.failure` üzerinde otomatik
  çağrı yapan alıcılar `approval.required` üzerinde çağrı yapmamalı.

### Payload şeması

Her webhook olayı aynı zarfı taşır:

```json
{
  "event": "training.start | training.success | training.failure | training.reverted | approval.required",
  "run_name": "<dize>",
  "status": "started | succeeded | failed | reverted | awaiting_approval",
  "metrics": {"<isim>": <sayı>, ...},
  "reason": "<maskelenmiş dize ya da null>",
  "model_path": "<dosya sistemi yolu ya da null>",
  "attachments": [{"title": "...", "text": "...", "color": "..."}]
}
```

`metrics`, `reason` ve `model_path` her zaman şemada bulunur; yalnızca
ihtiyaç duyan olaylarda doldurulur. `attachments`, Slack uyumlu blok'tur
— diğer alıcılar görmezden gelebilir.

### Güvenlik garantileri

1. **Sebepler maskelenir.** Her `reason` alanı, taşıma öncesi
   `forgelm.data_audit.mask_secrets` üzerinden geçer; böylece AWS /
   GitHub / Slack / OpenAI / Google / JWT / özel-anahtar blokları /
   Azure storage dizeleri süreçten dışarı çıkmaz. `data_audit` ithal
   edilemezse, ham dize yerine alan
   `"[REDACTED — secrets masker unavailable]"` ile değiştirilir.
2. **Sebepler 2048 karaktere kırpılır.** Bundan uzun stack trace'ler
   `"… (truncated)"` ile kesilir.
3. **Model ağırlıkları yok.** `approval.required` yalnızca staging
   dosya sistemi yolunu taşır. Ağırlıklar diskte kalır; o dizini zaten
   operatör kontrol eder.
4. **Webhook URL'si sızdırılmaz.** URL'ler günlüklerde maskelenir
   (`scheme://host/<ilk-segment>/...`) ve 2xx olmayan yanıt gövdesi
   bastırılır.
5. **SSRF koruması.** `webhook.allow_private_destinations=true`
   ayarlanmadığı sürece özel / loopback / link-local hedefler
   reddedilir.

### Saklama rehberi

Webhook payload'ları **geçicidir**. Denetim kaydı değildir. Uzun süreli
geçmişe ihtiyaç duyan alıcılar, webhook trafiğini arşivlemek yerine
denetim JSONL dosyasının (`<output_dir>/compliance/audit_log.jsonl`) anlık
görüntüsünü almalıdır; çünkü denetim günlüğü yalnız-eklenir
hash-zincirli kayıttır ve webhook akışı en-iyi-çabadır (best-effort).
