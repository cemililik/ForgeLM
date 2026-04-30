"""LLM-as-Judge evaluation pipeline.

Uses a strong LLM (API-based or local) to score fine-tuned model outputs
on quality, helpfulness, and instruction-following.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("forgelm.judge")

DEFAULT_RUBRIC = """Score the following AI assistant response on a scale of 1-10.

Criteria:
- Helpfulness: Does it answer the user's question?
- Accuracy: Is the information correct?
- Clarity: Is the response well-structured and easy to understand?
- Instruction-following: Does it follow the user's instructions?

User prompt: {prompt}
Assistant response: {response}

Respond with ONLY a JSON object: {{"score": <1-10>, "reason": "<brief explanation>"}}"""


@dataclass
class JudgeResult:
    """Result of an LLM-as-Judge evaluation."""

    average_score: float = 0.0
    # None entries are sentinel values for parse/transport failures (see
    # _clip_judge_score). Consumers iterating ``scores`` must filter or
    # otherwise handle them; the average is computed over non-None entries.
    scores: List[Optional[float]] = field(default_factory=list)
    passed: bool = True
    failure_reason: Optional[str] = None
    details: List[Dict[str, Any]] = field(default_factory=list)


OPENAI_API_BASE = "https://api.openai.com/v1/chat/completions"


def _parse_judge_json(text: str) -> Dict[str, Any]:
    """Safely parse judge response JSON, handling common LLM output quirks."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from markdown code block
    if "```" in text:
        for block in text.split("```"):
            block = block.strip().removeprefix("json").strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    logger.warning("Could not parse judge response as JSON: %s", text[:200])
    # Use score=None as the failure sentinel — score=0 used to be clipped up
    # to 1.0 by _clip_judge_score and silently lowered the average.
    return {"score": None, "reason": f"Invalid JSON response: {text[:200]}"}


def _call_api_judge(prompt: str, api_key: str, model: str = "gpt-4o", api_base: Optional[str] = None) -> Dict[str, Any]:
    """Call an API-based judge (OpenAI-compatible endpoint).

    Routes through :func:`forgelm._http.safe_post` so SSRF / scheme /
    redirect / timeout / TLS policy is enforced once across every outbound
    call site (see ``forgelm/_http.py``). The bearer token in
    ``Authorization`` is masked from the failure log by ``safe_post``.
    """
    from ._http import HttpSafetyError, safe_post

    url = api_base or OPENAI_API_BASE
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    try:
        response = safe_post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_judge_json(content)
    except HttpSafetyError as e:
        logger.warning("API judge URL rejected by HTTP policy: %s", e)
        return {"score": None, "reason": f"API error: {e}"}
    except json.JSONDecodeError as e:
        logger.warning("API judge returned invalid JSON: %s", e)
        return {"score": None, "reason": f"Invalid JSON from API: {e}"}
    except Exception as e:
        logger.warning("API judge call failed: %s", e)
        return {"score": None, "reason": f"API error: {e}"}


def _call_local_judge(prompt: str, model: Any, tokenizer: Any) -> Dict[str, Any]:
    """Call a local model as judge."""
    import torch

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=200, do_sample=False)
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        return _parse_judge_json(response)
    except Exception as e:
        logger.warning("Local judge evaluation failed: %s", e)
        return {"score": None, "reason": f"Local judge error: {e}"}


def _load_eval_prompts(path: str) -> List[str]:
    """Load prompts from a JSONL file (one prompt per line, plain or JSON object)."""
    prompts: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                prompts.append(data.get("prompt", data.get("text", "")))
            except json.JSONDecodeError:
                prompts.append(line)
    return prompts


