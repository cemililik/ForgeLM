# Troubleshooting & FAQ

Common issues and solutions when using ForgeLM.

---

## Installation Issues

### `ModuleNotFoundError: No module named 'bitsandbytes'`

bitsandbytes (QLoRA) only works on Linux:

```bash
# Linux only
pip install forgelm[qlora]

# macOS/Windows: disable 4-bit quantization
# In your config:
model:
  load_in_4bit: false
```

### `ModuleNotFoundError: No module named 'unsloth'`

Unsloth only works on Linux:

```bash
# Linux only
pip install forgelm[unsloth]

# Other platforms: use transformers backend
model:
  backend: "transformers"
```

### `ImportError: lm-evaluation-harness is required`

```bash
pip install forgelm[eval]
```

---

## Training Issues

### CUDA Out of Memory (OOM)

**Solutions (in order of impact):**

1. **Enable 4-bit quantization** (if not already):
   ```yaml
   model:
     load_in_4bit: true
   ```

2. **Reduce batch size**:
   ```yaml
   training:
     per_device_train_batch_size: 1
     gradient_accumulation_steps: 8  # keep effective batch size
   ```

3. **Reduce max sequence length**:
   ```yaml
   model:
     max_length: 1024  # down from 2048
   ```

4. **Use DeepSpeed ZeRO-3 for large models**:
   ```yaml
   distributed:
     strategy: "deepspeed"
     deepspeed_config: "zero3_offload"
   ```

5. **Reduce LoRA rank**:
   ```yaml
   lora:
     r: 8  # down from 16
   ```

### Training Loss is NaN or Inf

**Causes:**
- Learning rate too high
- Batch size too small without gradient accumulation
- Mixed precision issues

**Solutions:**

```yaml
training:
  learning_rate: 1.0e-5  # reduce from 2e-5
  gradient_accumulation_steps: 4
```

If persists, disable mixed precision by ensuring `bf16: false` and `fp16: false` (these are ForgeLM defaults).

### Training is Very Slow

1. **Use Unsloth** (Linux, 2-5x speedup):
   ```yaml
   model:
     backend: "unsloth"
   ```

2. **Enable packing** (if your data supports it):
   ```yaml
   training:
     packing: true
   ```

3. **Use multiple GPUs**:
   ```yaml
   distributed:
     strategy: "deepspeed"
     deepspeed_config: "zero2"
   ```

### `ValueError: Unknown trainer_type`

Valid trainer types: `sft`, `orpo`, `dpo`, `simpo`, `kto`, `grpo`

```yaml
training:
  trainer_type: "sft"  # check spelling
```

### `KeyError: Dataset must contain 'chosen' and 'rejected' columns`

Your dataset format doesn't match the trainer type:

| Trainer | Required Columns |
|---------|-----------------|
| `sft` | `User`/`instruction` + `Assistant`/`output`, or `messages` |
| `dpo`, `simpo`, `orpo` | `chosen` + `rejected` |
| `kto` | `completion` + `label` (boolean) |
| `grpo` | `prompt` |

---

## Configuration Issues

### How to Validate Config Without Training

```bash
forgelm --config my_config.yaml --dry-run
```

### Config Validation Error: Field Type Mismatch

ForgeLM uses Pydantic v2 for validation. Error messages show the exact field:

```
Configuration validation failed: 1 validation error for ForgeConfig
training -> learning_rate
  Input should be a valid number [type=float_parsing, input_value='not_a_number']
```

Fix the YAML value to match the expected type.

### Unknown Fields in Config

Extra/unknown fields in YAML are silently ignored (Pydantic v2 default). This means typos like `lerning_rate` won't cause an error — they'll just be ignored with the default value used instead.

**Tip:** Always use `--dry-run` to verify resolved values.

---

## Evaluation Issues

### Auto-Revert Keeps Deleting My Model

Your evaluation thresholds may be too strict:

```yaml
evaluation:
  auto_revert: true
  max_acceptable_loss: 2.0  # increase this if models keep being reverted
```

Or disable auto-revert and check manually:

```yaml
evaluation:
  auto_revert: false
```

### Benchmark Scores Are Zero

- Check that `lm-eval` is installed: `pip install forgelm[eval]`
- Check that benchmark tasks are valid: `arc_easy`, `hellaswag`, `mmlu`, etc.
- Try with `limit: 10` first for quick testing:
  ```yaml
  evaluation:
    benchmark:
      enabled: true
      tasks: ["arc_easy"]
      limit: 10
  ```

---

## Multi-GPU Issues

### NCCL Errors

```bash
# Increase timeout
export NCCL_TIMEOUT=1800

# Debug NCCL
export NCCL_DEBUG=INFO

# Check GPUs are visible
nvidia-smi
```

### DeepSpeed Config Not Found

```
FileNotFoundError: DeepSpeed preset 'zero2' not found
```

Ensure you're running from the ForgeLM project root, or use an absolute path:

```yaml
distributed:
  deepspeed_config: "/path/to/ForgeLM/configs/deepspeed/zero2.json"
```

### QLoRA + ZeRO-3 Issues

QLoRA (4-bit) with DeepSpeed ZeRO-3 has known compatibility issues. Use ZeRO-2 instead:

```yaml
distributed:
  strategy: "deepspeed"
  deepspeed_config: "zero2"  # not zero3
```

---

## Docker Issues

### GPU Not Detected in Docker

```bash
# Ensure NVIDIA Container Toolkit is installed
nvidia-smi  # should work on host

# Run with GPU support
docker run --gpus all forgelm --version
```

### Shared Memory Error in Multi-GPU Docker

```bash
docker run --gpus all --shm-size=16g ...
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | Success | Model is ready |
| `1` | Config error | Fix your YAML |
| `2` | Training error | Check GPU, memory, dependencies |
| `3` | Evaluation failure | Model quality below threshold — adjust thresholds or improve data |
| `4` | Awaiting approval | Human review required — run `forgelm --approve <run_id>` after review |

---

## Getting Help

- **GitHub Issues**: [github.com/cemililik/ForgeLM/issues](https://github.com/cemililik/ForgeLM/issues)
- **Dry-run debug**: `forgelm --config job.yaml --dry-run --log-level DEBUG`
- **JSON diagnostics**: `forgelm --config job.yaml --output-format json 2>error.log`
