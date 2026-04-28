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
| `forgelm doctor` | Ortam kontrolü — Python, CUDA, GPU, bağımlılıklar. |
| `forgelm quickstart` | Yerleşik şablonları listele veya örnekle. |
| `forgelm ingest` | PDF/DOCX/EPUB → JSONL dönüşümü. |
| `forgelm audit` | Eğitim öncesi veri denetimi. |
| `forgelm benchmark` | Model üzerinde lm-eval-harness koştur. |
| `forgelm safety-eval` | Llama Guard skorlama. |
| `forgelm chat` | Etkileşimli REPL. |
| `forgelm batch-chat` | Etkileşimsiz prompt → yanıt. |
| `forgelm export` | GGUF export ve quantization. |
| `forgelm deploy` | Deployment config üret (Ollama, vLLM, TGI vb.). |
| `forgelm verify-annex-iv` | Annex IV artifact'ını doğrula. |
| `forgelm verify-log` | Audit log zincirini doğrula. |
| `forgelm verify-gguf` | GGUF bütünlüğünü doğrula. |
| `forgelm cache-models` | Air-gap için HuggingFace modellerini önceden cache'le. |
| `forgelm cache-tasks` | lm-evaluation-harness görevlerini önceden cache'le. |
| `forgelm trend` | Son koşular arasında metric trendlerini göster. |
| `forgelm compare-runs` | Koşu metriklerini yan yana karşılaştır. |
| `forgelm approve` | İnsan onay isteğini imzala. |
| `forgelm approvals` | Bekleyen onayları listele. |

Bunlardan herhangi biri için `forgelm <subcommand> --help`.

## Üst seviye bayraklar (birçok subcommand'da)

| Bayrak | Açıklama |
|---|---|
| `--config PATH` | YAML config dosya yolu. Eğitim için gerekli. |
| `--dry-run` | Config'i ve referansları doğrula; eğitim yok. |
| `--fit-check` | VRAM tahmini ve verdict; eğitim yok. |
| `--estimate-cost` | Uçuş öncesi maliyet tahmini; eğitim yok. |
| `--offline` | Tüm ağ çağrılarını kapat; her şey cache'lenmiş olmalı. |
| `--output-format {plain,json}` | Log formatı. CI için JSON. |
| `--verbose, -v` | Log detayını artır. |
| `--quiet, -q` | Log detayını azalt. |
| `--version` | Sürümü yazdır. |
| `--help, -h` | Yardım göster. |

## Eğitim: `forgelm`

En sık kullanılan pattern'ler:

```shell
$ forgelm --config configs/run.yaml --dry-run        # doğrula
$ forgelm --config configs/run.yaml --fit-check      # VRAM kontrolü
$ forgelm --config configs/run.yaml                  # eğit
$ forgelm --config configs/run.yaml --resume         # son checkpoint'ten devam
$ forgelm --config configs/run.yaml --merge          # merge işi olarak çalıştır
$ forgelm --config configs/run.yaml --generate-data  # sadece sentetik veri
```

Belirli bir checkpoint'ten devam: `--resume-from PATH`.

## Audit: `forgelm audit`

```shell
$ forgelm audit DATAFILE_OR_DIR \
    [--output ./audit/] \
    [--strict] \
    [--dedup-algo simhash|minhash] \
    [--dedup-threshold N] \
    [--skip-pii] [--skip-secrets] [--skip-quality] [--skip-leakage] \
    [--remove-duplicates] [--remove-cross-split-overlap=val|test] \
    [--output-clean PATH] \
    [--show-leakage] \
    [--sample-rate FLOAT]
```

