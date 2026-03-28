"""Tests for synthetic data generation pipeline."""

import json
import os

import pytest

from forgelm.config import ForgeConfig, load_config
from forgelm.synthetic import SyntheticDataGenerator, SyntheticResult

BASE = {
    "model": {"name_or_path": "test/model"},
    "lora": {"r": 16, "alpha": 32},
    "data": {"dataset_name_or_path": "test.jsonl"},
    "training": {"output_dir": "./out"},
}


def _config(**overrides):
    cfg = {**BASE}
    for key, val in overrides.items():
        cfg[key] = val
    return ForgeConfig(**cfg)


class TestSyntheticConfig:
    def test_disabled_by_default(self):
        config = _config()
        assert config.synthetic is None

    def test_enabled_config(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "gpt-4",
                "teacher_backend": "api",
                "api_base": "https://api.openai.com/v1",
                "seed_prompts": ["What is AI?", "Explain ML."],
            }
        )
        assert config.synthetic.enabled is True
        assert config.synthetic.teacher_model == "gpt-4"
        assert config.synthetic.teacher_backend == "api"
        assert len(config.synthetic.seed_prompts) == 2

    def test_defaults(self):
        config = _config(synthetic={"enabled": True, "teacher_model": "gpt-4"})
        assert config.synthetic.temperature == 0.7
        assert config.synthetic.max_new_tokens == 1024
        assert config.synthetic.output_format == "messages"
        assert config.synthetic.api_delay == 0.5
        assert config.synthetic.api_timeout == 60
        assert config.synthetic.output_file == "synthetic_data.jsonl"

    def test_local_backend(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "meta-llama/Llama-3-8B",
                "teacher_backend": "local",
            }
        )
        assert config.synthetic.teacher_backend == "local"

    def test_file_backend(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "n/a",
                "teacher_backend": "file",
                "seed_file": "responses.jsonl",
            }
        )
        assert config.synthetic.teacher_backend == "file"


class TestSyntheticResult:
    def test_success_rate_zero(self):
        r = SyntheticResult(total_prompts=0)
        assert r.success_rate == 0.0

    def test_success_rate_partial(self):
        r = SyntheticResult(total_prompts=10, successful=7, failed=3)
        assert r.success_rate == 0.7

    def test_success_rate_full(self):
        r = SyntheticResult(total_prompts=5, successful=5, failed=0)
        assert r.success_rate == 1.0


class TestSyntheticGenerator:
    def test_raises_if_not_enabled(self):
        config = _config()
        with pytest.raises(ValueError, match="not enabled"):
            SyntheticDataGenerator(config)

    def test_load_seed_prompts_inline(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "seed_prompts": ["prompt1", "prompt2", "prompt3"],
            }
        )
        gen = SyntheticDataGenerator(config)
        prompts = gen._load_seed_prompts()
        assert prompts == ["prompt1", "prompt2", "prompt3"]

    def test_load_seed_prompts_from_text_file(self, tmp_path):
        seed_file = tmp_path / "seeds.txt"
        seed_file.write_text("What is Python?\nExplain recursion.\n\nHow does TCP work?\n")

        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "seed_file": str(seed_file),
            }
        )
        gen = SyntheticDataGenerator(config)
        prompts = gen._load_seed_prompts()
        assert len(prompts) == 3
        assert "What is Python?" in prompts

    def test_load_seed_prompts_from_jsonl(self, tmp_path):
        seed_file = tmp_path / "seeds.jsonl"
        lines = [
            json.dumps({"prompt": "What is AI?"}),
            json.dumps({"prompt": "Explain ML."}),
        ]
        seed_file.write_text("\n".join(lines))

        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "seed_file": str(seed_file),
            }
        )
        gen = SyntheticDataGenerator(config)
        prompts = gen._load_seed_prompts()
        assert len(prompts) == 2
        assert prompts[0] == "What is AI?"

    def test_format_entry_messages(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "output_format": "messages",
                "system_prompt": "Be helpful.",
            }
        )
        gen = SyntheticDataGenerator(config)
        entry = gen._format_entry("What is AI?", "AI is artificial intelligence.")
        assert "messages" in entry
        assert len(entry["messages"]) == 3  # system + user + assistant
        assert entry["messages"][0]["role"] == "system"
        assert entry["messages"][1]["content"] == "What is AI?"
        assert entry["messages"][2]["content"] == "AI is artificial intelligence."

    def test_format_entry_instruction(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "output_format": "instruction",
            }
        )
        gen = SyntheticDataGenerator(config)
        entry = gen._format_entry("What is AI?", "AI is artificial intelligence.")
        assert entry == {"instruction": "What is AI?", "output": "AI is artificial intelligence."}

    def test_format_entry_chatml(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "output_format": "chatml",
            }
        )
        gen = SyntheticDataGenerator(config)
        entry = gen._format_entry("Q?", "A.")
        assert entry == {"User": "Q?", "Assistant": "A."}

    def test_file_backend_generate(self, tmp_path):
        """Test file-based teacher (pre-generated responses)."""
        seed_file = tmp_path / "seeds.jsonl"
        lines = [
            json.dumps({"prompt": "What is AI?", "response": "AI is artificial intelligence."}),
            json.dumps({"prompt": "What is ML?", "response": "ML is machine learning."}),
        ]
        seed_file.write_text("\n".join(lines))

        output_file = tmp_path / "output.jsonl"
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "n/a",
                "teacher_backend": "file",
                "seed_file": str(seed_file),
                "output_file": str(output_file),
                "output_format": "instruction",
            }
        )

        gen = SyntheticDataGenerator(config)
        result = gen.generate()

        assert result.total_prompts == 2
        assert result.successful == 2
        assert result.failed == 0
        assert os.path.isfile(str(output_file))

        with open(str(output_file)) as f:
            entries = [json.loads(line) for line in f]
        assert len(entries) == 2
        assert entries[0]["instruction"] == "What is AI?"
        assert entries[0]["output"] == "AI is artificial intelligence."

    def test_empty_prompts_no_crash(self):
        config = _config(
            synthetic={
                "enabled": True,
                "teacher_model": "test",
                "seed_prompts": [],
            }
        )
        gen = SyntheticDataGenerator(config)
        result = gen.generate()
        assert result.total_prompts == 0
        assert result.successful == 0


class TestSyntheticYaml:
    def test_yaml_round_trip(self, tmp_path):
        yaml_content = """
model:
  name_or_path: "test/model"
lora:
  r: 16
  alpha: 32
data:
  dataset_name_or_path: "test.jsonl"
training:
  output_dir: "./out"
synthetic:
  enabled: true
  teacher_model: "gpt-4o"
  teacher_backend: "api"
  api_base: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  temperature: 0.5
  output_format: "messages"
"""
        config_file = tmp_path / "synth.yaml"
        config_file.write_text(yaml_content)
        config = load_config(str(config_file))

        assert config.synthetic.enabled is True
        assert config.synthetic.teacher_model == "gpt-4o"
        assert config.synthetic.temperature == 0.5

    def test_config_template_still_valid(self):
        config = load_config("config_template.yaml")
        assert config.synthetic is None
