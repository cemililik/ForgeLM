# `forgelm approvals` — Subcommand Referansı

> **Hedef kitle:** Madde 14 insan-onay kararı bekleyen koşumları keşfeden ForgeLM operatörleri ve tek bir koşumun audit zincirini uçtan uca okuyan denetçiler.
> **Ayna:** [approvals_subcommand.md](approvals_subcommand.md)

`forgelm approvals`, [`forgelm approve` / `forgelm reject`](approve_subcommand.md)'in **keşif tamamlayıcısıdır** (Phase 37). `--output-dir` altındaki `audit_log.jsonl`'i tarar ve karar bekleyen tüm koşumları (`--pending`) veya tek bir koşum için tam audit zincirini (`--show RUN_ID`) raporlar.

Subcommand salt-okunurdur: audit log'u, staging dizinini veya başka herhangi bir on-disk artefact'ı asla değiştirmez.

## Synopsis

```text
forgelm approvals --pending --output-dir DIR
                  [--output-format {text,json}]

forgelm approvals --show RUN_ID --output-dir DIR
                  [--output-format {text,json}]
```

`--pending` ve `--show` karşılıklı dışlayıcıdır (argparse zorunluluğu uygular). Tam olarak biri verilmelidir.

| Argüman / flag | Zorunlu | Açıklama |
|---|---|---|
| `--pending` | birinden biri | Audit log'unda eşleşen terminal karar (`granted` / `rejected`) bulunmayan `human_approval.required` event'i taşıyan tüm koşumları listeler. |
| `--show RUN_ID` | birinden biri | Tek bir koşum için tam approval-gate audit zincirini (talep → karar) artı on-disk staging dizin yapısını yazdırır. |
| `--output-dir DIR` | evet | `audit_log.jsonl` ve `final_model.staging/` içeren training output dizini. |
| `--output-format {text,json}` | hayır (varsayılan `text`) | `json`, CI tüketicileri için stdout'a tam olarak bir yapısal nesne yazdırır. |

## `--pending` ne yapar

`forgelm.cli.subcommands._approvals._handle_pending` içinde uygulanır:

1. `audit_log.jsonl`'in var olduğunu ve okunabilir olduğunu doğrular (`forgelm approve` ile aynı `_assert_audit_log_readable_or_exit` helper'ına delege eder).
2. Zinciri `human_approval.required` event'leri için tarar.
3. Her böyle event için, aynı `run_id`'de daha sonraki terminal karar (`granted` / `rejected`) tarar. Terminal kararı olmayan koşumlar pending olarak işaretlenir.
4. `RUN_ID`, `AGE` (şimdiye göre), `REQUESTED_AT` (ISO-8601), `STAGING` (present / missing) içeren bir tablo yazdırır.

Örnek text çıktı:

```text
Pending approvals (2):

RUN_ID            AGE   REQUESTED_AT               STAGING
----------------  ----  -------------------------  -------
fg-abc123def456   3h    2026-04-30T11:33:10+00:00  present
fg-def456abc789   1d    2026-04-29T14:12:55+00:00  present
```

Örnek JSON zarfı:

```json
{"success": true, "pending": [{"run_id": "fg-abc123def456", "requested_at": "2026-04-30T11:33:10+00:00", "age": "3h", "staging": "present"}], "count": 1}
```

## `--show RUN_ID` ne yapar

`forgelm.cli.subcommands._approvals._handle_show` içinde uygulanır:

1. `--pending` ile aynı audit-log okunabilirlik kapısı.
2. Verilen `run_id` için her event'i replay eder (`human_approval.required`, `human_approval.granted`, `human_approval.rejected`).
3. Staging dizin içeriğini listeler (mevcutsa).

Bilinmeyen bir `run_id` üzerinde `--show` net bir hata mesajıyla 1 koduyla çıkar.

Örnek text çıktı:

```text
Run: fg-abc123def456
Status: pending

Audit chain (oldest first):
  [2026-04-30T11:33:10+00:00] human_approval.required — require_human_approval=true

Staging contents (4 entries):
  - adapter_config.json
  - adapter_model.safetensors
  - tokenizer.json
  - tokenizer_config.json
```

Örnek JSON zarfı:

```json
{"success": true, "run_id": "fg-abc123def456", "status": "pending", "events": [{"event": "human_approval.required", "timestamp": "2026-04-30T11:33:10+00:00", "operator": "gha:Acme/pipelines:training:run-42"}], "staging": {"path": "outputs/run42/final_model.staging.fg-abc123def456", "entries": ["adapter_config.json", "adapter_model.safetensors", "tokenizer.json", "tokenizer_config.json"]}}
```

## Yayılan audit event'leri

**Hiçbiri.** `forgelm approvals` strict salt-okunur bir inspector'dır ve audit event yaymaz. Zincirde göreceğiniz event'ler yalnızca trainer (`human_approval.required`) ve `forgelm approve` / `forgelm reject` (`human_approval.granted` / `.rejected`) tarafından üretilenlerdir.

## Exit kodları

| Kod | Anlamı |
|---|---|
| 0 | Listeleme veya `--show` başarılı. `--pending` kuyruk boşken 0 döner (pending karar yok geçerli yanıttır). |
| 1 | Config hatası: `audit_log.jsonl` okunamaz veya bozuk, ne `--pending` ne `--show` verilmiş (argparse genelde yakalar), `--show` üzerinde bilinmeyen `run_id`. |
| 2 | Runtime hatası: zinciri okurken veya staging dizinini listelerken I/O başarısızlığı. |

Kod 3 (`EXIT_EVAL_FAILURE`) ve 4 (`EXIT_AWAITING_APPROVAL`) bu subcommand'ın yüzeyinin parçası değildir.

## CI kullanım deseni

JSON zarfı desteklenen CI yüzeyidir:

```bash
# Her staged model bir karara sahip olana kadar deploy job'ını blokla.
pending=$(forgelm approvals --pending --output-dir ./outputs --output-format json | jq '.count')
if [ "$pending" -gt 0 ]; then
    echo "::warning::$pending onay hâlâ bekliyor"
    exit 1
fi
```

Daha zengin bir policy kuran operatörler (örn. "herhangi bir bekleyen karar N saatten eskiyse deploy'u blokla") `age` field'ını parse eder. Text çıktısını yalnızca tavsiye olarak ele alın — JSON zarfı stabil sözleşmedir.

## Bkz.

- [`approve_subcommand.md`](approve_subcommand.md) — terminal karar tamamlayıcısı (`approve` / `reject`).
- [`../guides/human_approval_gate.md`](../guides/human_approval_gate.md) — deployer akışı.
- [`audit_event_catalog.md`](audit_event_catalog.md) — bu subcommand tarafından okunan `human_approval.*` satırları dahil tam event sözlüğü.
- [`../qms/access_control.md`](../qms/access_control.md) §6 — segregation-of-duties cookbook (`--show`'un projelendirdiği `human_approval.granted` satırlarını kullanır).
