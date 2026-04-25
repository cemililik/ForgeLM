"""
Core inference primitives shared across chat, judge, synthetic, and safety modules.

Provides a unified load/generate interface with streaming support, logit statistics,
and adaptive sampling.  Heavy dependencies (torch, transformers, peft) are imported
lazily so that --help and config parsing remain lightweight.
"""
from __future__ import annotations

import logging
import math
from threading import Thread
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("forgelm.inference")


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def load_model(
    path: str,
    adapter: Optional[str] = None,
    backend: str = "transformers",
    load_in_4bit: bool = False,
    load_in_8bit: bool = False,
    trust_remote_code: bool = False,
    device_map: Optional[str] = "auto",
) -> Tuple[Any, Any]:
    """Load a causal LM and tokenizer for inference.

    Args:
        path: Local directory or HF Hub model ID.
        adapter: Optional PEFT adapter path.  Adapter weights are merged into
            the base model and unloaded so generation is self-contained.
        backend: ``"transformers"`` (default) or ``"unsloth"``.
        load_in_4bit: Enable bitsandbytes 4-bit NF4 quantisation (CUDA only).
        load_in_8bit: Enable bitsandbytes 8-bit quantisation (CUDA only).
        trust_remote_code: Allow execution of model-bundled code.
        device_map: Passed directly to ``from_pretrained``; ``"auto"`` for
            multi-GPU, ``None`` to skip placement (e.g. CPU-only).

    Returns:
        ``(model, tokenizer)`` tuple ready for generation.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if backend.lower() == "unsloth":
        return _load_unsloth(path, adapter, trust_remote_code)

    logger.info("Loading model for inference: %s", path)

    tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=trust_remote_code)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: Dict[str, Any] = {"trust_remote_code": trust_remote_code}
    if device_map is not None:
        model_kwargs["device_map"] = device_map

    if torch.cuda.is_available():
        if load_in_4bit:
            from transformers import BitsAndBytesConfig

            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        elif load_in_8bit:
            model_kwargs["load_in_8bit"] = True

    model = AutoModelForCausalLM.from_pretrained(path, **model_kwargs)
    model.eval()

    if adapter:
        logger.info("Loading PEFT adapter from %s, merging into base model.", adapter)
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
        model = model.merge_and_unload()
        logger.info("Adapter merged and unloaded.")

    return model, tokenizer


def _load_unsloth(
    path: str,
    adapter: Optional[str],
    trust_remote_code: bool,
) -> Tuple[Any, Any]:
    """Load model via the Unsloth backend for faster inference."""
    try:
        from unsloth import FastLanguageModel
    except ImportError as e:
        raise ImportError(
            "Unsloth backend requested but 'unsloth' is not installed.  "
            "Install with: pip install unsloth"
        ) from e

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=path,
        dtype=None,
        load_in_4bit=True,
        trust_remote_code=trust_remote_code,
    )
    FastLanguageModel.for_inference(model)

    if adapter:
        logger.warning(
            "Unsloth backend: separate adapter loading is not supported.  "
            "Merge the adapter into the base model before inference, or use "
            "backend='transformers'."
        )
    return model, tokenizer


# ---------------------------------------------------------------------------
# Input preparation
# ---------------------------------------------------------------------------


def _build_prompt(
    tokenizer: Any,
    messages: List[Dict[str, str]],
) -> str:
    """Format a message list into a prompt string using the tokenizer's chat template.

    Falls back to a plain ``role: content`` concatenation when no template is
    available (e.g. raw base models).
    """
    if getattr(tokenizer, "chat_template", None) and hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    parts: List[str] = []
    for msg in messages:
        parts.append(f"{msg['role']}: {msg['content']}")
    return "\n".join(parts)


def _to_messages(
    prompt: str,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Assemble a message list from a user prompt, optional system prompt, and history."""
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    messages: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    top_k: int = 50,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
    do_sample: bool = True,
) -> str:
    """Generate a response for *prompt*.

    Handles chat template formatting automatically.  Pass *messages* to supply
    a pre-built message list (e.g. for multi-turn chat); otherwise the function
    builds one from *prompt*, *system_prompt*, and *history*.

    Returns the generated response text only (input tokens stripped).
    """
    import torch

    if messages is None:
        messages = _to_messages(prompt, system_prompt, history)

    text = _build_prompt(tokenizer, messages)
    input_ids = tokenizer(text, return_tensors="pt").input_ids.to(model.device)

    gen_kwargs: Dict[str, Any] = dict(
        input_ids=input_ids,
        max_new_tokens=max_new_tokens,
        do_sample=do_sample,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    if do_sample:
        gen_kwargs.update(temperature=temperature, top_k=top_k, top_p=top_p)
    gen_kwargs["repetition_penalty"] = repetition_penalty

    with torch.inference_mode():
        output_ids = model.generate(**gen_kwargs)

    new_tokens = output_ids[0][input_ids.shape[-1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def generate_stream(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    messages: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    top_k: int = 50,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
    do_sample: bool = True,
) -> Iterator[str]:
    """Stream generation token-by-token.

    Yields decoded text fragments as they are produced.  Uses
    ``TextIteratorStreamer`` in a background thread so the caller's loop can
    update the UI without blocking.
    """
    from transformers import TextIteratorStreamer

    if messages is None:
        messages = _to_messages(prompt, system_prompt, history)

    text = _build_prompt(tokenizer, messages)
    input_ids = tokenizer(text, return_tensors="pt").input_ids.to(model.device)

    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

    gen_kwargs: Dict[str, Any] = dict(
        input_ids=input_ids,
        max_new_tokens=max_new_tokens,
        do_sample=do_sample,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        streamer=streamer,
    )
    if do_sample:
        gen_kwargs.update(temperature=temperature, top_k=top_k, top_p=top_p)
    gen_kwargs["repetition_penalty"] = repetition_penalty

    thread = Thread(target=model.generate, kwargs=gen_kwargs, daemon=True)
    thread.start()

    for token_text in streamer:
        yield token_text

    thread.join()


# ---------------------------------------------------------------------------
# Logit statistics
# ---------------------------------------------------------------------------


def logit_stats(logits: Any) -> Dict[str, float]:
    """Compute generation-quality statistics from a single-position logit tensor.

    Args:
        logits: 1-D tensor of shape ``[vocab_size]``.

    Returns:
        Dict with keys:
          - ``entropy``: Shannon entropy (nats) over the softmax distribution.
          - ``top1_prob``: Probability of the argmax token.
          - ``effective_vocab``: Number of tokens with probability > 1 %.
    """
    import torch

    probs = torch.softmax(logits.float(), dim=-1)
    log_probs = torch.log(probs + 1e-10)
    entropy = float(-torch.sum(probs * log_probs).item())
    top1_prob = float(probs.max().item())
    effective_vocab = int((probs > 0.01).sum().item())
    return {
        "entropy": round(entropy, 4),
        "top1_prob": round(top1_prob, 4),
        "effective_vocab": effective_vocab,
    }


# ---------------------------------------------------------------------------
# Adaptive sampling
# ---------------------------------------------------------------------------


def adaptive_sample(
    logits: Any,
    temperature: float = 1.0,
    top_k: int = 50,
    top_p: float = 0.9,
    entropy_threshold: float = 6.5,
) -> int:
    """Sample the next token with entropy-adaptive strategy.

    When the model is confident (entropy < *entropy_threshold*), uses greedy
    decoding to avoid introducing noise.  For high-entropy distributions,
    applies temperature scaling followed by top-k and nucleus (top-p) filtering
    before sampling.

    Args:
        logits: 1-D tensor of shape ``[vocab_size]``.
        temperature: Scaling factor for logits in sampling mode.
        top_k: Keep only the *top_k* most likely tokens.
        top_p: Nucleus probability mass threshold.
        entropy_threshold: Shannon entropy (nats) below which greedy decoding
            is used.  ``math.log(vocab_size)`` ≈ 10.8 for a 50 k vocab.

    Returns:
        Integer token index.
    """
    import torch

    probs = torch.softmax(logits.float(), dim=-1)
    entropy = float(-torch.sum(probs * torch.log(probs + 1e-10)).item())

    if entropy < entropy_threshold:
        return int(logits.argmax().item())

    # Temperature scaling
    scaled = logits.float() / max(temperature, 1e-6)

    # Top-k filtering
    if top_k > 0:
        k = min(top_k, scaled.size(-1))
        top_vals, _ = torch.topk(scaled, k)
        cutoff = top_vals[..., -1].unsqueeze(-1)
        scaled = scaled.masked_fill(scaled < cutoff, float("-inf"))

    # Nucleus (top-p) filtering
    if 0.0 < top_p < 1.0:
        sorted_logits, sorted_idx = torch.sort(scaled, descending=True)
        cumulative = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
        remove = cumulative - torch.softmax(sorted_logits, dim=-1) > top_p
        sorted_logits[remove] = float("-inf")
        scaled = scaled.scatter(-1, sorted_idx, sorted_logits)

    sample_probs = torch.softmax(scaled, dim=-1)
    return int(torch.multinomial(sample_probs, num_samples=1).item())