Tam semantic için bkz. [Veri Seti Denetimi](#/data/audit).

## Ingest: `forgelm ingest`

```shell
$ forgelm ingest INPUT_DIR \
    --output PATH.jsonl \
    [--recursive] \
    [--strategy tokens|markdown|paragraph|sentence] \
    [--max-tokens N] [--overlap N] \
    [--pii-mask] [--secrets-mask] \
    [--pii-locale tr|de|fr|us] \
    [--language LANG] \
    [--include "*.pdf,*.md"] [--exclude "drafts/*"] \
    [--format raw|instructions|qa]
```

Bkz. [Doküman Ingest'i](#/data/ingestion).

## Chat: `forgelm chat`

```shell
$ forgelm chat CHECKPOINT \
    [--base BASE_MODEL] \
    [--temperature 0.7] [--top-p 0.9] [--max-tokens 1024] \
    [--system "system prompt"] \
    [--safety on|off] \
    [--load PATH]                              # kayıtlı oturum yükle
```

REPL içinde slash komutları: `/reset`, `/save`, `/load`, `/system`, `/temperature`, `/top_p`, `/max_tokens`, `/safety`, `/help`, `/quit`. Bkz. [Etkileşimli Chat](#/deployment/chat).

## Export: `forgelm export`

```shell
$ forgelm export CHECKPOINT_DIR \
    --output PATH.gguf \
    --quant q4_k_m|q5_k_m|q6_k|q8_0|q3_k_m|q2_k|fp16 \
    [--merge]                                  # export öncesi LoRA'yı base'e merge et
```

Tek komutta birden çok seviye için `--quant`'ı virgülle ayırın. Bkz. [GGUF Export](#/deployment/gguf-export).

## Deploy: `forgelm deploy`

```shell
$ forgelm deploy CHECKPOINT_DIR \
    --target ollama|vllm|tgi|hf-endpoints|kserve|triton \
    --output PATH_OR_DIR
```

Bkz. [Deploy Hedefleri](#/deployment/deploy-targets).

## Kimlik doğrulama

ForgeLM kimlik bilgilerini environment variable'lardan okur. Asla YAML'a koymayın.

| Sağlayıcı | Env var | Kullanılan |
|---|---|---|
| HuggingFace | `HF_TOKEN` | Geçit kontrollü modeller (Llama, Llama Guard) |
| OpenAI | `OPENAI_API_KEY` | LLM-as-judge, sentetik veri |
| Anthropic | `ANTHROPIC_API_KEY` | LLM-as-judge, sentetik veri |
| W&B | `WANDB_API_KEY` | Deney takibi |
| Cohere | `COHERE_API_KEY` | (sentetik veri) |

YAML interpolasyonu:

```yaml
auth:
  hf_token: "${HF_TOKEN}"
synthetic:
  teacher:
    api_key: "${OPENAI_API_KEY}"
```

Env var ayarlı değilse ForgeLM net bir hatayla config yüklemede başarısız olur — eksik token nedeniyle eğitim 6 saatte çökmektense bu daha iyidir.

## Exit kodları

| Exit | Anlamı |
|---|---|
| 0 | Başarı |
| 1 | Config / arg hatası |
| 2 | Audit uyarıları (`--strict` ile) |
| 3 | Otomatik geri alma / regresyon |
| 4 | İnsan onayı bekliyor |
| 130 | Kullanıcı kesti (Ctrl+C) |

Tam kontrat için bkz. [Exit Kodları](#/reference/exit-codes).

## Environment variable'lar

| Değişken | Ayarladığı |
|---|---|
| `HF_TOKEN` | HuggingFace auth |
| `HF_HOME` | HuggingFace cache dizini (varsayılan `~/.cache/huggingface`) |
| `HF_HUB_OFFLINE=1` | HF Hub ağ çağrılarını kapat |
| `TRANSFORMERS_OFFLINE=1` | transformers kütüphanesi ağ çağrılarını kapat |
| `HF_DATASETS_OFFLINE=1` | datasets kütüphanesi ağ çağrılarını kapat |
| `FORGELM_CACHE_DIR` | ForgeLM-özgü cache konumu |
| `FORGELM_LOG_LEVEL` | Log seviyesini override et (DEBUG, INFO, WARN, ERROR) |
| `FORGELM_RESUME_TOKEN` | API tabanlı insan onay akışı için token |

## Sık pattern'ler

### "Sadece eğit, beni rahatsız etme"

```shell
$ forgelm --config configs/run.yaml --output-format json | tee run.log
```

### "Audit yap, temizse eğit"

```shell
$ forgelm audit data/ --strict && forgelm --config configs/run.yaml
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
# Eğitim, export ve deployment config üretimi hepsi olur.
```

## Bkz.

- [Konfigürasyon Referansı](#/reference/configuration) — YAML eşi.
- [Exit Kodları](#/reference/exit-codes) — CI için kapı kontratı.
- [YAML Şablonları](#/reference/yaml-templates) — tam çalışan config'ler.
