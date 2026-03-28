"""Synthetic data pipeline for teacher→student distillation.

Generates training data by prompting a teacher model (API or local) and
saving structured outputs as JSONL for downstream fine-tuning.

Usage:
    forgelm --config job.yaml --generate-data

Or programmatically:
    from forgelm.synthetic import SyntheticDataGenerator
    gen = SyntheticDataGenerator(config)
    gen.generate("output.jsonl")
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyntheticResult:
    """Result of a synthetic data generation run."""

    total_prompts: int = 0
    successful: int = 0
    failed: int = 0
    output_file: str = ""
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successful / self.total_prompts if self.total_prompts > 0 else 0.0


class SyntheticDataGenerator:
    """Generate synthetic training data using a teacher model.

    Supports three teacher backends:
    - "api": OpenAI-compatible API (GPT-4, Claude, local vLLM, etc.)
    - "local": Load a HuggingFace model locally for generation
    - "file": Read responses from a pre-existing file (for offline/reproducible pipelines)
    """

    def __init__(self, config):
        self.config = config
        self.synth_cfg = config.synthetic
        if not self.synth_cfg or not self.synth_cfg.enabled:
            raise ValueError("Synthetic data generation is not enabled in config.")
        self._teacher = None

    def generate(self, output_path: Optional[str] = None) -> SyntheticResult:
        """Generate synthetic data and save to JSONL.

        Args:
            output_path: Override output file path. If None, uses config value.

        Returns:
            SyntheticResult with generation statistics.
        """
        output_file = output_path or self.synth_cfg.output_file
        prompts = self._load_seed_prompts()
        result = SyntheticResult(total_prompts=len(prompts), output_file=output_file)

        if not prompts:
            logger.warning("No seed prompts found. Nothing to generate.")
            return result

        logger.info(
            "Starting synthetic data generation: %d prompts, teacher=%s, backend=%s",
            len(prompts),
            self.synth_cfg.teacher_model,
            self.synth_cfg.teacher_backend,
        )

        start_time = time.time()
        generated = []

        for i, prompt in enumerate(prompts):
            try:
                response = self._call_teacher(prompt)
                if response:
                    entry = self._format_entry(prompt, response)
                    generated.append(entry)
                    result.successful += 1
                else:
                    result.failed += 1
                    result.errors.append(f"Prompt {i}: empty response")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Prompt {i}: {e}")
                logger.warning("Generation failed for prompt %d: %s", i, e)

            # Rate limiting for API backends
            if self.synth_cfg.teacher_backend == "api" and self.synth_cfg.api_delay > 0:
                time.sleep(self.synth_cfg.api_delay)

        result.duration_seconds = time.time() - start_time

        # Write output
        if generated:
            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                for entry in generated:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(
                "Synthetic data saved: %s (%d entries, %.1f%% success rate)",
                output_file,
                len(generated),
                result.success_rate * 100,
            )
        else:
            logger.warning("No data generated. Output file not created.")

        return result

    def _load_seed_prompts(self) -> List[str]:
        """Load seed prompts from file or inline config."""
        # From file
        if self.synth_cfg.seed_file and os.path.isfile(self.synth_cfg.seed_file):
            prompts = []
            with open(self.synth_cfg.seed_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # Support JSONL ({"prompt": "..."}) or plain text
                    try:
                        data = json.loads(line)
                        prompts.append(data.get("prompt", data.get("text", line)))
                    except json.JSONDecodeError:
                        prompts.append(line)
            logger.info("Loaded %d seed prompts from %s", len(prompts), self.synth_cfg.seed_file)
            return prompts

        # From inline list
        if self.synth_cfg.seed_prompts:
            return list(self.synth_cfg.seed_prompts)

        logger.warning("No seed_file or seed_prompts configured.")
        return []

    def _call_teacher(self, prompt: str) -> str:
        """Route to the appropriate teacher backend."""
        backend = self.synth_cfg.teacher_backend

        if backend == "api":
            return self._call_api_teacher(prompt)
        elif backend == "local":
            return self._call_local_teacher(prompt)
        elif backend == "file":
            # File-based teacher — responses pre-loaded, keyed by prompt hash
            return self._call_file_teacher(prompt)
        else:
            raise ValueError(f"Unknown teacher_backend: {backend}")

    def _call_api_teacher(self, prompt: str) -> str:
        """Call an OpenAI-compatible API teacher."""
        import requests

        api_base = self.synth_cfg.api_base.rstrip("/")
        api_key = self.synth_cfg.api_key or os.environ.get(self.synth_cfg.api_key_env or "", "")

        if not api_base:
            raise ValueError("synthetic.api_base is required for API teacher backend.")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        system_prompt = self.synth_cfg.system_prompt or "You are a helpful assistant."

        payload = {
            "model": self.synth_cfg.teacher_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.synth_cfg.max_new_tokens,
            "temperature": self.synth_cfg.temperature,
        }

        response = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.synth_cfg.api_timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _call_local_teacher(self, prompt: str) -> str:
        """Generate with a locally loaded HuggingFace model."""
        if self._teacher is None:
            self._load_local_teacher()

        model, tokenizer = self._teacher
        system_prompt = self.synth_cfg.system_prompt or "You are a helpful assistant."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        if hasattr(tokenizer, "apply_chat_template"):
            formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            formatted = f"{system_prompt}\n\nUser: {prompt}\nAssistant:"

        inputs = tokenizer(formatted, return_tensors="pt")
        if hasattr(model, "device"):
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

        outputs = model.generate(
            **inputs,
            max_new_tokens=self.synth_cfg.max_new_tokens,
            temperature=self.synth_cfg.temperature,
            do_sample=self.synth_cfg.temperature > 0,
        )
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        return response.strip()

    def _load_local_teacher(self):
        """Lazy-load the local teacher model."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading local teacher model: %s", self.synth_cfg.teacher_model)
        tokenizer = AutoTokenizer.from_pretrained(self.synth_cfg.teacher_model)
        model = AutoModelForCausalLM.from_pretrained(
            self.synth_cfg.teacher_model,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        self._teacher = (model, tokenizer)

    def _call_file_teacher(self, prompt: str) -> str:
        """Read pre-generated responses from a file."""
        if self._teacher is None:
            # Load all responses into memory, keyed by prompt
            responses = {}
            if self.synth_cfg.seed_file and os.path.isfile(self.synth_cfg.seed_file):
                with open(self.synth_cfg.seed_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            p = data.get("prompt", "")
                            r = data.get("response", data.get("completion", data.get("output", "")))
                            if p and r:
                                responses[p] = r
                        except json.JSONDecodeError:
                            continue
            self._teacher = responses

        return self._teacher.get(prompt, "")

    def _format_entry(self, prompt: str, response: str) -> dict:
        """Format a prompt-response pair into the configured output format."""
        fmt = self.synth_cfg.output_format

        if fmt == "messages":
            entry = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response},
                ]
            }
            if self.synth_cfg.system_prompt:
                entry["messages"].insert(0, {"role": "system", "content": self.synth_cfg.system_prompt})
            return entry
        elif fmt == "instruction":
            return {"instruction": prompt, "output": response}
        elif fmt == "chatml":
            return {"User": prompt, "Assistant": response}
        else:
            # Default: simple prompt/response
            return {"prompt": prompt, "response": response}
