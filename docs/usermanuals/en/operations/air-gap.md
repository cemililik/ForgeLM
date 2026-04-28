---
title: Air-Gap Operation
description: Train and evaluate without internet — pre-cache everything, run in isolated networks.
---

# Air-Gap Operation

For regulated industries (defence, healthcare, certain financial sectors) and high-security customer environments, training must happen on networks with no internet access. ForgeLM is designed to operate fully air-gapped: every internet-touching step has an offline equivalent.

## What needs to be online (one-time)

Before going air-gapped, pre-cache:

| Resource | Where to cache |
|---|---|
| Base model | `~/.cache/huggingface/hub/` |
| Tokeniser | (same — bundled with model) |
| Llama Guard | `~/.cache/huggingface/hub/` |
| `lm-evaluation-harness` task definitions | `~/.cache/lm-evaluation-harness/` |
| Python packages (`forgelm` + extras) | local pip wheel cache |

Pre-cache from a connected machine:

```shell
$ forgelm cache-models \
    --model "Qwen/Qwen2.5-7B-Instruct" \
    --safety "meta-llama/Llama-Guard-3-8B" \
    --output ./airgap-bundle/

$ forgelm cache-tasks \
    --tasks hellaswag,arc_easy,truthfulqa,mmlu \
    --output ./airgap-bundle/
```

Transfer `airgap-bundle/` to the offline host (USB, scp, whatever your security policy allows).

## On the air-gapped host

Set environment variables to point at the local cache and disable any network calls:

```shell
$ export HF_HOME="$(pwd)/airgap-bundle/huggingface"
$ export TRANSFORMERS_OFFLINE=1
$ export HF_HUB_OFFLINE=1
$ export HF_DATASETS_OFFLINE=1

$ forgelm --config configs/run.yaml --offline
```

The `--offline` flag tells ForgeLM to refuse any network call. If your config references a model that isn't cached, training fails with a clear error message:

```text
ERROR: model "meta-llama/Llama-Guard-3-8B" not in local cache.
       Pre-cache from a connected machine: forgelm cache-models --safety meta-llama/Llama-Guard-3-8B
```

## What `--offline` enforces

| Subsystem | Behaviour with `--offline` |
|---|---|
| HuggingFace Hub downloads | Disabled. Fail-fast if a model/tokeniser isn't cached. |
| W&B / MLflow / Comet | Disabled (or local-only for MLflow with file URI). |
| OpenAI / Anthropic judges | Disabled. Use a local judge model. |
| Webhooks | Disabled (or restricted to internal hosts via `webhook.allow_private`). |
| pip install (during runtime) | Disabled. |
| Telemetry | None — ForgeLM never phones home regardless. |

## Local synthetic data

If you need synthetic data generation in air-gap, use a local teacher:

```yaml
synthetic:
  enabled: true
  teacher:
    provider: "local"
    model: "Qwen/Qwen2.5-72B-Instruct"  # must be cached
    load_in_4bit: true
```

OpenAI / Anthropic providers fail on `--offline`.

## Local LLM-as-judge

```yaml
evaluation:
  judge:
    enabled: true
    judge_model:
      provider: "local"
      model: "Qwen/Qwen2.5-72B-Instruct"
```

A 72B local judge is slower than `gpt-4o-mini` but the quality is comparable for typical use cases. See [LLM-as-Judge](#/evaluation/judge).

## Evaluation in air-gap

`lm-evaluation-harness` typically downloads task definitions and datasets at runtime. Pre-cache them:

```shell
$ forgelm cache-tasks --tasks hellaswag,arc_easy,truthfulqa,mmlu
```

Configure ForgeLM to use the cache:

```yaml
evaluation:
  benchmark:
    tasks_dir: "${HF_HOME}/lm-evaluation-harness/"
```

## Verifying air-gap mode

```shell
$ forgelm doctor --offline
ForgeLM 0.5.2 (offline mode verified)
✓ HF_HUB_OFFLINE set
✓ TRANSFORMERS_OFFLINE set
✓ Local cache: airgap-bundle/huggingface (3.4 GB cached models)
✓ Llama Guard 3 8B available locally
✓ lm-evaluation-harness: 4 tasks cached
```

If `forgelm doctor --offline` reports anything unavailable, fix that *before* the air-gapped operator wastes their time.

## Bundle size estimate

For a typical fine-tuning project:

| Resource | Approx size |
|---|---|
| Base model (7B) in safetensors | 14 GB |
| Llama Guard 3 8B | 16 GB |
| Tokeniser + config | <100 MB |
| Eval task definitions + cached datasets | 500 MB - 2 GB |
| Python wheels (forgelm + extras) | 1-2 GB |
| **Total** | **~32-34 GB** |

Plan storage accordingly.

## Common pitfalls

:::warn
**Forgetting to set the environment variables.** Without `HF_HUB_OFFLINE=1`, HuggingFace libraries silently try to phone home and fall back to local cache. The fall-back works fine but you've now made an outbound connection — a compliance violation in some environments.
:::

:::warn
**Using `--offline` without pre-caching.** Training will fail at the first model load. Run `forgelm doctor --offline` before kicking off training to catch missing resources upfront.
:::

:::tip
**Build a CI image with everything pre-cached.** For air-gapped CI, package the pre-cached bundle into a Docker image. Every CI run starts from the cached state. See [Docker](#/operations/docker).
:::

## See also

- [Docker](#/operations/docker) — building images with pre-cached models.
- [Installation](#/getting-started/installation) — base install.
- [LLM-as-Judge](#/evaluation/judge) — local judge models.
