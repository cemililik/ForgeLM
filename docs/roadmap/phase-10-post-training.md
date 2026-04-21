# Phase 10: Post-Training Completion

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md).

**Goal:** Close the "trained, now what?" gap. After a fine-tune finishes, users should be able to sanity-check, export, and hand the model to a serving runtime (Ollama, vLLM, TGI) without leaving ForgeLM.
**Estimated Effort:** Medium (2-3 months)
**Priority:** High — single biggest post-9 UX gap; foundation for Phase 12 (quickstart)

> **Context:** External analyses of two adjacent projects (QKV-Core, Trion) plus internal retrospectives converged on the same finding: ForgeLM stops at `output_dir/` with an HF-format adapter/merged model, but the user's actual journey continues to sanity chat → quantization → serving. Competitors (Axolotl, Unsloth) leave this to external tooling. Owning this handoff — without rewriting the inference ecosystem — is a high-value, low-risk addition.

### Tasks:

1. [ ] **`forgelm/inference.py` — generation + logit statistics + adaptive sampling**
   Core API: `load_model(path, adapter=None, backend="transformers")`, `generate(model, tokenizer, prompt, **kwargs)`, `logit_stats(logits) -> {entropy, top1_prob, effective_vocab}`, `adaptive_sample(logits, temperature, top_k, top_p, entropy_threshold=6.5)`. Chat template reuse from `data.py`. Streaming + non-streaming via `TextIteratorStreamer`. Opt-in safety routing through existing `safety.py`.
   ```python
   from forgelm.inference import load_model, generate
   model, tok = load_model("./outputs/my_run", adapter="./outputs/my_run/adapter_model")
   text = generate(model, tok, "Hello", max_new_tokens=200, temperature=0.7)
   ```

2. [ ] **`forgelm chat` — interactive terminal loop**
   Terminal REPL: streaming output, `/reset`, `/save`, `/temperature 0.x`, `/system <prompt>` commands. `rich` for rendering. Auto-detect HF model vs merged adapter. Optional `--safety` flag wires Llama Guard check on each response (bridge to Layer 3 enterprise features).
   ```bash
   forgelm chat ./outputs/my_run
   forgelm chat ./outputs/my_run --adapter ./outputs/my_run/adapter_model --safety
   ```

3. [ ] **`forgelm export` — HF → GGUF conversion**
   Wrap `llama-cpp-python`'s conversion scripts; do not reimplement. Handle adapter merge (LoRA + base → single weights) before conversion. Support quants: `q2_k`, `q3_k_m`, `q4_k_m`, `q5_k_m`, `q8_0`, `f16`. Integrate with `compliance.py`: exported artifact SHA-256 added to `model_integrity.json`. Optional dependency: `pip install forgelm[export]`.
   ```bash
   forgelm export ./outputs/my_run --format gguf --quant q4_k_m --output model.gguf
   ```

4. [ ] **`forgelm fit-check` — VRAM fit advisor**
   Pre-flight memory estimator. Detects GPU via `torch.cuda.mem_get_info()`. Estimates peak VRAM = base (params × dtype) + activations (heuristic: batch × seq × hidden × 4 × layers) + optimizer state (AdamW 2×, 8bit 0.5×, GaLore rank-dependent). Produces verdict (FITS / TIGHT / OOM) and ordered recommendations (batch↓, seq↓, gradient_checkpointing, QLoRA, GaLore). Calibrated against known model-config pairs; target ±15% accuracy.
   ```bash
   forgelm --config my.yaml --fit-check
   # → GPU: RTX 3060 12GB; Estimated peak: 10.8 GB; Verdict: ✅ FITS with 0.5 GB headroom
   ```

5. [ ] **`forgelm deploy` — serving handoff config generation**
   Generates deployment configs for popular inference runtimes; does not run the server itself. Targets: `ollama` (Modelfile), `vllm` (engine config YAML), `tgi` (docker-compose.yaml), `hf-endpoints` (API spec). Output is a ready-to-consume file the user runs with the target tool.
   ```bash
   forgelm deploy ./outputs/my_run --target ollama --output ./Modelfile
   forgelm deploy ./outputs/my_run --target vllm --output ./vllm_config.yaml
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
