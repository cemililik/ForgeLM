# Design: Interactive Configuration Wizard (`--wizard`)

## Overview
To improve accessibility for users coming from no-code tools (like the DGX-Spark Finetuner), ForgeLM will introduce an interactive wizard mode.

## Proposed Flow
The wizard will be triggered via `python3 -m forgelm.cli --wizard`.

1.  **Welcome & Hardware Detection**: Detect available VRAM and suggest a backend (Unsloth vs. Transformers).
2.  **Model Selection**: Prompt for a HuggingFace repository name. Perform a pre-flight check for `safetensors`.
3.  **Strategy Selection**: Choose between LoRA, QLoRA, or DoRA with simplified explanations of each.
4.  **Dataset Path**: Prompt for local file path or HF Hub dataset. Validate format on-the-fly.
5.  **Output Config**: Ask for a filename to save the generated YAML.
6.  **Quick Run**: Ask if the user wants to start training immediately using the generated config.

## Implementation Details
- Use `rich` or `questionary` for a beautiful interactive experience.
- The wizard's primary output is a standard `config.yaml`, ensuring compatibility with the existing config-driven architecture.
