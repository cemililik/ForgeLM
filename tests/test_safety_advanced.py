"""Unit tests for Phase 9: Advanced safety scoring features."""

import json
import os

from forgelm.config import SafetyConfig
from forgelm.safety import (
    CATEGORY_SEVERITY,
    HARM_CATEGORIES,
    SafetyResult,
    _append_trend_entry,
    _extract_category,
)


class TestSafetyConfigPhase9:
    def test_default_scoring_binary(self):
        s = SafetyConfig(enabled=True)
        assert s.scoring == "binary"
        assert s.min_safety_score is None
        assert s.min_classifier_confidence == 0.7
        assert s.track_categories is False
        assert s.severity_thresholds is None

    def test_confidence_weighted_config(self):
        s = SafetyConfig(
            enabled=True,
            scoring="confidence_weighted",
            min_safety_score=0.85,
            min_classifier_confidence=0.6,
        )
        assert s.scoring == "confidence_weighted"
        assert s.min_safety_score == 0.85

    def test_category_tracking_config(self):
        s = SafetyConfig(
            enabled=True,
            track_categories=True,
            severity_thresholds={"critical": 0, "high": 0.01, "medium": 0.05},
        )
        assert s.track_categories is True
        assert s.severity_thresholds["critical"] == 0

    def test_full_config_yaml(self, tmp_path):
        import yaml

        from forgelm.config import load_config

        data = {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {},
            "data": {"dataset_name_or_path": "org/dataset"},
            "evaluation": {
                "safety": {
                    "enabled": True,
                    "scoring": "confidence_weighted",
                    "min_safety_score": 0.9,
                    "track_categories": True,
                    "severity_thresholds": {"critical": 0, "high": 0.01},
                }
            },
        }
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.evaluation.safety.scoring == "confidence_weighted"
        assert cfg.evaluation.safety.severity_thresholds["critical"] == 0


class TestSafetyResultPhase9:
    def test_result_with_confidence(self):
        r = SafetyResult(
            safe_ratio=0.95,
            safety_score=0.92,
            low_confidence_count=3,
            category_distribution={"violent_crimes": 1, "hate": 2},
            severity_distribution={"critical": 1, "high": 2},
        )
        assert r.safety_score == 0.92
        assert r.low_confidence_count == 3
        assert r.category_distribution["hate"] == 2
        assert r.severity_distribution["critical"] == 1

    def test_result_defaults(self):
        r = SafetyResult()
        assert r.safety_score is None
        assert r.low_confidence_count == 0
        assert r.category_distribution is None


class TestExtractCategory:
    def test_llama_guard_format(self):
        assert _extract_category("unsafe\nS1") == "S1"
        assert _extract_category("unsafe S5") == "S5"
        assert _extract_category("unsafe\nS14") == "S14"

    def test_safe_label(self):
        assert _extract_category("safe") is None

    def test_unknown_format(self):
        assert _extract_category("harmful") is None

    def test_case_insensitive(self):
        assert _extract_category("UNSAFE\ns7") == "S7"


class TestHarmCategories:
    def test_all_categories_have_severity(self):
        for code in HARM_CATEGORIES:
            assert code in CATEGORY_SEVERITY, f"Missing severity for {code}"

    def test_critical_categories(self):
        critical = [k for k, v in CATEGORY_SEVERITY.items() if v == "critical"]
        assert "S1" in critical  # violent crimes
        assert "S4" in critical  # child exploitation
        assert "S9" in critical  # weapons

    def test_category_count(self):
        assert len(HARM_CATEGORIES) == 14


class TestTrendTracking:
    def test_append_creates_file(self, tmp_path):
        _append_trend_entry(str(tmp_path), 0.95, 0.97, True)
        trend_path = os.path.join(str(tmp_path), "safety_trend.jsonl")
        assert os.path.isfile(trend_path)
        with open(trend_path) as f:
            entry = json.loads(f.readline())
        assert entry["safety_score"] == 0.95
        assert entry["passed"] is True

    def test_append_multiple(self, tmp_path):
        _append_trend_entry(str(tmp_path), 0.95, 0.97, True)
        _append_trend_entry(str(tmp_path), 0.92, 0.94, True)
        _append_trend_entry(str(tmp_path), 0.88, 0.90, False)
        trend_path = os.path.join(str(tmp_path), "safety_trend.jsonl")
        with open(trend_path) as f:
            entries = [json.loads(line) for line in f]
        assert len(entries) == 3
        assert entries[0]["safety_score"] == 0.95
        assert entries[2]["passed"] is False

    def test_trend_has_timestamps(self, tmp_path):
        _append_trend_entry(str(tmp_path), 0.95, 0.97, True)
        trend_path = os.path.join(str(tmp_path), "safety_trend.jsonl")
        with open(trend_path) as f:
            entry = json.loads(f.readline())
        assert "timestamp" in entry


class TestBuiltInPromptLibrary:
    def test_general_safety_prompts_exist(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "safety_prompts", "general_safety.jsonl")
        assert os.path.isfile(path)
        with open(path) as f:
            prompts = [json.loads(line) for line in f]
        assert len(prompts) >= 15
        assert all("prompt" in p for p in prompts)

    def test_bias_discrimination_prompts_exist(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "safety_prompts", "bias_discrimination.jsonl")
        assert os.path.isfile(path)
        with open(path) as f:
            prompts = [json.loads(line) for line in f]
        assert len(prompts) >= 10

    def test_jailbreak_prompts_exist(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "safety_prompts", "jailbreak_attempts.jsonl")
        assert os.path.isfile(path)
        with open(path) as f:
            prompts = [json.loads(line) for line in f]
        assert len(prompts) >= 10

    def test_all_prompts_valid_jsonl(self):
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "configs", "safety_prompts")
        for filename in os.listdir(prompts_dir):
            if filename.endswith(".jsonl"):
                with open(os.path.join(prompts_dir, filename)) as f:
                    for i, line in enumerate(f):
                        data = json.loads(line)
                        assert "prompt" in data, f"{filename} line {i + 1}: missing 'prompt' key"
