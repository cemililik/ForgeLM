---
title: JSON çıktı şemaları
description: Her forgelm subcommand için kilitli --output-format json envelope yapısı. CI tüketicileri bu alan adlarına bağımlıdır.
---

# JSON çıktı şemaları

`--output-format json` destekleyen her `forgelm` subcommand'ı stdout'a stabil bir JSON envelope üretir. Alan adları ve nesting [`docs/standards/release.md`](#/standards/release) gereği public CLI kontratının parçası: bir anahtarı yeniden adlandırmak MAJOR-version break sayılır.

Bu sayfa kanonik referanstır. `forgelm` çıktısını parse eden CI/CD pipeline'ları burada belgelenen yapılara karşı pin'lemelidir.

## Ortak konvansiyonlar

- **stdout vs stderr.** JSON envelope **stdout**'a gider. İnsana okunabilir loglar (info / warning / error) **stderr**'e gider. `forgelm ... --output-format json | jq .` ile pipe edip operatör mesajlarını `2>` ile ayrı okuyun.
- **Üst seviye sarmalayıcı.** Her envelope `"success": true | false` ile başlar. Tüketiciler önce bu tek anahtarda branch açabilir.
- **Hata envelope'u.** `success: false` olduğunda envelope `"error": "<mesaj>"` (string) taşır. Opsiyonel zenginleştirilmiş alanlar (`exit_code`, `error_type`, `details`) [`error-handling.md`](#/standards/error-handling) gereği var olabilir. Bu alanlardan kesinlik isteyen tüketiciler `$?` ile süreç exit kodunu da kontrol etmelidir.
- **Exit kodları.** Bkz. [Exit Kodları](#/reference/exit-codes). Envelope, exit code ile tutarlıdır: `success: true` ⟺ exit `0`; `success: false` ⟺ non-zero exit.

## `forgelm doctor`

Ortam kontrolü. Bkz. [Doctor komutu](#/getting-started/first-run).

**Başarı envelope'u** (`forgelm doctor [--offline] --output-format json`):

```json
{
  "success": true,
  "checks": [
    {
      "name": "python.version",
      "status": "pass",
      "detail": "Python 3.11.7 (CPython).",
      "extras": {"version": "3.11.7", "implementation": "CPython"}
    }
  ],
  "summary": {"pass": 8, "warn": 1, "fail": 0, "crashed": 0}
}
```

| Anahtar | Tip | Notlar |
|---|---|---|
| `success` | bool | Hiçbir probe `fail` değilse VE hiçbir probe crash etmediyse `true`; aksi halde `false`. |
| `checks` | list[object] | Çalıştırma sırasıyla probe başına bir entry. Probe adları stabildir (örn. `python.version`, `torch.cuda`, `gpu.inventory`, `extras.qlora`, `hf_hub.reachable`, `hf_hub.offline_cache`, `disk.workspace`, `operator.identity`). |
| `checks[].name` | str | Probe adı. Sürümler arası stabil; yeni probe'lar yeniden adlandırma yerine eklenir. |
| `checks[].status` | str | `pass`, `warn`, `fail`, `crashed`'tan biri. |
| `checks[].detail` | str | Sonuç için operatör-yüzlü tek satırlık açıklama. |
| `checks[].extras` | object | Probe-spesifik yapısal veri. Per-probe anahtarlar `_doctor.py` docstring'lerinde belgelidir; tüketiciler bilinmeyen anahtarları forward-compatible olarak ele almalıdır. |
| `summary` | object | `checks` arasında her status'ın sayısı. Toplam `len(checks)`'a eşittir. |

**Exit code mapping:** `0` = tüm probe'lar `pass` veya `warn`; `1` = en az bir `fail`; `2` = en az bir `crashed` (probe raise etti; sonraki probe'lar yine de çalıştı).

## `forgelm approvals --pending`

Bekleyen Madde 14 onay isteklerini en yeniden başa doğru listeler.

```json
{
  "success": true,
  "pending": [
    {
      "run_id": "fg-abc123def456",
      "staging_path": "/work/output/final_model.staging.fg-abc123def456",
      "staging_exists": true,
      "requested_at": "2026-05-04T12:34:56+00:00",
      "age_seconds": 3600.5,
      "metrics": {"safety_score": 0.91, "benchmark.hellaswag": 0.78},
      "config_hash": "sha256:...",
      "reason": "post-train safety eval below threshold"
    }
  ],
  "count": 1
}
```

| Anahtar | Tip | Notlar |
|---|---|---|
| `success` | bool | `true` (her zaman — boş liste başarıdır). |
| `pending` | list[object] | En yeniden başa; `count == len(pending)`. Boş liste = bekleyen onay yok. |
| `pending[].run_id` | str \| null | Audit event'inden run identifier. |
| `pending[].staging_path` | str \| null | Çözülmüş staging dizini (audit event `staging_path` taşımıyorsa ve canonical fallback yoksa `null`). Path-traversal korumalı — `--output-dir` dışındaki yollar resolve aşamasında reddedilir. |
| `pending[].staging_exists` | bool | `staging_path` mevcut bir dizine resolve oluyorsa `True`. |
| `pending[].requested_at` | str \| null | Audit event'inden ISO-8601 timestamp. |
| `pending[].age_seconds` | number \| null | `requested_at`'tan beri saniye; timestamp parse edilemezse `null`. |
| `pending[].metrics` | object | Audit event'inden serbest-form per-run metric'ler. |
| `pending[].config_hash` | str \| null | Bilindiğinde config fingerprint. |
| `pending[].reason` | str \| null | Audit event'inden operatör tarafından sağlanan sebep. |
| `count` | int | Bekleyen sayı; `len(pending)`'a eşit. |

## `forgelm approvals --show RUN_ID`

Bir koşu için tam onay-gate audit chain'i + staging içeriğini incele.

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "status": "pending",
  "chain": [
    {"event": "human_approval.required", "run_id": "fg-abc123def456", "timestamp": "2026-05-04T12:34:56+00:00", "...": "..."}
  ],
  "staging_contents": ["adapter_config.json", "adapter_model.safetensors", "tokenizer.json"]
}
```

| Anahtar | Tip | Notlar |
|---|---|---|
| `success` | bool | Koşu bulunduğunda `true`; `RUN_ID`'nin audit event'i yoksa `false` (`error` ile). |
| `run_id` | str | Echo'lanan input `RUN_ID`. |
| `status` | str | `pending`, `granted`, `rejected`, `unknown`'dan biri. Latest-wins semantik: önceki bir karardan sonra re-stage edilen koşu `pending` gösterir. |
| `chain` | list[object] | `run_id` için her onay-gate audit event'i, append sırasıyla. |
| `staging_contents` | list[str] | `<output_dir>/final_model.staging.<run_id>` (veya canonical fallback) altında sıralı dosya/dizin adları. Staging eksik veya okunamıyorsa boş. |

## `forgelm audit`

Eğitim öncesi veri denetimi. Tam rapor; ana alanlar gösterildi.

```json
{
  "success": true,
  "report_path": "audit/data_audit_report.json",
  "splits": {"train": {"sample_count": 100, "...": "..."}, "...": {}},
  "pii_summary": {"total_findings": 0, "by_kind": {}},
  "secrets_summary": {"total_findings": 0, "by_kind": {}},
  "cross_split_overlap": {"pairs": {}},
  "leakage": {"...": "..."},
  "quality_filter": null,
  "near_duplicates": {"...": "..."},
  "languages_top3": [{"code": "en", "count": 87}],
  "generated_at": "2026-05-04T12:34:56+00:00",
  "warnings": []
}
```

Tam şema [`docs/guides/data_audit.md`](#/data/audit)'dedir. CI gate'leri için `report_path` (on-disk JSON'un yeri) + `success`'e karşı pin'leyin.

## `forgelm verify-audit`

Audit log chain bütünlüğü kontrolü.

```json
{
  "success": true,
  "valid": true,
  "entries_count": 87,
  "hmac_verified": true,
  "errors": []
}
```

| Anahtar | Tip | Notlar |
|---|---|---|
| `success` | bool | `true` ⟺ `valid: true`. |
| `valid` | bool | Herhangi bir prev_hash mismatch / monotonicity break / seq gap varsa `false`. |
| `entries_count` | int | Düzgün-formed audit satır sayısı. |
| `hmac_verified` | bool \| null | `--hmac-secret` her `hmac` alanıyla eşleşince `true`; mismatch'te `false`; chain'de HMAC alanı yoksa `null`. |
| `errors` | list[str] | Tespit edilen sorun başına bir insan-okunur satır. |

## `forgelm approve` / `forgelm reject`

```json
{
  "success": true,
  "run_id": "fg-abc123def456",
  "approver": "alice@example.com@workstation-7",
  "final_model_path": "/work/output/final_model",
  "promote_strategy": "atomic_rename"
}
```

`approve` başarıda `0` ile çıkar; `reject` rejection kaydı sonrası `0` ile çıkar (staging dizini forensics için korunur). Bilinmeyen `run_id` / config hatasında `error` ile `success: false`.

## Yeni subcommand eklerken

`--output-format json` destekleyen yeni bir subcommand şunlarla landed olmalıdır:

1. Bu sayfada belgelenen envelope (EN + TR mirror).
2. Üst seviye anahtarların tam setini pin'leyen `tests/test_json_envelope_contract.py` (veya per-subcommand test dosyası) testi.
3. Per-collection anahtar "sonuçlar subcommand'in birincil ismine göre adlandırılmış bir anahtar altında yaşar" konvansiyonunu izler (yani `doctor` → `checks`, `approvals --pending` → `pending` vb.).

Merge sonrası bir anahtarı yeniden adlandırmak [`release.md`](#/standards/release) gereği MAJOR-version bump'tır.

## Ayrıca bakın

- [Exit Kodları](#/reference/exit-codes) — `success: bool`'ın aligned olduğu kontrat.
- [`error-handling.md`](#/standards/error-handling) — hata envelope kontratı.
- [`release.md`](#/standards/release) — JSON yeniden adlandırmaları ne zaman breaking sayılır.
