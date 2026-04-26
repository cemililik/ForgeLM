"""Tests for the BYOD (bring-your-own-data) input loop in ``wizard.py``.

Covers the path-validation block in ``_maybe_run_quickstart_template``:
nonexistent paths, directories, malformed JSONL, valid JSONL, HF Hub dataset
IDs, and ``~`` expansion. These are unit tests — no subprocess, no GPU,
no network. ``input()`` is stubbed via ``builtins.input`` patching, and
``run_quickstart`` is patched to keep the tests hermetic.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from forgelm import wizard


def _make_input(answers):
    """Return a side_effect callable that returns each answer in order."""
    answers = list(answers)

    def _impl(_prompt_text=""):
        if not answers:
            raise AssertionError("input() called more times than answers provided")
        return answers.pop(0)

    return _impl


# Inputs we feed to the wizard before the BYOD prompt:
#   1. "y" — accept the quickstart-template offer
#   2. "domain-expert" — pick the BYOD template
# After that the BYOD loop consumes its own answers.
_PRELUDE = ["y", "domain-expert"]


def test_byod_rejects_nonexistent_path(capsys):
    answers = _PRELUDE + ["/no/such/file.jsonl", "cancel"]
    with patch("builtins.input", side_effect=_make_input(answers)):
        result = wizard._maybe_run_quickstart_template()
    assert result is None
    captured = capsys.readouterr().out
    assert "Path not found or not a regular file: /no/such/file.jsonl" in captured


def test_byod_rejects_directory(tmp_path, capsys):
    # tmp_path itself is a directory — the BYOD loop must reject it AND hint
    # at the Phase 11 ingestion pipeline (forgelm ingest) since a directory
    # of raw docs is the most plausible reason a user landed here.
    answers = _PRELUDE + [str(tmp_path), "cancel"]
    with patch("builtins.input", side_effect=_make_input(answers)):
        result = wizard._maybe_run_quickstart_template()
    assert result is None
    captured = capsys.readouterr().out
    assert "is a directory, not a JSONL file" in captured
    assert "forgelm ingest" in captured


def test_byod_rejects_malformed_jsonl(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{bad json\n", encoding="utf-8")
    answers = _PRELUDE + [str(bad), "cancel"]
    with patch("builtins.input", side_effect=_make_input(answers)):
        result = wizard._maybe_run_quickstart_template()
    assert result is None
    captured = capsys.readouterr().out
    assert "not valid JSONL" in captured


def test_byod_accepts_valid_jsonl(tmp_path):
    good = tmp_path / "good.jsonl"
    good.write_text('{"messages":[]}\n', encoding="utf-8")
    answers = _PRELUDE + [str(good)]

    fake_result = type(
        "R",
        (),
        {
            "config_path": tmp_path / "generated.yaml",
            "chosen_model": "test-model",
            "selection_reason": "test",
            "dataset_path": str(good),
        },
    )()

    with (
        patch("builtins.input", side_effect=_make_input(answers)),
        patch("forgelm.quickstart.run_quickstart", return_value=fake_result) as mock_run,
    ):
        result = wizard._maybe_run_quickstart_template()

    assert result == str(tmp_path / "generated.yaml")
    mock_run.assert_called_once()
    # The dataset_override should be the resolved absolute path.
    _args, kwargs = mock_run.call_args
    assert kwargs["dataset_override"] == str(good)


def test_byod_accepts_hf_hub_id(tmp_path, capsys):
    hub_id = "tatsu-lab/alpaca"
    answers = _PRELUDE + [hub_id]

    fake_result = type(
        "R",
        (),
        {
            "config_path": tmp_path / "generated.yaml",
            "chosen_model": "test-model",
            "selection_reason": "test",
            "dataset_path": hub_id,
        },
    )()

    with (
        patch("builtins.input", side_effect=_make_input(answers)),
        patch("forgelm.quickstart.run_quickstart", return_value=fake_result) as mock_run,
    ):
        result = wizard._maybe_run_quickstart_template()

    assert result == str(tmp_path / "generated.yaml")
    captured = capsys.readouterr().out
    assert f"Treating '{hub_id}' as an HF Hub dataset ID" in captured
    # The HF ID must be passed through unchanged — not turned into a Path.
    _args, kwargs = mock_run.call_args
    assert kwargs["dataset_override"] == hub_id


def test_byod_expands_user_home(tmp_path, monkeypatch):
    good = tmp_path / "data.jsonl"
    good.write_text('{"messages":[]}\n', encoding="utf-8")

    # Pretend the user's home is tmp_path so "~/data.jsonl" expands to our file.
    monkeypatch.setenv("HOME", str(tmp_path))
    # On POSIX Path.expanduser() reads $HOME; setting it is enough.

    typed = "~/data.jsonl"
    answers = _PRELUDE + [typed]

    fake_result = type(
        "R",
        (),
        {
            "config_path": tmp_path / "generated.yaml",
            "chosen_model": "test-model",
            "selection_reason": "test",
            "dataset_path": str(good),
        },
    )()

    with (
        patch("builtins.input", side_effect=_make_input(answers)),
        patch("forgelm.quickstart.run_quickstart", return_value=fake_result) as mock_run,
    ):
        result = wizard._maybe_run_quickstart_template()

    assert result == str(tmp_path / "generated.yaml")
    _args, kwargs = mock_run.call_args
    # The override must be the expanded absolute path, not the literal "~/...".
    # _validate_local_jsonl applies .resolve() after .expanduser(), so on
    # macOS where /tmp is a symlink to /private/tmp the override may carry
    # the canonical form — compare via Path equality instead of string match.
    expanded = Path(typed).expanduser().resolve()
    assert Path(kwargs["dataset_override"]) == expanded
    # And it should resolve to our actual tmp file.
    assert Path(kwargs["dataset_override"]).is_file()


def test_byod_relative_local_path_not_misclassified_as_hub_id(tmp_path, monkeypatch, capsys):
    """``data/train.jsonl`` matches the HF Hub regex shape but is a local file.

    Regression: an earlier version of the loop tested the HF Hub regex
    *before* the local-file probe, so a relative path that happened to look
    like ``<org>/<name>`` (single slash, safe-name char class) silently
    became a Hub ID and bypassed JSONL validation. The fixed loop tries
    local first, falls back to Hub semantics only when the path is missing.
    """
    nested = tmp_path / "data"
    nested.mkdir()
    real_file = nested / "train.jsonl"
    real_file.write_text('{"messages":[]}\n', encoding="utf-8")

    monkeypatch.chdir(tmp_path)  # so "data/train.jsonl" resolves under tmp_path

    typed = "data/train.jsonl"
    answers = _PRELUDE + [typed]

    fake_result = type(
        "R",
        (),
        {
            "config_path": tmp_path / "generated.yaml",
            "chosen_model": "test-model",
            "selection_reason": "test",
            "dataset_path": str(real_file),
        },
    )()

    with (
        patch("builtins.input", side_effect=_make_input(answers)),
        patch("forgelm.quickstart.run_quickstart", return_value=fake_result) as mock_run,
    ):
        result = wizard._maybe_run_quickstart_template()

    assert result == str(tmp_path / "generated.yaml")
    captured = capsys.readouterr().out
    # Must NOT have been treated as an HF Hub ID.
    assert "Treating" not in captured, "relative local path was misclassified as a Hub ID"

    _args, kwargs = mock_run.call_args
    # The override must point to the actual on-disk file, expanded to absolute.
    assert Path(kwargs["dataset_override"]) == real_file.resolve()
