# Phase 10: Post-Training Completion

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md).

**Goal:** Close the "trained, now what?" gap. After a fine-tune finishes, users should be able to sanity-check, export, and hand the model to a serving runtime (Ollama, vLLM, TGI) without leaving ForgeLM.
**Estimated Effort:** Medium (2-3 months)
**Priority:** High — single biggest post-9 UX gap; foundation for Phase 12 (quickstart)

> **Context:** External analyses of two adjacent projects (QKV-Core, Trion) plus internal retrospectives converged on the same finding: ForgeLM stops at `output_dir/` with an HF-format adapter/merged model, but the user's actual journey continues to sanity chat → quantization → serving. Competitors (Axolotl, Unsloth) leave this to external tooling. Owning this handoff — without rewriting the inference ecosystem — is a high-value, low-risk addition.

**Status: ✅ Complete** — shipped in `v0.4.0` (April 2026)

### Tasks:

1. [x] **`forgelm/inference.py` — generation + logit statistics + adaptive sampling**
   Core API: `load_model(path, adapter=None, backend="transformers")`, `generate(model, tokenizer, prompt, **kwargs)`, `generate_stream(...)` (streaming via `TextIteratorStreamer`), `logit_stats(logits) -> {entropy, top1_prob, effective_vocab}`, `adaptive_sample(logits, temperature, top_k, top_p, entropy_threshold=6.5)`. Chat template reuse via `tokenizer.apply_chat_template`. Fallback to `"role: content"` join when no template. Shared by `chat.py`, `judge.py`, `synthetic.py`.
   ```python
   from forgelm.inference import load_model, generate
   model, tok = load_model("./outputs/my_run", adapter="./outputs/my_run/adapter_model")
   text = generate(model, tok, "Hello", max_new_tokens=200, temperature=0.7)
   ```

2. [x] **`forgelm chat` — interactive terminal loop**
   Terminal REPL in `forgelm/chat.py`: streaming output (default), `/reset`, `/save [file]`, `/temperature 0.x`, `/system <prompt>`, `/help` commands. `rich` optional rendering. History management with 50-pair cap. The `--safety` per-turn screen flag is planned for v0.6.0+ Pro CLI (today's safety pipeline runs through the YAML `safety:` block during training/eval).
   ```bash
   forgelm chat ./outputs/my_run
   ```

   `forgelm chat`'s shipping form takes a positional checkpoint path
   plus optional `--adapter`. The per-turn Llama Guard screen via
   `--safety` is planned for v0.6.0+ Pro CLI (see Phase 13 roadmap);
   today operators get the same screening by enabling
   `safety: enabled: true` in the YAML config the chat REPL reads.
   The flag-form preview (`forgelm chat ... --safety`) is NOT
   runnable today.

3. [x] **`forgelm export` — HF → GGUF conversion**
   Wraps `llama-cpp-python`'s `convert_hf_to_gguf.py`; no reimplementation. Handles adapter merge (LoRA + base → merged fp16) before conversion. Supports quants: `q2_k`, `q3_k_m`, `q4_k_m`, `q5_k_m`, `q8_0`, `f16`. SHA-256 of output artifact appended to `model_integrity.json`. Optional dependency: `pip install forgelm[export]`.
   ```bash
   forgelm export ./outputs/my_run --format gguf --quant q4_k_m --output model.gguf
   ```

4. [x] **`--fit-check` — VRAM fit advisor**
   Pre-flight memory estimator in `forgelm/fit_check.py`. Detects GPU via `torch.cuda.mem_get_info()`. Estimates peak VRAM = base (params × dtype) + LoRA adapter + optimizer state (AdamW/8bit/GaLore variants) + activations (with gradient-checkpointing scaling). Produces verdict (FITS / TIGHT / OOM / UNKNOWN) with ordered recommendations. Falls back to hypothetical mode when no GPU is detected.
   ```bash
   forgelm --config my.yaml --fit-check
   # → GPU: RTX 3060 12GB; Estimated peak: 10.8 GB; Verdict: ✅ FITS
   forgelm --config my.yaml --fit-check --output-format json
   ```

5. [x] **`forgelm deploy` — serving handoff config generation**
   Template-based config generation in `forgelm/deploy.py`; does not run the server. Targets: `ollama` (Modelfile), `vllm` (engine config YAML), `tgi` (docker-compose.yaml), `hf-endpoints` (JSON spec). All targets support `--output-format json`.
   ```bash
   forgelm deploy ./outputs/my_run --target ollama --output ./Modelfile
   forgelm deploy ./outputs/my_run --target vllm --output ./vllm_config.yaml
   forgelm deploy ./outputs/my_run --target tgi --output ./docker-compose.yaml
   forgelm deploy ./outputs/my_run --target hf-endpoints --output ./endpoint.json
   ```

### Requirements:
- All five modules must work without GPU for config generation (fit-check excepted — it reads GPU but doesn't require one, falls back to hypothetical mode).
- `inference.py` and `chat.py` share the same load/generate primitives with `safety.py`, `judge.py`, and `synthetic.py`; refactor duplicated `model.generate()` calls into the new module.
- Each CLI command supports `--output-format json` for pipeline integration.
- `pip install forgelm[export]` is optional; core install must not require `llama-cpp-python`.
- Windows/Linux/macOS compatibility for all CLI surface (GGUF export may require specific toolchains, document clearly).

### Delivery:
- Target release: `v0.4.0` ("Post-Training Completion")
- Each task = independent PR with tests; no cross-task blocking dependencies.

---
