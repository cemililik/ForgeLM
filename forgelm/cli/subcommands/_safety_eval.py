"""``forgelm safety-eval`` — standalone safety evaluation subcommand.

Phase 36 closure of GH-005.  Wraps the existing
:func:`forgelm.safety.run_safety_evaluation` library function so an
operator can evaluate a fine-tuned model's safety profile without
having to wire it through a full training-config YAML.

Use cases:

- A pre-deployment safety check on a third-party model the operator
  is about to deploy.
- A post-incident re-evaluation of a previously-shipped model when
  the harm-classifier has been updated.
- A scheduled regression check in a release pipeline (the trainer
  pre-flight already covers training-time evaluation; this is the
  release-time counterpart).

Exit codes:

- 0 — evaluation completed; safety thresholds passed.
- 1 — evaluation completed but safety thresholds exceeded
  (operator-actionable; the model failed the gate).
- 2 — runtime error (model load failure, classifier load failure,
  probes file unreadable, missing optional dep).
"""

from __future__ import annotations

import json
import os
import sys
from typing import NoReturn

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# Path to the bundled default-probes file; resolved relative to this
# module so the file ships inside the wheel.
_DEFAULT_PROBES_RELPATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "safety_prompts",
    "default_probes.jsonl",
)


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> NoReturn:
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


def _resolve_probes_path(args, output_format: str) -> str:
    """Pick the probes file: explicit ``--probes`` > ``--default-probes`` flag."""
    explicit = getattr(args, "probes", None)
    use_default = getattr(args, "default_probes", False)
    if explicit and use_default:
        _output_error_and_exit(
            output_format,
            "--probes and --default-probes are mutually exclusive.",
            EXIT_CONFIG_ERROR,
        )
    if explicit:
        if not os.path.isfile(explicit):
            _output_error_and_exit(
                output_format,
                f"Probes file not found: {explicit!r}.",
                EXIT_CONFIG_ERROR,
            )
        return explicit
    if use_default:
        if not os.path.isfile(_DEFAULT_PROBES_RELPATH):
            _output_error_and_exit(
                output_format,
                f"Bundled default probes file is missing: {_DEFAULT_PROBES_RELPATH!r}.  "
                "Reinstall the package or supply --probes <path>.",
                EXIT_TRAINING_ERROR,
            )
        return _DEFAULT_PROBES_RELPATH
    _output_error_and_exit(
        output_format,
        "One of --probes <jsonl> or --default-probes is required.",
        EXIT_CONFIG_ERROR,
    )


def _load_model_for_safety(model_path: str, output_format: str):
    """Load the model + tokenizer for evaluation.

    Routes through the existing :mod:`forgelm.model` loader for
    ``.safetensors`` / HF Hub paths and through :mod:`forgelm.inference`
    for ``.gguf`` (the standalone subcommand mirrors what training-time
    safety evaluation does).
    """
    if model_path.endswith(".gguf"):
        try:
            from forgelm.inference import load_gguf_model
        except ImportError as exc:
            _output_error_and_exit(
                output_format,
                f"GGUF backend unavailable; install with: pip install 'forgelm[export]'.  ImportError: {exc}",
                EXIT_CONFIG_ERROR,
            )
        try:
            return load_gguf_model(model_path)
        except Exception as exc:  # noqa: BLE001 — best-effort: GGUF loaders surface a wide failure surface (file truncation, magic mismatch, llama-cpp-python missing).
            _output_error_and_exit(
                output_format,
                f"Failed to load GGUF model {model_path!r}: {exc}",
                EXIT_TRAINING_ERROR,
            )

    # Default path: HF / local-checkpoint loader.  We use the underlying
    # transformers loaders directly because in standalone mode we do
    # not have a full ForgeConfig with which to drive
    # :func:`forgelm.model.get_model_and_tokenizer`.
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForCausalLM.from_pretrained(model_path)
        return model, tokenizer
    except ImportError as exc:
        _output_error_and_exit(
            output_format,
            f"transformers is required for safety-eval; install with: pip install forgelm.  ImportError: {exc}",
            EXIT_CONFIG_ERROR,
        )
    except Exception as exc:  # noqa: BLE001 — broad surface from HF loaders (FileNotFoundError, OSError, ValueError, KeyError, etc.).
        _output_error_and_exit(
            output_format,
            f"Failed to load model {model_path!r}: {exc}",
            EXIT_TRAINING_ERROR,
        )


def _run_safety_eval_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm safety-eval``."""
    model_path = getattr(args, "model", None)
    if not model_path:
        _output_error_and_exit(
            output_format,
            "safety-eval requires --model <path-or-hub-id>.",
            EXIT_CONFIG_ERROR,
        )

    classifier_path = getattr(args, "classifier", None) or "meta-llama/Llama-Guard-3-8B"
    probes_path = _resolve_probes_path(args, output_format)
    output_dir = getattr(args, "output_dir", None) or os.getcwd()
    max_new_tokens = int(getattr(args, "max_new_tokens", 512) or 512)

    try:
        from forgelm.safety import run_safety_evaluation
    except ImportError as exc:
        _output_error_and_exit(
            output_format,
            f"forgelm.safety unavailable; this should never happen on a healthy install.  ImportError: {exc}",
            EXIT_TRAINING_ERROR,
        )

    model, tokenizer = _load_model_for_safety(model_path, output_format)

    try:
        result = run_safety_evaluation(
            model=model,
            tokenizer=tokenizer,
            classifier_path=classifier_path,
            test_prompts_path=probes_path,
            max_new_tokens=max_new_tokens,
            output_dir=output_dir,
        )
    except Exception as exc:  # noqa: BLE001 — broad surface: classifier load failure, OOM, generation crash all funnel into one operator-facing failure path.
        _output_error_and_exit(
            output_format,
            f"safety-eval crashed during evaluation: {exc.__class__.__name__}: {exc}",
            EXIT_TRAINING_ERROR,
        )

    # ``forgelm.safety.SafetyResult`` exposes the per-category breakdown
    # under ``category_distribution`` (an Optional[Dict[str, int]] that
    # is None when the operator did not opt into ``track_categories``).
    # The earlier ``harm_categories`` field name was wrong — getattr
    # would silently fall back to ``{}`` and the rendered output would
    # always be empty even on a populated run.
    payload = {
        "model": model_path,
        "classifier": classifier_path,
        "probes": probes_path,
        "output_dir": output_dir,
        "passed": getattr(result, "passed", False),
        "safety_score": getattr(result, "safety_score", None),
        "safe_ratio": getattr(result, "safe_ratio", None),
        "category_distribution": dict(getattr(result, "category_distribution", None) or {}),
        "failure_reason": getattr(result, "failure_reason", None),
    }
    if output_format == "json":
        print(json.dumps({"success": payload["passed"], **payload}, indent=2, default=str))
    else:
        marker = "PASS" if payload["passed"] else "FAIL"
        print(f"{marker}: safety-eval against {model_path}")
        print(f"  safety_score = {payload['safety_score']}")
        print(f"  safe_ratio   = {payload['safe_ratio']}")
        if payload["category_distribution"]:
            print("  category_distribution:")
            for cat, count in sorted(payload["category_distribution"].items()):
                print(f"    {cat}: {count}")
        if payload["failure_reason"]:
            print(f"  failure_reason = {payload['failure_reason']}")
    sys.exit(EXIT_SUCCESS if payload["passed"] else EXIT_CONFIG_ERROR)


__all__ = [
    "_run_safety_eval_cmd",
    "_resolve_probes_path",
    "_DEFAULT_PROBES_RELPATH",
]
