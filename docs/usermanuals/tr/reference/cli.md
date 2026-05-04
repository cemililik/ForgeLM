---
title: CLI Referansı
description: Her forgelm subcommand'ı ve bayrağı, auth kurulumu ve sık pattern'ler.
---

# CLI Referansı

ForgeLM, subcommand'larla tek bir `forgelm` binary'si yayınlar. Bu sayfa kanonik referanstır; eğitsel rehberlik için bkz. [İlk Koşunuz](#/getting-started/first-run).

## Üst seviye subcommand'lar

| Komut | Yaptığı |
|---|---|
| `forgelm` (subcommand'sız) | Eğit (`--config` ile). |
| `forgelm doctor` | Ortam kontrolü — Python, CUDA, GPU, bağımlılıklar, HF cache. |
| `forgelm quickstart` | Yerleşik şablonları listele veya örnekle. |
| `forgelm ingest` | PDF/DOCX/EPUB → JSONL dönüşümü. |
| `forgelm audit` | Eğitim öncesi veri denetimi (PII / secrets / dedup / leakage / quality). |
| `forgelm chat` | Etkileşimli REPL. |
| `forgelm export` | GGUF export ve quantization. |
| `forgelm deploy` | Deployment config üret (Ollama, vLLM, TGI, HF Endpoints). |
| `forgelm verify-audit` | Audit log zincirini doğrula (timestamp, prev_hash, HMAC). |
| `forgelm approve` | İnsan onay isteğini imzala ve `final_model.staging/`'i promote et. |
| `forgelm reject` | İnsan onay isteğini reddet ve staging'i at. |
| `forgelm approvals` | Bekleyen onayları listele (`--pending`) veya tek birini incele (`--show RUN_ID`). |

Bunlardan herhangi biri için `forgelm <subcommand> --help`.

## Üst seviye bayraklar (eğitim modu — `--config` ile kullanılır)

| Bayrak | Açıklama |
|---|---|
| `--config PATH` | YAML config dosya yolu. Eğitim için gerekli. |
| `--wizard` | `config.yaml` üretmek için etkileşimli yapılandırma sihirbazını başlat. |
| `--dry-run` | Config'i ve model/dataset erişimini doğrula; eğitim yok. |
| `--fit-check` | Eğitim VRAM tahmini; model yüklenmez. `--config` gerektirir. |
| `--resume [PATH]` | Eğitime kaldığı yerden devam. Çıplak `--resume` son checkpoint'i otomatik bulur; `--resume PATH` belirli bir yerden. |
| `--offline` | Air-gap modu: tüm HF Hub ağ çağrılarını kapat. Modeller ve dataset'ler yerel olarak mevcut olmalı. |
| `--benchmark-only MODEL_PATH` | Mevcut bir model üzerinde benchmark koştur, eğitim yok. `evaluation.benchmark` config'i gerektirir. |
| `--merge` | Config'in `merge:` bloğundan model birleştirmeyi koştur. Eğitim yok. |
| `--generate-data` | Teacher modelle sentetik eğitim verisi üret. Eğitim yok. |
| `--compliance-export OUTPUT_DIR` | EU AI Act uyum artifact'larını (audit trail, data provenance, Annex IV) OUTPUT_DIR'a export et. Manifest'in tamamlanması için eğitimden sonra koşturun. |
| `--data-audit PATH` | **Deprecated alias**, `forgelm audit PATH` için. v0.7.0'da kaldırılacak. Yeni script'ler subcommand'ı kullanmalı. |
| `--output DIR` | `--data-audit` / `--compliance-export` için çıktı dizini (varsayılan: `./audit/` ya da `./compliance/`). |
| `--output-format {text,json}` | Sonuçlar için çıktı formatı (varsayılan: `text`). CI için JSON. |
| `--quiet, -q` | INFO loglarını bastır. Sadece warning ve error göster. |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Log detay seviyesi (varsayılan: INFO). |
| `--version` | Sürümü yazdır. |
| `--help, -h` | Yardım göster. |

## Eğitim: `forgelm`

En sık kullanılan pattern'ler:

```shell
$ forgelm --config configs/run.yaml --dry-run        # doğrula
$ forgelm --config configs/run.yaml --fit-check      # VRAM kontrolü
$ forgelm --config configs/run.yaml                  # eğit
$ forgelm --config configs/run.yaml --resume         # otomatik son checkpoint'ten devam
$ forgelm --config configs/run.yaml --resume /path   # belirli bir checkpoint'ten devam
$ forgelm --config configs/run.yaml --merge          # birleştirme işi olarak koştur
$ forgelm --config configs/run.yaml --generate-data  # sadece sentetik veri
```

## Doctor: `forgelm doctor`

```shell
$ forgelm doctor                                     # tam ortam kontrolü
$ forgelm doctor --offline                           # air-gap varyantı: cache + offline-env probe'ları
$ forgelm doctor --output-format json | jq .         # CI dostu envelope
```

Python sürümünü, torch / CUDA / GPU'yu, opsiyonel extra'ları, HF Hub erişilebilirliğini (veya `--offline` ile HF cache'i), disk alanını, operator kimliğini ve audit-secret yapılandırmasını probe eder. Exit kodları: `0` = hepsi geçti (warning OK), `1` = en az bir fail, `2` = bir probe'un kendisi crash etti.

## Audit: `forgelm audit`

```shell
$ forgelm audit DATAFILE_OR_DIR \
    [--output ./audit/] \
    [--strict] \
    [--workers N] \
    [--dedup-method {simhash,minhash}] \
    [--near-dup-threshold N] \
    [--minhash-jaccard FLOAT] [--minhash-num-perm N] \
    [--skip-pii] [--skip-secrets] [--skip-quality] [--skip-leakage] \
    [--remove-duplicates] [--remove-cross-split-overlap=val|test] \
    [--output-clean PATH] \
    [--show-leakage] \
    [--sample-rate FLOAT] \
    [--pii-ml] [--pii-ml-language LANG] \
    [--croissant] \
    [--verbose]
```

`--workers N` split düzeyinde paralellik sağlar; on-disk JSON worker sayısından bağımsız olarak byte-identical (sadece `generated_at` zamanı değişir). Tam semantik için bkz. [Veri Denetimi](#/data/audit).

## Ingest: `forgelm ingest`

```shell
$ forgelm ingest INPUT_PATH \
    --output PATH.jsonl \
    [--recursive] \
    [--strategy {sliding,paragraph,markdown}] \
    [--chunk-size N] [--overlap N] \
    [--chunk-tokens N] [--overlap-tokens N] [--tokenizer MODEL_NAME] \
    [--pii-mask] [--secrets-mask] [--all-mask] \
    [--pii-ml-language LANG]
```

Bkz. [Doküman Ingestion](#/data/ingestion).

## Chat: `forgelm chat`

```shell
$ forgelm chat MODEL_PATH \
    [--adapter PATH] \
    [--system "system prompt"] \
    [--temperature 0.7] [--max-new-tokens 512] [--no-stream] \
    [--load-in-4bit | --load-in-8bit] \
    [--trust-remote-code] \
    [--backend {transformers,unsloth}]
```

REPL içindeki slash komutları: `/reset`, `/save [file]`, `/temperature N`, `/system [prompt]`, `/help` (alias `/?`), `/exit` (alias `/quit`). Bkz. [Etkileşimli Chat](#/deployment/chat).

## Export: `forgelm export`

```shell
$ forgelm export CHECKPOINT_DIR \
    --output PATH.gguf \
    --quant {q2_k,q3_k_m,q4_k_m,q5_k_m,q8_0,f16} \
    [--adapter PATH] \
    [--no-integrity-update]
```

Tek komutta çoklu seviye için `--quant`'ı virgülle ayırın. Bkz. [GGUF Export](#/deployment/gguf-export).

## Deploy: `forgelm deploy`

```shell
$ forgelm deploy MODEL_PATH \
    --target {ollama,vllm,tgi,hf-endpoints} \
    [--output PATH] \
    [--system "PROMPT"]                              # sadece Ollama
    [--max-length 4096] \
    [--gpu-memory-utilization 0.90]                  # vLLM
    [--port 8080]                                    # TGI
    [--trust-remote-code]                            # vLLM
    [--vendor aws]                                   # HF Endpoints
```

Bkz. [Deploy Hedefleri](#/deployment/deploy-targets).

## Onaylar: `forgelm approvals` / `forgelm approve` / `forgelm reject`

```shell
$ forgelm approvals --pending                        # bekleyen onay gate'lerini listele
$ forgelm approvals --show RUN_ID                    # belirli bir koşunun chain + staging'ini incele
$ forgelm approve  RUN_ID --comment "N. inceledi."   # final_model.staging/ → final_model/ promote
$ forgelm reject   RUN_ID --comment "Sebep ..."      # staging'i at
```

Bkz. [İnsan Gözetim Gate'i](#/compliance/human-oversight). Exit kodları: `0` = bekleyen liste / onay kaydedildi, `1` = bilinmeyen run_id / config hatası, `4` (sadece eğitim modu) = onay bekliyor.

## Audit log doğrula: `forgelm verify-audit`

```shell
$ forgelm verify-audit PATH/TO/audit_log.jsonl
$ forgelm verify-audit PATH/TO/audit_log.jsonl --hmac-secret "$FORGELM_AUDIT_SECRET"
$ forgelm verify-audit PATH/TO/audit_log.jsonl --require-hmac
```

Monoton timestamp'leri, `prev_hash` zincir bütünlüğünü, `seq` boşluk tespitini ve (yapılandırıldığında) HMAC imzalarını doğrular. Geçerli zincirde exit `0`; tahrif tespitinde structured error envelope ile non-zero.

## Kimlik Doğrulama

ForgeLM credential'ları environment variable'lardan alır. Asla YAML'a koymayın.

| Sağlayıcı | Env var | Kullanım yeri |
|---|---|---|
| HuggingFace | `HF_TOKEN` (alias: `HUGGINGFACE_TOKEN`) | Gated modeller (Llama, Llama Guard) |
| OpenAI | `OPENAI_API_KEY` | LLM-as-judge, sentetik veri |
| Anthropic | `ANTHROPIC_API_KEY` | LLM-as-judge, sentetik veri |
| W&B | `WANDB_API_KEY` | Experiment tracking |
| Cohere | `COHERE_API_KEY` | (sentetik veri) |

YAML interpolation:

```yaml
auth:
  hf_token: "${HF_TOKEN}"
synthetic:
  teacher:
    api_key: "${OPENAI_API_KEY}"
```

Env var set değilse ForgeLM config yüklemede net bir hata ile çıkar — eğitime 6 saat girmiş halde eksik token ile crash etmekten iyidir.

## Exit kodları

| Exit | Anlamı |
|---|---|
| 0 | Başarı |
| 1 | Config / argüman hatası |
| 2 | Audit warning (`--strict` ile) / probe crash (`forgelm doctor`) |
| 3 | Auto-revert / regression |
| 4 | İnsan onayı bekleniyor (eğitim pipeline) |
| 130 | Kullanıcı kesintiye uğrattı (Ctrl+C) |

Tam kontrat için bkz. [Exit Kodları](#/reference/exit-codes).

## Environment variable'lar

| Değişken | Ne ayarlar |
|---|---|
| `HF_TOKEN` / `HUGGINGFACE_TOKEN` | HuggingFace authentication |
| `HF_HOME` | HuggingFace cache kökü (varsayılan `~/.cache/huggingface`) |
| `HF_HUB_CACHE` | HF Hub cache dizinini özel olarak override et (öncelik: `HF_HUB_CACHE` > `HF_HOME/hub` > varsayılan) |
| `HF_HUB_OFFLINE=1` | HF Hub ağ çağrılarını kapat |
| `HF_ENDPOINT` | HF Hub endpoint override (self-hosted mirror için); `forgelm doctor` tarafından honor edilir |
| `TRANSFORMERS_OFFLINE=1` | transformers kütüphanesi ağ çağrılarını kapat |
| `HF_DATASETS_OFFLINE=1` | datasets kütüphanesi ağ çağrılarını kapat |
| `FORGELM_OPERATOR` | Audit event'lerinde kaydedilen operator kimliği (`getpass.getuser()@hostname`'i override eder) |
| `FORGELM_ALLOW_ANONYMOUS_OPERATOR` | `1` olduğunda audit log'un anonim operatör kaydetmesine izin verir (aksi halde çözülemeyen kimlik hatası) |
| `FORGELM_AUDIT_SECRET` | Audit log chain için HMAC imza anahtarı (tahrif tespitini açar) |
| `FORGELM_GGUF_CONVERTER` | Özel `convert-hf-to-gguf.py` script'inin yolu |

## Sık pattern'ler

### "Sadece eğit ve beni rahatsız etme"

```shell
$ forgelm --config configs/run.yaml --output-format json | tee run.log
```

### "Önce audit, temizse eğit"

```shell
$ forgelm audit data/ --strict && forgelm --config configs/run.yaml
```

### "İnsan onay gate'iyle eğit; sonra promote et"

```shell
$ forgelm --config configs/run.yaml                  # onay gate ateşlerse exit 4
$ forgelm approvals --pending                        # bekleyen koşuyu keşfet
$ forgelm approve RUN_ID --comment "İnceledim."      # staging'i promote et
```

### "Eğit, GGUF export et, Ollama'ya deploy et"

```yaml
# configs/run.yaml
output:
  gguf:
    enabled: true
deployment:
  target: ollama
```

```shell
$ forgelm --config configs/run.yaml
# Eğitim, export ve deploy config üretimi hep birlikte gerçekleşir.
```

## Ayrıca bakın

- [Configuration Referansı](#/reference/configuration) — YAML eşleşmesi.
- [Exit Kodları](#/reference/exit-codes) — CI için gate kontratı.
- [YAML Şablonları](#/reference/yaml-templates) — tam çalışan config'ler.
