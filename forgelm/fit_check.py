"""
VRAM fit advisor for ForgeLM training configurations.

Estimates peak GPU memory consumption *before* loading any model weights,
using only the model's architecture config and the training hyperparameters.
Targets ±15 % accuracy against empirically measured values.

Usage (programmatic):
    from forgelm.fit_check import estimate_vram
    result = estimate_vram(forge_config)
    print(result.verdict, result.estimated_gb)

Usage (CLI):
    forgelm --config my.yaml --fit-check
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("forgelm.fit_check")

# VRAM verdict thresholds (fraction of available memory)
_TIGHT_THRESHOLD = 0.85
_OOM_THRESHOLD = 0.95

# Bytes per parameter for each dtype/quant scheme
_BYTES_PER_PARAM: Dict[str, float] = {
    "4bit": 0.5,
    "8bit": 1.0,
    "bf16": 2.0,
    "fp16": 2.0,
    "fp32": 4.0,
}

# Known model size defaults keyed by name fragment (lowercase) for fallback
_MODEL_SIZE_HINTS: Dict[str, Tuple[int, int, int]] = {
    # (hidden_size, num_layers, intermediate_size)
    "1b": (2048, 16, 8192),
    "3b": (3072, 28, 8192),
    "7b": (4096, 32, 11008),
    "8b": (4096, 32, 14336),
    "13b": (5120, 40, 13824),
    "14b": (5120, 40, 13824),
    "30b": (6656, 60, 17920),
    "34b": (7168, 48, 20480),
    "70b": (8192, 80, 28672),
    "72b": (8192, 80, 29568),
}


@dataclass
class FitCheckResult:
    """Result of a VRAM estimation run."""

    verdict: str  # "FITS", "TIGHT", "OOM", or "UNKNOWN" (no GPU detected)
    estimated_gb: float
    available_gb: Optional[float]
    recommendations: List[str] = field(default_factory=list)
    breakdown: Dict[str, float] = field(default_factory=dict)
    hypothetical: bool = False  # True when no GPU was detected


# ---------------------------------------------------------------------------
# Architecture parameter extraction
# ---------------------------------------------------------------------------


def _load_arch_params(model_name_or_path: str, trust_remote_code: bool = False) -> Dict[str, Any]:
    """Fetch architecture parameters from HF config without loading weights.

    Returns a dict with guaranteed keys: hidden_size, num_hidden_layers,
    intermediate_size, vocab_size, num_attention_heads, num_key_value_heads.
    Falls back to size-hint heuristics when the config cannot be loaded.
    """
    params: Dict[str, Any] = {}
    try:
        from transformers import AutoConfig

        cfg = AutoConfig.from_pretrained(model_name_or_path, trust_remote_code=trust_remote_code)
        params["hidden_size"] = getattr(cfg, "hidden_size", None)
        params["num_hidden_layers"] = getattr(cfg, "num_hidden_layers", None)
        params["intermediate_size"] = getattr(cfg, "intermediate_size", None)
        params["vocab_size"] = getattr(cfg, "vocab_size", None)
        params["num_attention_heads"] = getattr(cfg, "num_attention_heads", None)
        params["num_key_value_heads"] = getattr(cfg, "num_key_value_heads", None)
        logger.debug("Loaded architecture config from %s", model_name_or_path)
    except Exception as e:
        logger.debug("Could not load AutoConfig for %s: %s — using size hint fallback.", model_name_or_path, e)

    # Fill in missing values using size-hint lookup on the model name
    name_lower = str(model_name_or_path).lower()
    hint: Optional[Tuple[int, int, int]] = None
    for fragment, h in _MODEL_SIZE_HINTS.items():
        if fragment in name_lower:
            hint = h
            break

    defaults = {
        "hidden_size": hint[0] if hint else 4096,
        "num_hidden_layers": hint[1] if hint else 32,
        "intermediate_size": hint[2] if hint else 11008,
        "vocab_size": 32000,
        "num_attention_heads": 32,
        "num_key_value_heads": 32,
    }
    for key, default in defaults.items():
        if params.get(key) is None:
            params[key] = default

    # Derived: GQA key-value groups
    if params["num_key_value_heads"] is None:
        params["num_key_value_heads"] = params["num_attention_heads"]

    return params


def _estimate_param_count(arch: Dict[str, Any]) -> int:
    """Estimate total parameter count from architecture dimensions.

    Accounts for: embeddings, per-layer attention (GQA-aware), per-layer FFN
    (SwiGLU/GeGLU style with gate+up+down), and layer-norm weights.
    Does NOT include optional biases (usually small).
    """
    h = arch["hidden_size"]
    n_layers = arch["num_hidden_layers"]
    vocab = arch["vocab_size"]
    intermediate = arch["intermediate_size"]
    n_heads = arch["num_attention_heads"]
    n_kv = arch["num_key_value_heads"]
    head_dim = h // n_heads

    # Embedding + LM head (often tied; treat as single copy for conservative estimate)
    embedding_params = vocab * h

    # Attention projections: Q (h×h), K (h × kv_heads×head_dim), V (same as K), O (h×h)
    q_params = h * h
    kv_params = h * n_kv * head_dim
    o_params = h * h
    attn_params = q_params + 2 * kv_params + o_params

    # FFN: gate + up (h → intermediate) and down (intermediate → h); SwiGLU has 3 matrices
    ffn_params = 3 * h * intermediate

    # Layer norms: 2 per layer (pre-attn + pre-ffn), each of size h
    ln_params = 2 * h

    per_layer = attn_params + ffn_params + ln_params
    total = embedding_params + n_layers * per_layer + h  # +h for final norm

    return int(total)


# ---------------------------------------------------------------------------
# VRAM component estimators
# ---------------------------------------------------------------------------


def _base_model_gb(num_params: int, quant: str) -> float:
    """Model weight memory in GB."""
    bpp = _BYTES_PER_PARAM.get(quant, 2.0)
    return num_params * bpp / (1024 ** 3)


def _lora_adapter_gb(arch: Dict[str, Any], lora_r: int, target_module_count: int) -> float:
    """LoRA adapter parameter memory in GB (always fp32 trainable params)."""
    h = arch["hidden_size"]
    # Each target module: A (h×r) + B (r×h); two matrices per layer × num_layers
    adapter_params = 2 * lora_r * h * target_module_count * arch["num_hidden_layers"]
    return adapter_params * 4 / (1024 ** 3)  # fp32


def _optimizer_state_gb(trainable_params: int, optimizer: str) -> float:
    """Optimizer state memory in GB.

    AdamW (fp32 moments): 8 bytes per trainable parameter.
    8-bit Adam: ~2 bytes per trainable parameter.
    Adafactor: ~4 bytes (first moment only, optional).
    """
    optimizer_lower = optimizer.lower()
    if "8bit" in optimizer_lower or "8_bit" in optimizer_lower:
        bpp = 2.0
    elif "adafactor" in optimizer_lower:
        bpp = 4.0
    else:
        bpp = 8.0  # AdamW default
    return trainable_params * bpp / (1024 ** 3)


def _activation_gb(
    arch: Dict[str, Any],
    batch_size: int,
    seq_len: int,
    gradient_checkpointing: bool,
) -> float:
    """Activation memory in GB during the backward pass.

    Heuristic: batch × seq × hidden × 4 (bytes fp16) × layers × 2 (fwd+bwd).
    Gradient checkpointing reduces this by roughly sqrt(num_layers).
    """
    h = arch["hidden_size"]
    n_layers = arch["num_hidden_layers"]
    # Activation per layer: q,k,v,attn_scores,attn_probs,ffn_intermediate
    bytes_per_token_per_layer = h * 2 * 6  # 6 activation tensors, fp16
    raw_gb = batch_size * seq_len * bytes_per_token_per_layer * n_layers / (1024 ** 3)

    if gradient_checkpointing:
        # Recompute activations during backward; only store ~sqrt(n) checkpoints
        factor = max(math.sqrt(n_layers), 1.0)
        return raw_gb / factor
    return raw_gb * 2  # forward + backward without checkpointing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def estimate_vram(config: Any) -> FitCheckResult:
    """Estimate peak training VRAM for a ForgeConfig.

    Queries the model's architecture via AutoConfig (network call on first run
    for HF Hub models; cached by transformers).  Falls back to size-hint
    heuristics when the config cannot be fetched (offline, private models).

    Returns a :class:`FitCheckResult` with verdict, breakdown, and ordered
    recommendations.
    """
    import torch

    t = config.training
    m = config.model
    lora = config.lora

    # --- architecture ---
    arch = _load_arch_params(m.name_or_path, trust_remote_code=m.trust_remote_code)
    num_params = _estimate_param_count(arch)

    # --- quantisation scheme ---
    if m.load_in_4bit:
        quant = "4bit"
    else:
        dtype = getattr(m, "bnb_4bit_compute_dtype", "bf16")
        quant = {"auto": "bf16", "bfloat16": "bf16", "bf16": "bf16", "float16": "fp16", "fp16": "fp16"}.get(
            str(dtype).lower(), "bf16"
        )

    # --- component estimates ---
    base_gb = _base_model_gb(num_params, quant)

    target_module_count = len(lora.target_modules)
    adapter_gb = _lora_adapter_gb(arch, lora.r, target_module_count)
    trainable_params = int(adapter_gb * (1024 ** 3) / 4)  # fp32 param count

    optimizer_type = getattr(t, "galore_optim", "adamw") if getattr(t, "galore_enabled", False) else "adamw"
    optim_gb = _optimizer_state_gb(trainable_params, optimizer_type)

    grad_ckpt = getattr(t, "gradient_checkpointing", False)
    act_gb = _activation_gb(arch, t.per_device_train_batch_size, m.max_length, grad_ckpt)

    # GaLore adds gradient projection buffers (lora-rank-sized per parameter)
    galore_gb = 0.0
    if getattr(t, "galore_enabled", False):
        galore_rank = getattr(t, "galore_rank", 64)
        h = arch["hidden_size"]
        galore_gb = num_params * (galore_rank / h) * 4 / (1024 ** 3)

    total_gb = base_gb + adapter_gb + optim_gb + act_gb + galore_gb

    breakdown = {
        "base_model_gb": round(base_gb, 2),
        "lora_adapter_gb": round(adapter_gb, 2),
        "optimizer_state_gb": round(optim_gb, 2),
        "activations_gb": round(act_gb, 2),
        "galore_buffers_gb": round(galore_gb, 2),
        "total_estimated_gb": round(total_gb, 2),
        "quant_scheme": quant,
        "estimated_param_count_b": round(num_params / 1e9, 2),
    }

    # --- available VRAM ---
    available_gb: Optional[float] = None
    hypothetical = False
    try:
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            available_gb = total_bytes / (1024 ** 3)
        else:
            hypothetical = True
    except Exception as e:
        logger.debug("Could not query GPU memory: %s", e)
        hypothetical = True

    # --- verdict ---
    if hypothetical or available_gb is None:
        verdict = "UNKNOWN"
    elif total_gb <= available_gb * _TIGHT_THRESHOLD:
        verdict = "FITS"
    elif total_gb <= available_gb * _OOM_THRESHOLD:
        verdict = "TIGHT"
    else:
        verdict = "OOM"

    # --- recommendations (ordered by impact) ---
    recommendations = _build_recommendations(
        config=config,
        arch=arch,
        total_gb=total_gb,
        available_gb=available_gb,
        quant=quant,
        grad_ckpt=grad_ckpt,
    )

    return FitCheckResult(
        verdict=verdict,
        estimated_gb=round(total_gb, 2),
        available_gb=round(available_gb, 2) if available_gb is not None else None,
        recommendations=recommendations,
        breakdown=breakdown,
        hypothetical=hypothetical,
    )


def _build_recommendations(
    config: Any,
    arch: Dict[str, Any],
    total_gb: float,
    available_gb: Optional[float],
    quant: str,
    grad_ckpt: bool,
) -> List[str]:
    """Return an ordered list of recommendations to reduce VRAM usage."""
    recs: List[str] = []
    t = config.training
    m = config.model

    if available_gb and total_gb > available_gb * _TIGHT_THRESHOLD:
        # Most impactful first
        if t.per_device_train_batch_size > 1:
            new_bs = max(1, t.per_device_train_batch_size // 2)
            new_accum = t.gradient_accumulation_steps * (t.per_device_train_batch_size // new_bs)
            recs.append(
                f"Reduce per_device_train_batch_size from {t.per_device_train_batch_size} to {new_bs} "
                f"and increase gradient_accumulation_steps to {new_accum} to keep effective batch size."
            )

        if m.max_length > 1024:
            recs.append(
                f"Reduce max_length from {m.max_length} to {m.max_length // 2}; "
                "activation memory scales linearly with sequence length."
            )

        if not grad_ckpt:
            recs.append(
                "Enable gradient_checkpointing: true in your training config; "
                "trades ~20 % compute for significantly lower activation memory."
            )

        if quant not in ("4bit",) and not m.load_in_4bit:
            recs.append(
                "Enable load_in_4bit: true for QLoRA; reduces base model weight memory by ~75 %."
            )

        if not getattr(t, "galore_enabled", False):
            recs.append(
                "Consider galore_enabled: true (GaLore optimizer) for full-parameter "
                "training with gradient low-rank projection, reducing gradient memory."
            )

        if config.lora.r > 16:
            recs.append(
                f"Lower LoRA rank from r={config.lora.r} to 8–16; adapter memory and "
                "optimizer state scale with r."
            )

    return recs


def format_fit_check(result: FitCheckResult) -> str:
    """Format a FitCheckResult as a human-readable multi-line string."""
    lines: List[str] = []
    lines.append("=== VRAM Fit Check ===")

    if result.available_gb is not None:
        lines.append(f"  GPU available: {result.available_gb:.1f} GB")
    else:
        lines.append("  GPU: not detected (hypothetical mode)")

    lines.append(f"  Estimated peak: {result.estimated_gb:.1f} GB")

    verdict_icons = {"FITS": "✅", "TIGHT": "⚠️", "OOM": "❌", "UNKNOWN": "ℹ️"}
    icon = verdict_icons.get(result.verdict, "")
    lines.append(f"  Verdict: {icon} {result.verdict}")
    if result.available_gb and result.verdict == "FITS":
        headroom = result.available_gb - result.estimated_gb
        lines.append(f"           ({headroom:.1f} GB headroom)")

    lines.append("")
    lines.append("  Breakdown:")
    for k, v in result.breakdown.items():
        if k.endswith("_gb"):
            lines.append(f"    {k}: {v} GB")
        else:
            lines.append(f"    {k}: {v}")

    if result.recommendations:
        lines.append("")
        lines.append("  Recommendations (highest impact first):")
        for i, rec in enumerate(result.recommendations, 1):
            lines.append(f"    {i}. {rec}")

    lines.append("======================")
    return "\n".join(lines)
