---
title: Otomatik Geri Alma
description: Benchmark veya güvenlik gerilediğinde son-iyi checkpoint'e geri dön.
---

# Otomatik Geri Alma

Başlangıç noktasından daha kötü güvenlik veya kalite skoru alan bir fine-tuned model, hiç fine-tune etmemekten beterdir. Otomatik geri alma ForgeLM'in güvenlik ağıdır: konfigüre edilmiş bir eşik eğitimden sonra başarısız olursa koşu son-iyi checkpoint'e döner ve yapılandırılmış bir olay kaydı bırakır.

## Karar akışı

```mermaid
flowchart TD
    Start[Eğitim tamamlandı]
    Bench{Benchmark<br/>floor'lar geçti mi?}
    Safety{Güvenlik<br/>eşikleri geçti mi?}
    Loss{Final loss<br/>başlangıca kıyasla?}
    OK([Yeni checkpoint'i terfi ettir<br/>exit 0])
    Revert([Son-iyi'ye dön<br/>exit 3])
    Audit[Audit log'a<br/>olay kaydı ekle]

    Start --> Bench
    Bench -->|geçemedi| Audit
    Bench -->|geçti| Safety
    Safety -->|geçemedi| Audit
    Safety -->|geçti| Loss
    Loss -->|makul| OK
    Loss -->|patladı| Audit
    Audit --> Revert

    classDef ok fill:#1c2030,stroke:#22c55e,color:#e6e7ec
    classDef fail fill:#1c2030,stroke:#ef4444,color:#e6e7ec
    classDef question fill:#161a24,stroke:#0ea5e9,color:#e6e7ec
    class OK ok
    class Revert,Audit fail
    class Bench,Safety,Loss question
```

## Hangi sinyal geri almayı tetikler

| Sinyal | Eşik | Konfigüre edilen alan |
|---|---|---|
| Benchmark görevi floor altında | Görev başı `floors:` ayarı | `evaluation.benchmark.floors` |
| Bloklu kategoride güvenlik gerilemesi | `regression_tolerance` (vars. 0.05) | `evaluation.safety.regression_tolerance` |
| Final loss > başlangıç loss | Her zaman | konfigüre edilemez |
| Final loss NaN/Inf | Her zaman | konfigüre edilemez |
| Özel guard başarısız | Kullanıcı verdiği callable | `evaluation.guards.<isim>` |

Bunlardan herhangi biri geri almayı tetikler.

## Geri alma sırasında ne olur

1. ForgeLM son-iyi checkpoint'i belirler — DPO başarısız olduğunda genelde SFT checkpoint'i, ya da sürdürülen-eğitim senaryosunda önceki koşunun çıktısı.
2. Son-iyi ağırlıkları konfigüre çıktı dizinine kopyalar (kötü olanların üzerine yazar).
3. `audit_log.jsonl`'a olay kaydı yazar:

```json
{
  "ts": "2026-04-29T14:33:04Z",
  "event": "auto_revert",
  "trigger": "safety_regression",
  "regressed_categories": ["S5"],
  "baseline_safety": {"S5": {"max": 0.08}},
  "post_train_safety": {"S5": {"max": 0.42}},
  "restored_from": "./checkpoints/sft-base",
  "exit_code": 3
}
```

4. Opsiyonel olarak webhook fırlatır (Slack, Teams) — bkz. [Webhook'lar](#/operations/webhooks).
5. Exit kodu 3 ile çıkar.

## Konfigürasyon

```yaml
evaluation:
  auto_revert:
    enabled: true
    last_good_checkpoint: "./checkpoints/sft-base"
    notify_on_revert: true              # webhook fırlat
    keep_failed_checkpoint: true        # inceleme için kötü olanı da sakla
    failed_checkpoint_dir: "./checkpoints/failed/"
```

`last_good_checkpoint` belirtilmezse ForgeLM koşu başında yüklü olan modeli (girdi modeli) kullanır.

## Özel guard'lar

Yerleşik kontrollerin ötesinde ek guard'lar kaydedebilirsiniz:

```yaml
evaluation:
  guards:
    custom_metric:
      function: "my_module.check_brand_voice"
      threshold: 0.7                    # fonksiyon ≥ bunu döndürmeli
      severity: "critical"
```

```python
# my_module.py
def check_brand_voice(checkpoint_path: str) -> float:
    """Marka sesi puanını [0, 1] aralığında döndür."""
    # Kendi eval'inizi koşturun...
    return 0.82
```

Özel guard'lar aynı geri alma akışına entegre olur.

## CI/CD entegrasyonu

Otomatik geri alma CI exit kodlarıyla doğal eşleşir:

```yaml
# .github/workflows/train.yml
- name: Eğit ve değerlendir
  run: forgelm --config configs/run.yaml
  # exit 0 = başarı, exit 3 = otomatik geri alma tetiklendi
```

Exit 3'ten gelen CI başarısızlıkları *beklenen* — kapı bir gerilemeyi yakalamış demektir. Bastırmayın; araştırın.

## Sık hatalar

:::warn
**"Bugün üretime girmek için" otomatik geri almayı kapatmak.** Neredeyse her zaman yanlış karar. Gerçekten göndermeniz gerekiyorsa floor'u tek koşu için açık bir yorumla ve takip issue'sıyla düşürün. Audit log override'ı kaydeder.
:::

:::warn
**`last_good_checkpoint` silinmiş yola işaret etmek.** Restore hedefini bulamayan otomatik geri alma yüksek sesle başarısız olur. Eğitime başlamadan önce son-iyi checkpoint'i kararlı bir yola pinleyin.
:::

:::tip
**Otomatik geri almayı sabote ederek test edin.** CI kurulumunda bilerek bir floor'u modelinizin geçemeyeceğini bildiğiniz değere düşürün. Otomatik geri almanın tetiklendiğini, webhook'un postaladığını ve olay kaydının yazıldığını teyit edin. Güvenlik ağını test ederken sorunları keşfetmek, gerçek bir gerilemede keşfetmekten daha iyidir.
:::

## Bkz.

- [Benchmark Entegrasyonu](#/evaluation/benchmarks) — floor eşiklerini tanımlar.
- [Llama Guard Güvenliği](#/evaluation/safety) — güvenlik eşiklerini tanımlar.
- [Webhook'lar](#/operations/webhooks) — geri almada bildir.
- [Audit Log](#/compliance/audit-log) — geri alma olaylarının kaydedildiği yer.
