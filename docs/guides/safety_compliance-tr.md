# Güvenlik & Uyumluluk Kılavuzu (TR)

> **Not:** Bu dosya şu an yalnızca Faz 6'da eklenen `forgelm verify-audit` özelliğinin Türkçe karşılığını içerir. Tam bilingual eşleme (EN ↔ TR) `docs/guides/safety_compliance.md` dosyasının ileride yapılacak çevirisi ile tamamlanacaktır. Daha geniş bağlam için lütfen İngilizce sürüme bakın.

## Audit Log Bütünlüğü Doğrulama

ForgeLM'in audit log'u (`audit_log.jsonl`) SHA-256 hash zinciri kullanır; geriye dönük yapılan herhangi bir değişiklik zinciri kırar. Operatör `FORGELM_AUDIT_SECRET` ortam değişkenini ayarlamışsa her satıra ek olarak HMAC etiketi de yazılır — bu sayede log'a yazma erişimi olan ama operatör anahtarını bilmeyen bir saldırgan satır içeriklerini sahteleyemez.

### `forgelm verify-audit` alt komutu

`forgelm verify-audit` alt komutu, bir audit log dosyasının SHA-256 zincirini ve (verildiyse) HMAC etiketlerini doğrular:

```bash
forgelm verify-audit run123/audit_log.jsonl
# OK: 47 entries verified

FORGELM_AUDIT_SECRET=$OPERATOR_KEY forgelm verify-audit run123/audit_log.jsonl
# OK: 47 entries verified (HMAC validated)

forgelm verify-audit tampered.jsonl
# FAIL at line 23: chain broken at line 23: prev_hash='...' expected='...'
```

Çıkış kodları:

| Kod | Anlam |
|-----|-------|
| `0` | Zincir (ve denetlendiyse HMAC) eksiksiz |
| `1` | Zincir kırık veya HMAC eşleşmiyor (kurcalama / bozulma) |
| `2` | Dosya bulunamadı, okunamadı veya `--require-hmac` belirtildi ama secret env var ayarlı değil |

### Kütüphane fonksiyonu

CI/CD pipeline'larından programatik kullanım için:

```python
from forgelm.compliance import verify_audit_log, VerifyResult

result: VerifyResult = verify_audit_log(
    "run123/audit_log.jsonl",
    hmac_secret=os.environ.get("FORGELM_AUDIT_SECRET"),
)
if not result.valid:
    raise SystemExit(
        f"Audit log invalid at line {result.first_invalid_index}: {result.reason}"
    )
```

`VerifyResult` dataclass alanları: `valid` (bool), `entries_count` (int), `first_invalid_index` (Optional[int], 1-tabanlı), `reason` (Optional[str]).

### Strict mod (`--require-hmac`)

Düzenlemeli ortamlarda her satırın HMAC ile imzalı olması zorunlu olabilir. `--require-hmac` bayrağı:

- Secret env var ayarlı değilse derhal çıkış kodu 2 ile çıkar (operatör hatası).
- Herhangi bir satırda `_hmac` alanı yoksa çıkış kodu 1 ile başarısız olur.

```bash
FORGELM_AUDIT_SECRET=$OPERATOR_KEY forgelm verify-audit \
    run123/audit_log.jsonl --require-hmac
```

### Genesis manifest çapraz kontrolü

ForgeLM, audit log'un ilk yazılışında `audit_log.jsonl.manifest.json` adlı bir sidecar dosyası üretir. Bu dosya birinci satırın SHA-256 hash'ini sabitler; saldırgan log'u kesip yeni bir genesis satırı yazsa bile manifest eşleşmemesi tespit edilir. `verify-audit` bu sidecar'ı otomatik olarak okur — manifest yoksa zincir-bütünlüğü kontrolü gene yapılır, ancak truncate-and-resume tespit kapsamı daralır (DEBUG seviyesinde uyarı verilir).