def _load_local_judge(judge_model: str) -> Tuple[Any, Any]:
    """Load a local judge model + tokenizer pair."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info("Loading local judge model: %s", judge_model)
    tok = AutoTokenizer.from_pretrained(judge_model)
    mdl = AutoModelForCausalLM.from_pretrained(judge_model, device_map="auto")
    return mdl, tok


def _generate_response(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> str:
    """Generate a single response from the fine-tuned model under evaluation."""
    import torch as _torch

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with _torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    except Exception as e:
        logger.warning("Failed to generate response: %s", e)
        return ""


def _generate_responses_batched(
    model: Any,
    tokenizer: Any,
    prompts: List[str],
    max_new_tokens: int,
    batch_size: int = 8,
) -> List[str]:
    """Batched fine-tuned-model generation for the judge eval set.

    Pads to longest in the batch (left-padded for decoder-only generation)
    and falls back to per-prompt generation on CUDA OOM so a tight VRAM
    budget can't blank out the entire run.
    """
    import torch

    if batch_size <= 0:
        batch_size = 1

    if getattr(tokenizer, "pad_token", None) is None and getattr(tokenizer, "eos_token", None) is not None:
        tokenizer.pad_token = tokenizer.eos_token

    original_padding_side = getattr(tokenizer, "padding_side", "right")
    tokenizer.padding_side = "left"

    responses: List[str] = []
    try:
        for batch_start in range(0, len(prompts), batch_size):
            batch = prompts[batch_start : batch_start + batch_size]
            try:
                inputs = tokenizer(
                    batch,
                    return_tensors="pt",
                    truncation=True,
                    max_length=1024,
                    padding="longest",
                )
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                with torch.no_grad():
                    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
                prompt_len = inputs["input_ids"].shape[1]
                for row in outputs:
                    responses.append(tokenizer.decode(row[prompt_len:], skip_special_tokens=True))
            except torch.cuda.OutOfMemoryError as e:
                logger.warning(
                    "CUDA OOM on judge-generation batch of %d (start=%d). Falling back to single-prompt generation: %s",
                    len(batch),
                    batch_start,
                    e,
                )
                try:
                    torch.cuda.empty_cache()
                except RuntimeError:
                    pass
                for prompt in batch:
                    responses.append(_generate_response(model, tokenizer, prompt, max_new_tokens))
            except Exception as e:
                logger.warning(
                    "Judge-generation batch failed (start=%d, size=%d), retrying per-prompt: %s",
                    batch_start,
                    len(batch),
                    e,
                )
                for prompt in batch:
                    responses.append(_generate_response(model, tokenizer, prompt, max_new_tokens))
    finally:
        tokenizer.padding_side = original_padding_side

    return responses


def _clip_judge_score(raw_score: Optional[float]) -> Optional[float]:
    """Clip the judge's raw 1-10 score; pass through None for parse/transport failures.

    None preserves the failure signal so the caller can skip the sample in the
    average (rather than counting it as a 1.0 floor and pulling the score down).
    """
    if raw_score is None:
        return None
    score = max(1.0, min(10.0, raw_score))
    if raw_score != score:
        logger.warning(
            "Judge returned out-of-range score %.1f (expected 1-10), clipped to %.1f",
            raw_score,
            score,
        )
    return score


def _save_judge_results(
    output_dir: str,
    avg_score: float,
    min_score: float,
    passed: bool,
    num_prompts: int,
    details: List[Dict[str, Any]],
) -> None:
    """Persist the judge run summary as judge_results.json."""
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "judge_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "average_score": avg_score,
                "min_score": min_score,
                "passed": passed,
                "num_prompts": num_prompts,
                "details": details,
            },
            f,
            indent=2,
        )
    logger.info("Judge results saved to %s", results_path)


def run_judge_evaluation(
    model: Any,
    tokenizer: Any,
    eval_dataset_path: str,
    judge_model: str = "gpt-4o",
    judge_api_key: Optional[str] = None,
    rubric: Optional[str] = None,
    min_score: float = 5.0,
    max_new_tokens: int = 512,
    output_dir: Optional[str] = None,
    api_base: Optional[str] = None,
    # Phase 4 (closure F-performance-102) — batched fine-tuned-model generation
    batch_size: int = 8,
) -> JudgeResult:
    """Evaluate fine-tuned model outputs using an LLM judge.

    Args:
        model: The fine-tuned model to evaluate.
        tokenizer: Tokenizer for the model.
        eval_dataset_path: Path to JSONL with evaluation prompts.
        judge_model: Judge model name (API model or local path).
        judge_api_key: API key for API-based judges. None = use local model.
        rubric: Custom scoring rubric template. Uses default if None.
        min_score: Minimum average score to pass (1-10 scale).
        max_new_tokens: Max tokens for response generation.
        output_dir: Directory to save judge results.

    Returns:
        JudgeResult with scores and pass/fail status.
    """
    if not os.path.isfile(eval_dataset_path):
        logger.error("Judge eval dataset not found: %s", eval_dataset_path)
        return JudgeResult(passed=False, failure_reason=f"Eval dataset not found: {eval_dataset_path}")

    rubric = rubric or DEFAULT_RUBRIC
    eval_prompts = _load_eval_prompts(eval_dataset_path)
    if not eval_prompts:
        logger.warning("No eval prompts found. Skipping judge evaluation.")
        return JudgeResult(passed=True)

    logger.info("Running LLM-as-Judge evaluation with %d prompts (judge: %s)...", len(eval_prompts), judge_model)

    is_api_judge = judge_api_key is not None
    local_judge_model = None
    local_judge_tokenizer = None
    if not is_api_judge:
        try:
            local_judge_model, local_judge_tokenizer = _load_local_judge(judge_model)
        except Exception as e:
            logger.error("Failed to load local judge model: %s", e)
            return JudgeResult(passed=False, failure_reason=f"Judge model load failed: {e}")

    scores, details, failure_count = _score_eval_prompts(
        model=model,
        tokenizer=tokenizer,
        eval_prompts=eval_prompts,
        rubric=rubric,
        max_new_tokens=max_new_tokens,
        is_api_judge=is_api_judge,
        judge_api_key=judge_api_key,
        judge_model=judge_model,
        api_base=api_base,
        local_judge_model=local_judge_model,
        local_judge_tokenizer=local_judge_tokenizer,
        batch_size=batch_size,
    )

    avg_score, passed, failure_reason = _summarize_judge_scores(
        scores=scores,
        failure_count=failure_count,
        eval_prompts=eval_prompts,
        min_score=min_score,
    )

    if output_dir:
        _save_judge_results(output_dir, avg_score, min_score, passed, len(eval_prompts), details)

    return JudgeResult(
        average_score=avg_score,
        scores=scores,
        passed=passed,
        failure_reason=failure_reason,
        details=details,
    )


def _score_eval_prompts(
    *,
    model: Any,
    tokenizer: Any,
    eval_prompts: List[str],
    rubric: str,
    max_new_tokens: int,
    is_api_judge: bool,
    judge_api_key: Optional[str],
    judge_model: str,
    api_base: Optional[str],
    local_judge_model: Any,
    local_judge_tokenizer: Any,
    batch_size: int = 8,
) -> tuple[List[Optional[float]], List[Dict[str, Any]], int]:
    """Run each eval prompt through generation + judge, collect scores + details.

    Generation runs in batches of ``batch_size`` (closure F-performance-102) to
    amortize CUDA launch overhead across the eval set; the judge call is still
    per-prompt because the API path is rate-limited and the local-judge path
    typically uses a different model than the eval target.
    """
    scores: List[Optional[float]] = []
    details: List[Dict[str, Any]] = []
    failure_count = 0

    responses = _generate_responses_batched(model, tokenizer, eval_prompts, max_new_tokens, batch_size=batch_size)

    for prompt, response in zip(eval_prompts, responses):
        judge_prompt = rubric.format(prompt=prompt[:500], response=response[:1000])
        if is_api_judge:
            result = _call_api_judge(judge_prompt, judge_api_key, judge_model, api_base=api_base)
        else:
            result = _call_local_judge(judge_prompt, local_judge_model, local_judge_tokenizer)

        raw_score = result.get("score")
        score = _clip_judge_score(float(raw_score) if raw_score is not None else None)
        if score is None:
            failure_count += 1
        scores.append(score)
        details.append(
            {
                "prompt": prompt[:200],
                "response": response[:200],
                "score": score,
                "reason": result.get("reason", ""),
                "judge_failed": score is None,
            }
        )

    return scores, details, failure_count


def _summarize_judge_scores(
    *,
    scores: List[Optional[float]],
    failure_count: int,
    eval_prompts: List[str],
    min_score: float,
) -> tuple[float, bool, Optional[str]]:
    """Reduce per-prompt scores to (avg, passed, failure_reason).

    No valid scores → distinct failure mode. Treating it as "low average"
    would mislead the operator into thinking the model performed badly when
    the judge itself never produced a usable verdict.
    """
    valid_scores = [s for s in scores if s is not None]

    if not valid_scores:
        failure_reason = f"No valid judge scores (all {failure_count}/{len(eval_prompts)} parses/requests failed)."
        logger.error("JUDGE EVALUATION FAILED: %s", failure_reason)
        return 0.0, False, failure_reason

    avg_score = sum(valid_scores) / len(valid_scores)
    logger.info(
        "LLM-as-Judge average score: %.2f / 10.0 (%d/%d valid; %d judge failures)",
        avg_score,
        len(valid_scores),
        len(eval_prompts),
        failure_count,
    )
    if avg_score >= min_score:
        return avg_score, True, None

    failure_reason = f"Average judge score ({avg_score:.2f}) below minimum ({min_score:.2f})"
    logger.error("JUDGE EVALUATION FAILED: %s", failure_reason)
    return avg_score, False, failure_reason
