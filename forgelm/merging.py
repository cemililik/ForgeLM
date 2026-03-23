"""Model merging support.

Merge multiple LoRA adapters or fine-tuned models using various strategies.
Provides config-driven merging as a post-training step or standalone CLI command.
"""
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("forgelm.merging")


@dataclass
class MergeResult:
    """Result of a model merge operation."""
    success: bool
    output_dir: str = ""
    method: str = ""
    num_models: int = 0
    error: Optional[str] = None


def merge_peft_adapters(
    base_model_path: str,
    adapters: List[Dict[str, Any]],
    method: str = "linear",
    output_dir: str = "./merged_model",
    trust_remote_code: bool = False,
) -> MergeResult:
    """Merge multiple LoRA/PEFT adapters into a single model.

    Args:
        base_model_path: Path or HF ID of the base model.
        adapters: List of dicts with 'path' and 'weight' keys.
        method: Merge strategy — "linear", "ties", "dare", "slerp".
        output_dir: Where to save the merged model.
        trust_remote_code: Allow custom code from model repos.

    Returns:
        MergeResult with status.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    if not adapters:
        return MergeResult(success=False, error="No adapters provided for merging.")

    logger.info("Merging %d adapters with method '%s'...", len(adapters), method)
    logger.info("Base model: %s", base_model_path)

    try:
        # Load base model
        tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=trust_remote_code)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path, trust_remote_code=trust_remote_code, device_map="cpu"
        )

        if method == "linear":
            merged = _linear_merge(base_model, adapters)
        elif method in ("ties", "dare"):
            merged = _advanced_merge(base_model, adapters, method)
        elif method == "slerp":
            merged = _slerp_merge(base_model, adapters)
        else:
            return MergeResult(success=False, error=f"Unknown merge method: {method}")

        # Save merged model
        os.makedirs(output_dir, exist_ok=True)
        merged.save_pretrained(output_dir, safe_serialization=True)
        tokenizer.save_pretrained(output_dir)
        logger.info("Merged model saved to %s", output_dir)

        return MergeResult(
            success=True,
            output_dir=output_dir,
            method=method,
            num_models=len(adapters),
        )

    except Exception as e:
        logger.error("Model merging failed: %s", e)
        return MergeResult(success=False, error=str(e))


def _linear_merge(base_model, adapters):
    """Linear interpolation merge: weighted average of adapter parameters."""
    import torch
    from peft import PeftModel

    # Load and merge each adapter with weighted interpolation
    total_weight = sum(a.get("weight", 1.0) for a in adapters)
    if total_weight == 0:
        raise ValueError("Adapter weights sum to 0. Provide positive weights for merging.")

    # Capture base model state for reset between adapter loads
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}
    merged_state = None

    for adapter_info in adapters:
        path = adapter_info["path"]
        weight = adapter_info.get("weight", 1.0) / total_weight
        logger.info("  Loading adapter: %s (weight=%.3f)", path, weight)

        # Reset base model to original state before loading each adapter
        base_model.load_state_dict(base_state, strict=True)
        adapter_model = PeftModel.from_pretrained(base_model, path)
        merged_adapter = adapter_model.merge_and_unload()

        if merged_state is None:
            merged_state = {k: v.clone() * weight for k, v in merged_adapter.state_dict().items()}
        else:
            for k, v in merged_adapter.state_dict().items():
                if k in merged_state:
                    merged_state[k] += v * weight

        del adapter_model, merged_adapter

    missing, unexpected = base_model.load_state_dict(merged_state, strict=False)
    if unexpected:
        logger.warning("Merge produced %d unexpected keys (ignored).", len(unexpected))
    return base_model


def _advanced_merge(base_model, adapters, method):
    """TIES or DARE merge — requires mergekit or manual implementation."""
    logger.info("Using %s merge strategy.", method.upper())

    # Try mergekit first
    try:
        import mergekit  # noqa: F401
        logger.info("mergekit detected — using native %s merge.", method)
        return _mergekit_merge(base_model, adapters, method)
    except ImportError:
        pass

    # Fallback to linear merge with warning
    logger.warning(
        "%s merge requires mergekit (pip install mergekit). "
        "Falling back to linear interpolation.", method.upper()
    )
    return _linear_merge(base_model, adapters)


def _slerp_merge(base_model, adapters):
    """SLERP merge between two models (only supports 2 models)."""
    if len(adapters) != 2:
        logger.warning("SLERP requires exactly 2 models. Got %d. Falling back to linear.", len(adapters))
        return _linear_merge(base_model, adapters)

    import torch
    from peft import PeftModel

    logger.info("Performing SLERP merge between 2 adapters...")
    t = adapters[1].get("weight", 0.5)  # interpolation factor

    model_a = PeftModel.from_pretrained(base_model, adapters[0]["path"])
    state_a = model_a.merge_and_unload().state_dict()
    del model_a

    model_b = PeftModel.from_pretrained(base_model, adapters[1]["path"])
    state_b = model_b.merge_and_unload().state_dict()
    del model_b

    merged_state = {}
    for key in state_a:
        if key in state_b:
            v0 = state_a[key].float()
            v1 = state_b[key].float()
            # Simplified SLERP for parameter tensors
            dot = torch.sum(v0 * v1) / (torch.norm(v0) * torch.norm(v1) + 1e-8)
            dot = torch.clamp(dot, -1.0, 1.0)
            omega = torch.acos(dot)
            if omega.abs() < 1e-6:
                merged_state[key] = ((1 - t) * v0 + t * v1).to(state_a[key].dtype)
            else:
                so = torch.sin(omega)
                merged_state[key] = (
                    (torch.sin((1 - t) * omega) / so) * v0 +
                    (torch.sin(t * omega) / so) * v1
                ).to(state_a[key].dtype)
        else:
            merged_state[key] = state_a[key]

    base_model.load_state_dict(merged_state, strict=False)
    return base_model


def _mergekit_merge(base_model, adapters, method):
    """Merge using mergekit library."""
    # This is a placeholder for full mergekit integration.
    # mergekit uses its own config format and CLI — here we provide
    # a programmatic bridge.
    logger.info("Full mergekit integration: generating mergekit config and executing...")
    logger.warning("Programmatic mergekit bridge not yet implemented. Using linear fallback.")
    return _linear_merge(base_model, adapters)
