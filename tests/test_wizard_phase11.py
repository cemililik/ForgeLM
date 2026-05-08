"""Phase 11: ``_print`` indirection + wizard output coverage.

These tests pin the contract of :func:`forgelm.wizard._print` (mirror of
:func:`forgelm.chat.ChatSession._print`) and exercise the wizard's
output-emitting code paths through ``capsys`` so the module is no longer
exempt from the project's coverage floor. Closes F-code-105 / F-test-003.

No GPU / no network — every test stubs ``builtins.input`` for stdin reads
and (where needed) patches ``forgelm.quickstart.run_quickstart`` to keep
the side effects hermetic.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from forgelm import wizard

# ---------------------------------------------------------------------------
# _print indirection contract
# ---------------------------------------------------------------------------


class TestPrintIndirection:
    def test_print_writes_to_stdout(self, capsys):
        wizard._print("hello world")
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"
        assert captured.err == ""

    def test_print_accepts_multiple_positional_args(self, capsys):
        # Mirrors the builtin ``print`` calling convention so call sites
        # like ``_print("a", "b")`` keep working without a wrapper.
        wizard._print("a", "b", "c")
        assert capsys.readouterr().out == "a b c\n"

    def test_print_accepts_end_kwarg(self, capsys):
        # The wizard does not currently use ``end=``, but the indirection
        # must not silently drop ``print``'s kwargs — coding standard
        # forbids "looks-like-print but quietly different" wrappers.
        wizard._print("inline", end="")
        wizard._print("done")
        assert capsys.readouterr().out == "inlinedone\n"

    def test_print_accepts_sep_kwarg(self, capsys):
        wizard._print("a", "b", sep="-")
        assert capsys.readouterr().out == "a-b\n"

    def test_print_no_args_emits_blank_line(self, capsys):
        # ``print()`` with no args produces a single newline; the wizard
        # uses this idiom (e.g., the summary spacer) so it must round-trip.
        wizard._print()
        assert capsys.readouterr().out == "\n"


# ---------------------------------------------------------------------------
# Welcome banner / quickstart entry output
# ---------------------------------------------------------------------------


def _input_returning(*answers):
    """Build a side_effect for ``builtins.input`` that drains *answers*."""
    queue = list(answers)

    def _impl(_prompt_text=""):
        if not queue:
            raise AssertionError("input() called more times than answers provided")
        return queue.pop(0)

    return _impl


class TestWizardEntryOutput:
    def test_welcome_banner_printed(self, capsys):
        # Decline the quickstart offer — we only care that the banner
        # itself reached stdout. ``_maybe_run_quickstart_template`` short-
        # circuits to ``None`` before reaching any further interactive
        # prompts.
        with patch("builtins.input", side_effect=_input_returning("n")):
            result = wizard._maybe_run_quickstart_template()
        assert result is None
        captured = capsys.readouterr().out
        assert "ForgeLM Configuration Wizard" in captured
        # The 60-char rule line frames the banner; pin it so accidental
        # truncation at the seam is caught.
        assert "=" * 60 in captured

    def test_quickstart_template_listing_printed(self, capsys):
        # Accept the quickstart offer, then cancel out of the BYOD prompt
        # (the curated quickstart catalogue includes BYOD templates that
        # require a dataset path — "cancel" returns us cleanly to the
        # caller without spawning training).
        with patch(
            "builtins.input",
            side_effect=_input_returning("y", "domain-expert", "cancel"),
        ):
            result = wizard._maybe_run_quickstart_template()
        assert result is None
        captured = capsys.readouterr().out
        assert "Available templates:" in captured
        # Each template line carries a "[x] data" / "[ ] BYOD" badge —
        # the BYOD marker confirms the listing rendered the iteration body.
        assert "BYOD" in captured

    def test_byod_path_not_found_message_printed(self, capsys):
        with patch(
            "builtins.input",
            side_effect=_input_returning(
                "y",  # accept quickstart offer
                "domain-expert",  # pick a BYOD template
                "/definitely/not/here.jsonl",  # bogus path
                "cancel",  # bail out
            ),
        ):
            result = wizard._maybe_run_quickstart_template()
        assert result is None
        captured = capsys.readouterr().out
        assert "Path not found or not a regular file" in captured

    def test_unparseable_template_choice_falls_through(self, capsys):
        # Typing a non-numeric, non-template-name string at the picker
        # surfaces an explanatory message and returns None. Pinning the
        # exact "Could not interpret" prefix protects users that grep
        # logs for the failure mode.
        with patch(
            "builtins.input",
            side_effect=_input_returning("y", "not-a-real-template"),
        ):
            result = wizard._maybe_run_quickstart_template()
        assert result is None
        captured = capsys.readouterr().out
        assert "Could not interpret" in captured


# ---------------------------------------------------------------------------
# BYOD path + audit-skip messaging
# ---------------------------------------------------------------------------


class TestWizardByodOutput:
    def test_byod_hub_id_treatment_printed(self, capsys, tmp_path):
        hub_id = "tatsu-lab/alpaca"

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
            patch(
                "builtins.input",
                side_effect=_input_returning("y", "domain-expert", hub_id),
            ),
            patch("forgelm.quickstart.run_quickstart", return_value=fake_result),
        ):
            wizard._maybe_run_quickstart_template()

        captured = capsys.readouterr().out
        assert f"Treating '{hub_id}' as an HF Hub dataset ID" in captured

    def test_byod_audit_skip_hint_printed(self, tmp_path, capsys):
        # When the user declines the post-validation audit offer, the
        # wizard prints a "Skipped" hint pointing at the manual ``forgelm
        # audit`` command. That hint is the only signal a CI log gives
        # operators that they could have audited — pin it.
        good = tmp_path / "good.jsonl"
        good.write_text('{"messages": []}\n', encoding="utf-8")

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
            patch(
                "builtins.input",
                side_effect=_input_returning(
                    "y",  # accept quickstart offer
                    "domain-expert",  # pick BYOD template
                    str(good),  # validated JSONL
                    "n",  # decline the audit offer
                ),
            ),
            patch("forgelm.quickstart.run_quickstart", return_value=fake_result),
        ):
            wizard._maybe_run_quickstart_template()

        captured = capsys.readouterr().out
        assert "Skipped — audit can be run later via:" in captured
        assert f"forgelm audit {good}" in captured


# ---------------------------------------------------------------------------
# Validation helpers — lightweight, exercised directly
# ---------------------------------------------------------------------------


class TestValidationHelpersOutput:
    def test_validate_local_jsonl_missing_path_returns_sentinel(self):
        # Sanity check that _validate_local_jsonl uses _BYOD_LOCAL_NOT_FOUND
        # for paths that simply don't exist. No stdout assertion — the
        # caller is responsible for messaging on this branch.
        result = wizard._validate_local_jsonl("/no/such/path.jsonl")
        assert result is wizard._BYOD_LOCAL_NOT_FOUND

    def test_validate_local_jsonl_malformed_prints_error(self, tmp_path, capsys):
        bad = tmp_path / "bad.jsonl"
        bad.write_text("{not json\n", encoding="utf-8")
        result = wizard._validate_local_jsonl(str(bad))
        assert result is None
        captured = capsys.readouterr().out
        assert "not valid JSONL" in captured

    @pytest.mark.parametrize(
        "max_length,expect_none",
        [
            (1024, True),  # below threshold → no prompt, returns None
            (4096, True),  # at threshold → still no prompt, returns None
        ],
    )
    def test_collect_rope_scaling_short_context_silent(self, max_length, expect_none, capsys):
        # Short contexts must NOT emit the long-context detected line;
        # this guards the wizard from spamming spurious RoPE prompts on
        # the default 2048/4096 paths every operator hits.
        result = wizard._collect_rope_scaling(max_length)
        if expect_none:
            assert result is None
        captured = capsys.readouterr().out
        assert "Long context detected" not in captured

    def test_print_wizard_summary_includes_strategy_and_dataset(self, capsys):
        # Phase 22 rewrite: ``_print_wizard_summary`` takes the resolved
        # config dict instead of ~12 keyword arguments.  The summary
        # body now also includes the full YAML preview (G17), so we
        # only assert on the labelled summary lines that the rest of
        # the wizard depends on.
        wizard._print_wizard_summary(
            {
                "model": {
                    "name_or_path": "meta-llama/Llama-3.1-8B-Instruct",
                    "backend": "transformers",
                    "load_in_4bit": True,
                },
                "lora": {"r": 16, "alpha": 32, "method": "lora"},
                "training": {
                    "trainer_type": "sft",
                    "num_train_epochs": 3,
                    "per_device_train_batch_size": 4,
                    "output_dir": "./checkpoints",
                },
                "data": {"dataset_name_or_path": "tatsu-lab/alpaca"},
            }
        )
        out = capsys.readouterr().out
        assert "Configuration Summary" in out
        assert "Model:    meta-llama/Llama-3.1-8B-Instruct" in out
        assert "Strategy: QLoRA" in out
        assert "Trainer:  SFT" in out
        assert "Dataset:  tatsu-lab/alpaca" in out
        assert "Output:   ./checkpoints/final_model" in out

    def test_print_wizard_summary_galore_strategy(self, capsys):
        # GaLore takes precedence over the QLoRA / LoRA branch; pin the
        # branch so a reordering of the if/elif ladder can't silently
        # swallow the GaLore label in summaries.
        wizard._print_wizard_summary(
            {
                "model": {"name_or_path": "m", "backend": "transformers", "load_in_4bit": False},
                "lora": {"r": 8, "alpha": 16, "method": "lora"},
                "training": {
                    "trainer_type": "sft",
                    "galore_enabled": True,
                    "num_train_epochs": 1,
                    "per_device_train_batch_size": 1,
                    "output_dir": "./out",
                },
                "data": {"dataset_name_or_path": "d"},
            }
        )
        assert "Strategy: GaLore" in capsys.readouterr().out

    def test_print_wizard_summary_dora_suffix(self, capsys):
        wizard._print_wizard_summary(
            {
                "model": {"name_or_path": "m", "backend": "transformers", "load_in_4bit": True},
                "lora": {"r": 8, "alpha": 16, "method": "dora"},
                "training": {
                    "trainer_type": "dpo",
                    "num_train_epochs": 1,
                    "per_device_train_batch_size": 1,
                    "output_dir": "./out",
                },
                "data": {"dataset_name_or_path": "d"},
            }
        )
        out = capsys.readouterr().out
        assert "Strategy: QLoRA + DORA" in out
        assert "Trainer:  DPO" in out


class TestSaveConfigToFile:
    def test_save_config_emits_path_message(self, tmp_path, capsys):
        # Round-trips the happy path: the file is written and the
        # confirmation line names the path the wizard chose. The OSError
        # fallback is exercised separately via permission games elsewhere.
        target = tmp_path / "out.yaml"
        result = wizard._save_config_to_file({"model": {"name_or_path": "x"}}, str(target))
        assert Path(result) == target
        assert target.is_file()
        captured = capsys.readouterr().out
        assert f"Config saved to: {target}" in captured
