---
title: CLI Reference
description: Every forgelm subcommand and flag, with auth setup and common patterns.
---

# CLI Reference

ForgeLM ships a single `forgelm` binary with subcommands. This page is the canonical reference; for tutorial-level guidance, see [Your First Run](#/getting-started/first-run).

## Top-level subcommands

| Command | What it does |
|---|---|
| `forgelm` (no subcommand) | Train (with `--config`). |
| `forgelm doctor` | Environment check — Python, CUDA, GPU, deps. |
| `forgelm quickstart` | List or instantiate bundled templates. |
| `forgelm ingest` | PDF/DOCX/EPUB → JSONL conversion. |
| `forgelm audit` | Pre-train data audit. |
| `forgelm benchmark` | Run lm-eval-harness against a model. |
| `forgelm safety-eval` | Llama Guard scoring. |
| `forgelm chat` | Interactive REPL. |
| `forgelm batch-chat` | Non-interactive prompt → response. |
| `forgelm export` | GGUF export with quantisation. |
| `forgelm deploy` | Generate deployment config (Ollama, vLLM, TGI, etc). |
| `forgelm verify-annex-iv` | Validate an Annex IV artifact. |
| `forgelm verify-log` | Validate audit log chain. |
| `forgelm verify-gguf` | Validate GGUF integrity. |
| `forgelm cache-models` | Pre-cache HuggingFace models for air-gap. |
| `forgelm cache-tasks` | Pre-cache lm-evaluation-harness tasks. |
| `forgelm trend` | Show metric trends across recent runs. |
| `forgelm compare-runs` | Side-by-side comparison of run metrics. |
| `forgelm approve` | Sign a human approval request. |
| `forgelm approvals` | List pending approvals. |

Run `forgelm <subcommand> --help` for any of these.

## Top-level flags (apply across many subcommands)

| Flag | Description |
|---|---|
| `--config PATH` | YAML config file path. Required for training. |
| `--dry-run` | Validate config and references; no training. |
| `--fit-check` | Estimate VRAM and report verdict; no training. |
| `--estimate-cost` | Pre-flight cost estimate; no training. |
| `--offline` | Disable all network calls; require everything cached. |
| `--output-format {plain,json}` | Logging format. JSON for CI. |
| `--verbose, -v` | Increase logging detail. |
| `--quiet, -q` | Reduce logging detail. |
| `--version` | Print version. |
| `--help, -h` | Show help. |

## Training: `forgelm`

Most-used patterns:

```shell
$ forgelm --config configs/run.yaml --dry-run        # validate
$ forgelm --config configs/run.yaml --fit-check      # VRAM check
$ forgelm --config configs/run.yaml                  # train
$ forgelm --config configs/run.yaml --resume         # resume from last checkpoint
$ forgelm --config configs/run.yaml --merge          # run as a merge job
$ forgelm --config configs/run.yaml --generate-data  # synthetic data only
```

Resume from a specific checkpoint: `--resume-from PATH`.

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

See [Dataset Audit](#/data/audit) for full semantics.

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

See [Document Ingestion](#/data/ingestion).

## Chat: `forgelm chat`

```shell
$ forgelm chat CHECKPOINT \
    [--base BASE_MODEL] \
    [--temperature 0.7] [--top-p 0.9] [--max-tokens 1024] \
    [--system "system prompt"] \
    [--safety on|off] \
    [--load PATH]                              # load saved session
```

Slash commands within the REPL: `/reset`, `/save`, `/load`, `/system`, `/temperature`, `/top_p`, `/max_tokens`, `/safety`, `/help`, `/quit`. See [Interactive Chat](#/deployment/chat).

## Export: `forgelm export`

```shell
$ forgelm export CHECKPOINT_DIR \
    --output PATH.gguf \
    --quant q4_k_m|q5_k_m|q6_k|q8_0|q3_k_m|q2_k|fp16 \
    [--merge]                                  # merge LoRA into base before export
```

Comma-separate `--quant` for multiple levels in one command. See [GGUF Export](#/deployment/gguf-export).

## Deploy: `forgelm deploy`

```shell
$ forgelm deploy CHECKPOINT_DIR \
    --target ollama|vllm|tgi|hf-endpoints|kserve|triton \
    --output PATH_OR_DIR
```

See [Deploy Targets](#/deployment/deploy-targets).

## Authentication

ForgeLM picks up credentials from environment variables. Never put them in YAML.

| Provider | Env var | Used for |
|---|---|---|
| HuggingFace | `HF_TOKEN` | Gated models (Llama, Llama Guard) |
| OpenAI | `OPENAI_API_KEY` | LLM-as-judge, synthetic data |
| Anthropic | `ANTHROPIC_API_KEY` | LLM-as-judge, synthetic data |
| W&B | `WANDB_API_KEY` | Experiment tracking |
| Cohere | `COHERE_API_KEY` | (synthetic data) |

YAML interpolation:

```yaml
auth:
  hf_token: "${HF_TOKEN}"
synthetic:
  teacher:
    api_key: "${OPENAI_API_KEY}"
```

If the env var isn't set, ForgeLM fails at config load with a clear error — better than crashing 6 hours into training because of a missing token.

## Exit codes

| Exit | Meaning |
|---|---|
| 0 | Success |
| 1 | Config / arg error |
| 2 | Audit warnings (with `--strict`) |
| 3 | Auto-revert / regression |
| 4 | Awaiting human approval |
| 130 | User interrupted (Ctrl+C) |

See [Exit Codes](#/reference/exit-codes) for the full contract.

## Environment variables

| Variable | What it sets |
|---|---|
| `HF_TOKEN` | HuggingFace auth |
| `HF_HOME` | HuggingFace cache directory (default `~/.cache/huggingface`) |
| `HF_HUB_OFFLINE=1` | Disable HF Hub network calls |
| `TRANSFORMERS_OFFLINE=1` | Disable transformers library network calls |
| `HF_DATASETS_OFFLINE=1` | Disable datasets library network calls |
| `FORGELM_CACHE_DIR` | ForgeLM-specific cache location |
| `FORGELM_LOG_LEVEL` | Override logging level (DEBUG, INFO, WARN, ERROR) |
| `FORGELM_RESUME_TOKEN` | Token for the API-based human approval flow |

## Common patterns

### "Just train and don't bother me"

```shell
$ forgelm --config configs/run.yaml --output-format json | tee run.log
```

### "Run audit, then train if clean"

```shell
$ forgelm audit data/ --strict && forgelm --config configs/run.yaml
```

### "Train, export GGUF, deploy to Ollama"

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
# Training, export, and deploy config generation all happen.
```

## See also

- [Configuration Reference](#/reference/configuration) — YAML companion.
- [Exit Codes](#/reference/exit-codes) — gate contract for CI.
- [YAML Templates](#/reference/yaml-templates) — full working configs.
