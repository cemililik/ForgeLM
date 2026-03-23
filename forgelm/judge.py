"""LLM-as-Judge evaluation pipeline.

Uses a strong LLM (API-based or local) to score fine-tuned model outputs
on quality, helpfulness, and instruction-following.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    scores: List[float] = field(default_factory=list)
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
    return {"score": 0, "reason": f"Invalid JSON response: {text[:200]}"}


def _call_api_judge(prompt: str, api_key: str, model: str = "gpt-4o", api_base: str = None) -> Dict[str, Any]:
    """Call an API-based judge (OpenAI-compatible endpoint)."""
    import requests

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
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_judge_json(content)
    except json.JSONDecodeError as e:
        logger.warning("API judge returned invalid JSON: %s", e)
        return {"score": 0, "reason": f"Invalid JSON from API: {e}"}
    except Exception as e:
        logger.warning("API judge call failed: %s", e)
        return {"score": 0, "reason": f"API error: {e}"}


def _call_local_judge(prompt: str, model: Any, tokenizer: Any) -> Dict[str, Any]:
    """Call a local model as judge."""
    import torch

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=200, do_sample=False)
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return _parse_judge_json(response)
    except Exception as e:
        logger.warning("Local judge evaluation failed: %s", e)
        return {"score": 0, "reason": f"Local judge error: {e}"}


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

    # Load eval prompts
    eval_prompts = []
    with open(eval_dataset_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    eval_prompts.append(data.get("prompt", data.get("text", "")))
                except json.JSONDecodeError:
                    eval_prompts.append(line)

    if not eval_prompts:
        logger.warning("No eval prompts found. Skipping judge evaluation.")
        return JudgeResult(passed=True)

    logger.info("Running LLM-as-Judge evaluation with %d prompts (judge: %s)...", len(eval_prompts), judge_model)

    # Generate responses from fine-tuned model
    scores = []
    details = []
    is_api_judge = judge_api_key is not None

    # Load local judge if needed
    local_judge_model = None
    local_judge_tokenizer = None
    if not is_api_judge:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            logger.info("Loading local judge model: %s", judge_model)
            local_judge_tokenizer = AutoTokenizer.from_pretrained(judge_model)
            local_judge_model = AutoModelForCausalLM.from_pretrained(judge_model, device_map="auto")
        except Exception as e:
            logger.error("Failed to load local judge model: %s", e)
            return JudgeResult(passed=False, failure_reason=f"Judge model load failed: {e}")

    for prompt in eval_prompts:
        # Generate response from fine-tuned model
        try:
            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            with __import__("torch").no_grad():
                outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        except Exception as e:
            logger.warning("Failed to generate response: %s", e)
            response = ""

        # Score with judge
        judge_prompt = rubric.format(prompt=prompt[:500], response=response[:1000])
        if is_api_judge:
            result = _call_api_judge(judge_prompt, judge_api_key, judge_model)
        else:
            result = _call_local_judge(judge_prompt, local_judge_model, local_judge_tokenizer)

        score = float(result.get("score", 0))
        scores.append(score)
        details.append({
            "prompt": prompt[:200],
            "response": response[:200],
            "score": score,
            "reason": result.get("reason", ""),
        })

    avg_score = sum(scores) / len(scores) if scores else 0.0
    logger.info("LLM-as-Judge average score: %.2f / 10.0", avg_score)

    passed = avg_score >= min_score
    failure_reason = None
    if not passed:
        failure_reason = f"Average judge score ({avg_score:.2f}) below minimum ({min_score:.2f})"
        logger.error("JUDGE EVALUATION FAILED: %s", failure_reason)

    # Save results
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        results_path = os.path.join(output_dir, "judge_results.json")
        with open(results_path, "w") as f:
            json.dump({
                "average_score": avg_score,
                "min_score": min_score,
                "passed": passed,
                "num_prompts": len(eval_prompts),
                "details": details,
            }, f, indent=2)
        logger.info("Judge results saved to %s", results_path)

    return JudgeResult(
        average_score=avg_score,
        scores=scores,
        passed=passed,
        failure_reason=failure_reason,
        details=details,
    )
