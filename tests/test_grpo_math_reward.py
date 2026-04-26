"""Unit tests for the built-in GRPO math reward helpers.

These cover the pure-Python regex / normalization layer in ``forgelm.trainer``:

- ``_normalize_answer`` — strips units, punctuation, whitespace
- ``_answers_match`` — exact-string + numeric-tolerance comparison
- ``_math_reward_fn`` — the TRL-shaped callable that scores GRPO completions
- ``_dataset_has_gold_answers`` — probe used by the trainer wiring

The tests intentionally avoid importing torch / trl: the functions under test
are pure Python and must remain so (so the trainer can pass them to TRL's
GRPOTrainer across worker processes without pickling extra state).
"""

from __future__ import annotations

import pytest

from forgelm.trainer import (
    _answers_match,
    _dataset_has_gold_answers,
    _math_reward_fn,
    _normalize_answer,
)

# ---------------------------------------------------------------------------
# _normalize_answer
# ---------------------------------------------------------------------------


class TestNormalizeAnswer:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("15", "15"),
            ("  15  ", "15"),
            ("$15", "15"),
            ("15.", "15"),
            ("15%", "15"),
            ("40 m²", "40"),
            ("70 km/h", "70"),
            ("2 m/s", "2"),
            ("1500 mL", "1500"),
            ("150 liters", "150"),
            ("10 hours", "10"),
            ("9 cm", "9"),
            ("45 kg", "45"),
            ("12:15", "12:15"),  # time format passed through
            ("2/5", "2/5"),  # fraction format passed through
        ],
    )
    def test_strips_units_and_punctuation(self, raw, expected):
        assert _normalize_answer(raw) == expected

    def test_handles_none(self):
        assert _normalize_answer(None) == ""

    def test_handles_empty(self):
        assert _normalize_answer("") == ""

    def test_strips_compound_unit_first(self):
        # km/h must be stripped before km — otherwise "70 km/h" would leave "/h".
        assert _normalize_answer("70 km/h") == "70"


# ---------------------------------------------------------------------------
# _answers_match
# ---------------------------------------------------------------------------


class TestAnswersMatch:
    def test_exact_string_match(self):
        assert _answers_match("12:15", "12:15") is True

    def test_fraction_string_match(self):
        assert _answers_match("2/5", "2/5") is True

    def test_numeric_tolerance(self):
        assert _answers_match("1.5", "1.5000001") is True

    def test_numeric_inequality(self):
        assert _answers_match("15", "16") is False

    def test_numeric_string_normalized(self):
        # "15.0" and "15" represent the same number.
        assert _answers_match("15.0", "15") is True

    def test_non_numeric_mismatch(self):
        assert _answers_match("12:15", "13:00") is False

    def test_extracted_number_matches_gold_string(self):
        assert _answers_match("40", "40") is True


# ---------------------------------------------------------------------------
# _math_reward_fn
# ---------------------------------------------------------------------------


class TestMathRewardFn:
    def test_correct_answer_scores_one(self):
        completions = ["Step 1: 12-3-2 = 7. Answer: 7"]
        rewards = _math_reward_fn(completions, gold_answer=["7"])
        assert rewards == [1.0]

    def test_wrong_answer_scores_zero(self):
        completions = ["Step 1: I think the answer is 8. Answer: 8"]
        rewards = _math_reward_fn(completions, gold_answer=["7"])
        assert rewards == [0.0]

    def test_answer_with_unit_matches(self):
        # "$15" should normalize to "15" and match gold "15".
        completions = ["Cost is base + km*rate = 3 + 12 = 15. Answer: $15"]
        rewards = _math_reward_fn(completions, gold_answer=["15"])
        assert rewards == [1.0]

    def test_fraction_answer_matches(self):
        completions = ["P = 4/(4+6) = 4/10. Answer: 2/5"]
        rewards = _math_reward_fn(completions, gold_answer=["2/5"])
        assert rewards == [1.0]

    def test_time_answer_matches(self):
        completions = ["9:30 + 2:45 = 12:15. Answer: 12:15"]
        rewards = _math_reward_fn(completions, gold_answer=["12:15"])
        assert rewards == [1.0]

    def test_float_tolerance_accepts_close_value(self):
        completions = ["Answer: 2.0000000001"]
        rewards = _math_reward_fn(completions, gold_answer=["2"])
        assert rewards == [1.0]

    def test_missing_answer_marker_scores_zero(self):
        # No "Answer:" prefix anywhere in the completion.
        completions = ["The result is seven."]
        rewards = _math_reward_fn(completions, gold_answer=["7"])
        assert rewards == [0.0]

    def test_case_insensitive_marker(self):
        completions = ["working...\nANSWER: 7"]
        rewards = _math_reward_fn(completions, gold_answer=["7"])
        assert rewards == [1.0]

    def test_multiple_completions(self):
        completions = ["Answer: 7", "Answer: 8", "no marker here"]
        rewards = _math_reward_fn(completions, gold_answer=["7", "8", "9"])
        assert rewards == [1.0, 1.0, 0.0]

    def test_empty_completion_scores_zero(self):
        rewards = _math_reward_fn([""], gold_answer=["7"])
        assert rewards == [0.0]

    def test_none_completion_scores_zero(self):
        # Defensive: a None slot in the batch must not crash the reward fn.
        rewards = _math_reward_fn([None], gold_answer=["7"])
        assert rewards == [0.0]

    def test_returns_floats(self):
        rewards = _math_reward_fn(["Answer: 7"], gold_answer=["7"])
        assert all(isinstance(r, float) for r in rewards)


# ---------------------------------------------------------------------------
# _dataset_has_gold_answers
# ---------------------------------------------------------------------------


class TestDatasetHasGoldAnswers:
    def test_dict_rows_with_gold_answer(self):
        ds = {"train": [{"prompt": "x", "gold_answer": "5"}]}
        assert _dataset_has_gold_answers(ds) is True

    def test_dict_rows_without_gold_answer(self):
        ds = {"train": [{"prompt": "x"}]}
        assert _dataset_has_gold_answers(ds) is False

    def test_empty_gold_answer_treated_as_missing(self):
        ds = {"train": [{"prompt": "x", "gold_answer": ""}]}
        assert _dataset_has_gold_answers(ds) is False

    def test_no_train_split(self):
        assert _dataset_has_gold_answers({}) is False

    def test_empty_train_split(self):
        assert _dataset_has_gold_answers({"train": []}) is False

    def test_non_dict_dataset(self):
        assert _dataset_has_gold_answers([]) is False

    def test_hf_dataset_via_column_names(self):
        # Simulate a HuggingFace Dataset that doesn't allow dict-style row
        # access but exposes column_names.
        class FakeHFDataset:
            def __init__(self, cols):
                self.column_names = cols

            def __len__(self):
                return 1

            def __getitem__(self, _):
                # Force the column_names code path.
                raise IndexError

        ds = {"train": FakeHFDataset(["prompt", "gold_answer"])}
        assert _dataset_has_gold_answers(ds) is True
