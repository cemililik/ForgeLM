"""Phase 22 / 2026-05-08: CLI wizard parity-with-web modernisation tests.

Covers the new helpers + step-machine plumbing introduced when the CLI
wizard was extended to close the parity gap with ``site/js/wizard.js``
documented in
``docs/analysis/code_reviews/2026-05-07_cli_wizard_ux_analysis.md``:

- ``_parse_webhook_value`` — single-prompt webhook syntax with
  ``env:VAR_NAME`` prefix and HTTPS validation.
- ``_default_safety_probes_path`` — package-data resolution of the
  bundled probe set.
- ``_collect_trainer_hyperparameters`` — per-trainer fields gating.
- ``_check_navigation_token`` — back / reset sentinels.
- ``_apply_strict_tier_coercion`` — F-compliance-110 front-stop.
- ``_save_wizard_state`` / ``_load_wizard_state`` /
  ``_clear_wizard_state`` — XDG-aware persistence.
- ``_print_step_diff`` — terminal-friendly state diff.

No GPU / no network — every test stubs ``builtins.input`` for stdin
reads and uses a temp directory for persistence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from forgelm import wizard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _input_returning(*answers):
    """Build a side_effect for ``builtins.input`` that drains *answers*."""
    queue = list(answers)

    def _impl(_prompt_text=""):
        if not queue:
            raise AssertionError("input() called more times than answers provided")
        return queue.pop(0)

    return _impl


# ---------------------------------------------------------------------------
# Webhook URL parsing — Phase 22 / G15
# ---------------------------------------------------------------------------


class TestParseWebhookValue:
    def test_empty_returns_none(self):
        assert wizard._parse_webhook_value("") is None
        assert wizard._parse_webhook_value("   ") is None

    def test_https_url_accepted(self):
        section = wizard._parse_webhook_value("https://hooks.slack.com/services/T/B/X")
        assert section == {"url": "https://hooks.slack.com/services/T/B/X"}

    def test_env_prefix_emits_url_env(self):
        section = wizard._parse_webhook_value("env:SLACK_WEBHOOK_URL")
        assert section == {"url_env": "SLACK_WEBHOOK_URL"}

    def test_env_prefix_case_insensitive_keyword(self):
        # The ``env:`` keyword itself is matched case-insensitively so
        # operators copying values from the web wizard's YAML aren't
        # tripped up by case.
        section = wizard._parse_webhook_value("ENV:MY_WEBHOOK")
        assert section == {"url_env": "MY_WEBHOOK"}

    def test_env_prefix_empty_var_name_rejected(self):
        with pytest.raises(ValueError, match="non-empty variable name"):
            wizard._parse_webhook_value("env:")

    def test_env_prefix_lowercase_var_name_rejected(self):
        # POSIX env-var convention enforces uppercase letters; lower-
        # case names break ``${VAR}`` shell expansion in CI.
        with pytest.raises(ValueError, match="POSIX environment-variable name"):
            wizard._parse_webhook_value("env:lowercase_var")

    def test_bare_string_no_scheme_rejected(self):
        with pytest.raises(ValueError, match="not a valid URL"):
            wizard._parse_webhook_value("not-a-url")

    def test_unknown_scheme_rejected(self):
        with pytest.raises(ValueError, match="must use `https://`"):
            wizard._parse_webhook_value("ftp://example.com/hook")

    def test_http_warning_but_accepted(self, capsys):
        section = wizard._parse_webhook_value("http://hooks.example.com/x")
        assert section == {"url": "http://hooks.example.com/x"}
        captured = capsys.readouterr().out
        assert "uses HTTP, not HTTPS" in captured


# ---------------------------------------------------------------------------
# Safety probe path resolution — Phase 22 / G16
# ---------------------------------------------------------------------------


class TestDefaultSafetyProbesPath:
    def test_resolves_to_packaged_jsonl(self):
        # The bundled probe set lives at
        # ``forgelm/safety_prompts/default_probes.jsonl`` and is
        # shipped via ``[tool.setuptools.package-data]`` in
        # ``pyproject.toml`` (Phase 36).  The resolver must produce a
        # real on-disk path the trainer can ``open``.
        path = wizard._default_safety_probes_path()
        assert path.endswith("default_probes.jsonl")
        assert Path(path).is_file()

    def test_path_is_absolute_or_resolvable(self):
        # ``pkgutil.get_data`` would return bytes; the wizard prefers
        # ``importlib.resources.files`` so the operator gets a string
        # path they can hand to ``forgelm safety-eval --probes``.
        path = wizard._default_safety_probes_path()
        assert Path(path).resolve().is_file()


# ---------------------------------------------------------------------------
# Navigation tokens — Phase 22 / G3
# ---------------------------------------------------------------------------


class TestNavigationTokens:
    def test_back_token_raises_wizardback(self):
        for token in ("back", "b", "BACK", "  Back  "):
            with pytest.raises(wizard.WizardBack):
                wizard._check_navigation_token(token)

    def test_reset_token_raises_wizardreset(self):
        for token in ("reset", "r", "RESET", "  Reset  "):
            with pytest.raises(wizard.WizardReset):
                wizard._check_navigation_token(token)

    def test_cancel_token_does_not_raise(self):
        # Cancel is contextual — the BYOD path interprets it as "fall
        # back to the full wizard" and the step orchestrator relies on
        # Ctrl-C / Ctrl-D for clean exits.  Auto-raising on cancel
        # would break the existing BYOD flow.
        for token in ("cancel", "c", "q", "quit"):
            wizard._check_navigation_token(token)

    def test_empty_string_does_not_raise(self):
        wizard._check_navigation_token("")
        wizard._check_navigation_token("   ")

    def test_normal_input_does_not_raise(self):
        wizard._check_navigation_token("Llama-3.1-8B")
        wizard._check_navigation_token("yes")
        wizard._check_navigation_token("3")


# ---------------------------------------------------------------------------
# Trainer-specific hyperparameters — Phase 22 / G1
# ---------------------------------------------------------------------------


class TestCollectTrainerHyperparameters:
    def test_sft_returns_empty(self):
        # SFT has no per-trainer knobs in ``TrainingConfig``.
        with patch("builtins.input", side_effect=_input_returning()):
            result = wizard._collect_trainer_hyperparameters("sft")
        assert result == {}

    def test_dpo_returns_dpo_beta(self):
        with patch("builtins.input", side_effect=_input_returning("0.1")):
            result = wizard._collect_trainer_hyperparameters("dpo")
        assert result == {"dpo_beta": 0.1}

    def test_simpo_returns_beta_and_gamma(self):
        with patch("builtins.input", side_effect=_input_returning("2.0", "0.5")):
            result = wizard._collect_trainer_hyperparameters("simpo")
        assert result == {"simpo_beta": 2.0, "simpo_gamma": 0.5}

    def test_kto_returns_kto_beta(self):
        with patch("builtins.input", side_effect=_input_returning("0.1")):
            result = wizard._collect_trainer_hyperparameters("kto")
        assert result == {"kto_beta": 0.1}

    def test_orpo_returns_orpo_beta(self):
        with patch("builtins.input", side_effect=_input_returning("0.1")):
            result = wizard._collect_trainer_hyperparameters("orpo")
        assert result == {"orpo_beta": 0.1}

    def test_grpo_returns_full_block_with_reward_model(self):
        with patch(
            "builtins.input",
            side_effect=_input_returning("4", "512", "my_reward.score"),
        ):
            result = wizard._collect_trainer_hyperparameters("grpo")
        assert result == {
            "grpo_num_generations": 4,
            "grpo_max_completion_length": 512,
            "grpo_reward_model": "my_reward.score",
        }

    def test_grpo_omits_reward_model_when_blank(self):
        # Empty reward_model means "use the built-in shaper" — which
        # the schema represents as ``None``.  The wizard drops the key
        # entirely so the YAML doesn't carry an empty string the
        # validator would have to special-case.
        with patch("builtins.input", side_effect=_input_returning("4", "512", "")):
            result = wizard._collect_trainer_hyperparameters("grpo")
        assert result == {
            "grpo_num_generations": 4,
            "grpo_max_completion_length": 512,
        }
        assert "grpo_reward_model" not in result


# ---------------------------------------------------------------------------
# Strict-tier auto-coercion — Phase 22 / G8
# ---------------------------------------------------------------------------


class TestApplyStrictTierCoercion:
    def test_minimal_risk_no_op(self):
        config = {"evaluation": {"auto_revert": True}}
        wizard._apply_strict_tier_coercion(config, {"risk_classification": "minimal-risk"})
        # Should NOT have added safety + require_human_approval.
        assert "safety" not in config["evaluation"]
        assert "require_human_approval" not in config["evaluation"]

    def test_high_risk_enables_safety_and_human_approval(self, capsys):
        config: dict = {}
        wizard._apply_strict_tier_coercion(config, {"risk_classification": "high-risk"})
        assert config["evaluation"]["require_human_approval"] is True
        assert config["evaluation"]["safety"]["enabled"] is True
        assert config["evaluation"]["auto_revert"] is True
        captured = capsys.readouterr().out
        assert "Article 9" in captured
        assert "Article 14" in captured

    def test_unacceptable_also_triggers_coercion(self):
        config: dict = {}
        wizard._apply_strict_tier_coercion(config, {"risk_classification": "unacceptable"})
        assert config["evaluation"]["safety"]["enabled"] is True

    def test_does_not_overwrite_explicit_safety_block(self):
        # Operator already configured safety with track_categories=False;
        # coercion mustn't clobber their choices when safety is already
        # enabled.
        config = {"evaluation": {"safety": {"enabled": True, "track_categories": False}}}
        wizard._apply_strict_tier_coercion(config, {"risk_classification": "high-risk"})
        assert config["evaluation"]["safety"]["enabled"] is True
        assert config["evaluation"]["safety"]["track_categories"] is False


# ---------------------------------------------------------------------------
# Persistence — Phase 22 / G6
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """Redirect the wizard state directory to a tmp_path."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    yield tmp_path / "forgelm"


class TestPersistence:
    def test_load_returns_none_when_no_snapshot(self, isolated_state_dir):
        assert wizard._load_wizard_state() is None

    def test_save_and_load_roundtrip(self, isolated_state_dir):
        snapshot = {
            "experience": "beginner",
            "use_case": "customer-support",
            "current_step": 3,
            "completed_steps": ["welcome", "use-case", "model"],
            "config": {"model": {"name_or_path": "Qwen/Qwen2.5-7B-Instruct"}},
        }
        wizard._save_wizard_state(snapshot)
        loaded = wizard._load_wizard_state()
        assert loaded == snapshot

    def test_clear_removes_snapshot(self, isolated_state_dir):
        wizard._save_wizard_state({"experience": "expert"})
        wizard._clear_wizard_state()
        assert wizard._load_wizard_state() is None

    def test_clear_is_idempotent(self, isolated_state_dir):
        # Clearing a non-existent snapshot must not raise — the wizard
        # calls ``_clear_wizard_state`` on successful completion even
        # when nothing was saved.
        wizard._clear_wizard_state()
        wizard._clear_wizard_state()  # still fine

    def test_load_returns_none_on_version_mismatch(self, isolated_state_dir):
        path = wizard._wizard_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("v: 99999\nexperience: expert\n", encoding="utf-8")
        assert wizard._load_wizard_state() is None

    def test_load_returns_none_on_corrupt_snapshot(self, isolated_state_dir):
        path = wizard._wizard_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Invalid YAML — must not raise; just silently miss.
        path.write_text("not: valid: yaml: at: all", encoding="utf-8")
        assert wizard._load_wizard_state() is None

    def test_state_path_honours_xdg_cache_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert wizard._wizard_state_path() == tmp_path / "forgelm" / "wizard_state.yaml"

    def test_state_path_falls_back_to_home_cache_when_xdg_unset(self, monkeypatch):
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        path = wizard._wizard_state_path()
        # ``Path.home() / ".cache"`` may differ across CI environments,
        # but the trailing components are stable.
        assert path.name == "wizard_state.yaml"
        assert path.parent.name == "forgelm"


# ---------------------------------------------------------------------------
# Step-diff preview — Phase 22 / G7
# ---------------------------------------------------------------------------


class TestStepDiff:
    def test_no_diff_emits_nothing(self, capsys):
        wizard._print_step_diff({"a": 1}, {"a": 1}, "step1")
        assert capsys.readouterr().out == ""

    def test_added_keys_marked_with_plus(self, capsys):
        wizard._print_step_diff({}, {"model": {"name_or_path": "X"}}, "model")
        out = capsys.readouterr().out
        assert "Step diff (model):" in out
        assert "+ model.name_or_path: 'X'" in out

    def test_changed_keys_marked_with_tilde(self, capsys):
        wizard._print_step_diff({"a": 1}, {"a": 2}, "params")
        out = capsys.readouterr().out
        assert "~ a: 1 → 2" in out

    def test_nested_dict_paths_dotted(self, capsys):
        wizard._print_step_diff(
            {"training": {"epochs": 3}},
            {"training": {"epochs": 3, "batch_size": 4}},
            "training-params",
        )
        out = capsys.readouterr().out
        assert "+ training.batch_size: 4" in out
        assert "training.epochs" not in out  # unchanged → not printed


# ---------------------------------------------------------------------------
# Webhook collector — Phase 22 / G15 (integration around ``_parse_webhook_value``)
# ---------------------------------------------------------------------------


class TestCollectWebhookConfig:
    def test_decline_returns_none(self):
        with patch("builtins.input", side_effect=_input_returning("n")):
            assert wizard._collect_webhook_config() is None

    def test_env_prefix_default_accepted(self):
        # The prompt default is ``env:FORGELM_WEBHOOK_URL`` so an empty
        # answer accepts the suggested env-var.  ``notify_on_start``
        # defaults to ``False`` (web-wizard parity) — start
        # notifications are noisy and most operators want only success
        # / failure pings.
        with patch("builtins.input", side_effect=_input_returning("y", "")):
            section = wizard._collect_webhook_config()
        assert section == {
            "url_env": "FORGELM_WEBHOOK_URL",
            "notify_on_start": False,
            "notify_on_success": True,
            "notify_on_failure": True,
        }

    def test_https_url_accepted(self):
        with patch(
            "builtins.input",
            side_effect=_input_returning("y", "https://hooks.slack.com/x"),
        ):
            section = wizard._collect_webhook_config()
        assert section is not None
        assert section["url"] == "https://hooks.slack.com/x"

    def test_invalid_url_reprompts(self, capsys):
        # First answer is malformed; second is a valid env: ref.
        with patch(
            "builtins.input",
            side_effect=_input_returning("y", "not-a-url", "env:MY_HOOK"),
        ):
            section = wizard._collect_webhook_config()
        assert section is not None
        assert section["url_env"] == "MY_HOOK"
        captured = capsys.readouterr().out
        assert "not a valid URL" in captured


# ---------------------------------------------------------------------------
# Use-case preset registry — Phase 22 / G12 + I4
# ---------------------------------------------------------------------------


class TestUseCasePresets:
    def test_presets_match_quickstart_template_keys(self):
        # I4: the web wizard's USE_CASE_PRESETS keys must adopt the
        # CLI quickstart TEMPLATES keys (single source of truth).  This
        # asserts the CLI side of the agreement: every TEMPLATES key
        # appears in ``_wizard_use_case_presets``.
        from forgelm.quickstart import TEMPLATES

        presets = wizard._wizard_use_case_presets()
        for key in TEMPLATES.keys():
            assert key in presets, f"Use-case preset for '{key}' missing"

    def test_custom_preset_present(self):
        # ``custom`` is a wizard-only escape hatch that doesn't seed
        # any defaults.
        presets = wizard._wizard_use_case_presets()
        assert wizard._MANUAL_USE_CASE in presets
        assert presets[wizard._MANUAL_USE_CASE]["model"] is None


# ---------------------------------------------------------------------------
# Strategy choice mapping — Phase 22 / G2
# ---------------------------------------------------------------------------


class TestStrategyChoices:
    def test_six_strategies_listed(self):
        # QLoRA / LoRA / DoRA / PiSSA / rsLoRA / GaLore — the full
        # ``LoraConfigModel.method`` Literal plus GaLore as a separate
        # axis.
        assert len(wizard._STRATEGY_CHOICES) == 6

    def test_methods_cover_full_lora_literal(self):
        methods = {choice.method for choice in wizard._STRATEGY_CHOICES if not choice.use_galore}
        assert methods == {"lora", "dora", "pissa", "rslora"}

    def test_galore_choice_is_singleton(self):
        galore_choices = [c for c in wizard._STRATEGY_CHOICES if c.use_galore]
        assert len(galore_choices) == 1


# ---------------------------------------------------------------------------
# GaLore optimizer variants — Phase 22 / G9
# ---------------------------------------------------------------------------


class TestGaloreOptimizers:
    def test_six_variants_listed(self):
        assert len(wizard._GALORE_OPTIMIZERS) == 6

    def test_includes_layerwise_siblings(self):
        # The original wizard listed only the three base variants.
        # Phase 22 surfaces all six, including ``_layerwise`` siblings
        # that drop peak VRAM further by recomputing per-layer.
        assert "galore_adamw_layerwise" in wizard._GALORE_OPTIMIZERS
        assert "galore_adamw_8bit_layerwise" in wizard._GALORE_OPTIMIZERS
        assert "galore_adafactor_layerwise" in wizard._GALORE_OPTIMIZERS


# ---------------------------------------------------------------------------
# Schema-default parity — Phase 22 / G11
# ---------------------------------------------------------------------------


class TestSchemaDefaultParity:
    def test_lora_r_default_matches_schema(self):
        # G11: the v0.5.5 wizard set DEFAULT_LORA_R = 16 while the
        # schema default in ``LoraConfigModel.r`` was 8.  Phase 22
        # aligns the wizard with the schema so an operator who accepts
        # every prompt produces a YAML byte-equivalent to
        # ``ForgeConfig()``.
        from forgelm.config import LoraConfigModel

        assert wizard.DEFAULT_LORA_R == LoraConfigModel.model_fields["r"].default

    def test_lora_alpha_default_is_2x_r(self):
        # Adapter convention: alpha = 2 * r.
        assert wizard.DEFAULT_LORA_ALPHA == 2 * wizard.DEFAULT_LORA_R

    def test_default_epochs_matches_schema(self):
        from forgelm.config import TrainingConfig

        assert wizard.DEFAULT_EPOCHS == TrainingConfig.model_fields["num_train_epochs"].default

    def test_default_batch_size_matches_schema(self):
        from forgelm.config import TrainingConfig

        assert wizard.DEFAULT_BATCH_SIZE == TrainingConfig.model_fields["per_device_train_batch_size"].default

    def test_default_lr_matches_schema(self):
        from forgelm.config import TrainingConfig

        assert wizard.DEFAULT_LR == TrainingConfig.model_fields["learning_rate"].default


# ---------------------------------------------------------------------------
# Orchestrator step-machine — Phase 22 / G3 + G7 + I3
#
# The orchestrator was the lowest-coverage module after the Phase 22
# split (14 % per the post-merge review).  These tests exercise the
# step driver directly with stub steps so we don't need to mock 9
# real ``_collect_*`` helpers.
# ---------------------------------------------------------------------------


class TestStepMachineDriver:
    """Exercise ``_drive_wizard_steps`` directly with stub steps."""

    def _make_steps(self, runners):
        """Build a tuple of ``_StepDef``-shaped objects for *runners*."""
        return tuple(
            wizard._orchestrator._StepDef(label=f"step-{i}", runner=runner) for i, runner in enumerate(runners)
        )

    def test_runs_every_step_in_order(self, isolated_state_dir, monkeypatch):
        order = []

        def make(label):
            def runner(state):
                order.append(label)
                state.config[label] = True

            return runner

        steps = self._make_steps([make("a"), make("b"), make("c")])
        monkeypatch.setattr(wizard._orchestrator, "_STEPS", steps)

        state = wizard._orchestrator._drive_wizard_steps(wizard._WizardState())
        assert order == ["a", "b", "c"]
        assert state.completed_steps == ["step-0", "step-1", "step-2"]
        assert state.current_step == 3

    def test_back_restores_prev_config(self, isolated_state_dir, monkeypatch):
        # Step 1 mutates state.config; step 2 mutates it then raises
        # WizardBack.  Mutations from step 2 must NOT leak back into
        # step 1 — that's the whole point of the prev_config snapshot.
        attempts = {"step-1": 0}

        def step0(state):
            state.config.setdefault("model", {})["name"] = "from-step-0"

        def step1_first(state):
            # First entry: mutate then back out.
            attempts["step-1"] += 1
            if attempts["step-1"] == 1:
                state.config["leaked"] = "should-not-survive"
                raise wizard.WizardBack

        def step0_after_back(state):
            # Re-running step 0 — the leaked key from step 1's first
            # attempt MUST be gone.
            assert "leaked" not in state.config

        # Stitch: step 0 runs twice (first then after back); step 1
        # runs once (raises back), then once more silently.
        runs = {"step-0": 0}

        def step0_combined(state):
            runs["step-0"] += 1
            if runs["step-0"] == 1:
                step0(state)
            else:
                step0_after_back(state)

        def step1_combined(state):
            attempts["step-1"] += 1
            if attempts["step-1"] == 1:
                state.config["leaked"] = "should-not-survive"
                raise wizard.WizardBack

        steps = self._make_steps([step0_combined, step1_combined])
        monkeypatch.setattr(wizard._orchestrator, "_STEPS", steps)

        state = wizard._orchestrator._drive_wizard_steps(wizard._WizardState())
        assert "leaked" not in state.config
        assert state.config["model"]["name"] == "from-step-0"

    def test_back_at_first_step_is_no_op(self, isolated_state_dir, monkeypatch, capsys):
        attempts = {"calls": 0}

        def step0(state):
            attempts["calls"] += 1
            if attempts["calls"] == 1:
                raise wizard.WizardBack
            # Second call: succeed normally.
            state.config["done"] = True

        steps = self._make_steps([step0])
        monkeypatch.setattr(wizard._orchestrator, "_STEPS", steps)

        wizard._orchestrator._drive_wizard_steps(wizard._WizardState())
        captured = capsys.readouterr().out
        assert "Already at the first step" in captured

    def test_reset_re_loops_with_fresh_state(self, isolated_state_dir, monkeypatch):
        # WizardReset MUST cause the driver to start over with a fresh
        # _WizardState — returning early would let _run_full_wizard
        # treat the reset as a completed run and try to save an empty
        # config.
        attempts = {"step-0": 0, "step-1": 0}

        def step0(state):
            attempts["step-0"] += 1
            state.config["k0"] = attempts["step-0"]

        def step1(state):
            attempts["step-1"] += 1
            if attempts["step-1"] == 1:
                raise wizard.WizardReset

        steps = self._make_steps([step0, step1])
        monkeypatch.setattr(wizard._orchestrator, "_STEPS", steps)

        state = wizard._orchestrator._drive_wizard_steps(wizard._WizardState())
        # step-0 ran twice (first run + after reset), step-1 ran twice
        # too (first raised reset, second completed cleanly).
        assert attempts["step-0"] == 2
        assert attempts["step-1"] == 2
        # State after the reset should reflect the second (fresh) run,
        # not the first.
        assert state.config["k0"] == 2

    def test_persists_after_each_completed_step(self, isolated_state_dir, monkeypatch):
        def step0(state):
            state.config["a"] = 1

        def step1(state):
            # Snapshot must already include step 0's mutation when we
            # arrive here — the orchestrator persists eagerly.
            saved = wizard._load_wizard_state()
            assert saved is not None
            assert saved["config"]["a"] == 1
            state.config["b"] = 2

        steps = self._make_steps([step0, step1])
        monkeypatch.setattr(wizard._orchestrator, "_STEPS", steps)

        wizard._orchestrator._drive_wizard_steps(wizard._WizardState())
        saved = wizard._load_wizard_state()
        assert saved is not None
        assert saved["config"] == {"a": 1, "b": 2}
        assert saved["completed_steps"] == ["step-0", "step-1"]


class TestMaybeResumeState:
    def test_returns_fresh_state_when_no_snapshot(self, isolated_state_dir):
        state = wizard._orchestrator._maybe_resume_state()
        assert state.current_step == 0
        assert state.config == {}
        assert state.completed_steps == []

    def test_resumes_from_saved_snapshot(self, isolated_state_dir):
        wizard._save_wizard_state(
            {
                "experience": "beginner",
                "use_case": "domain-expert",
                "current_step": 2,
                "completed_steps": ["welcome", "use-case"],
                "config": {"model": {"name_or_path": "x"}},
            }
        )
        with patch("builtins.input", side_effect=_input_returning("y")):  # accept resume
            state = wizard._orchestrator._maybe_resume_state()
        assert state.current_step == 2
        assert state.completed_steps == ["welcome", "use-case"]
        assert state.config == {"model": {"name_or_path": "x"}}
        assert state.experience == "beginner"

    def test_decline_resume_clears_snapshot(self, isolated_state_dir):
        wizard._save_wizard_state(
            {
                "experience": "expert",
                "use_case": "custom",
                "current_step": 1,
                "completed_steps": ["welcome"],
                "config": {"a": 1},
            }
        )
        with patch("builtins.input", side_effect=_input_returning("n")):  # decline
            state = wizard._orchestrator._maybe_resume_state()
        assert state.current_step == 0
        assert state.config == {}
        # Snapshot was cleared so a future load returns None.
        assert wizard._load_wizard_state() is None


class TestStepWelcome:
    def test_welcome_sets_backend_hint(self, capsys):
        # Stubbing _detect_hardware to return "no GPU" makes the
        # outcome deterministic across CI runners that may or may not
        # see CUDA.
        state = wizard._WizardState()
        with (
            patch("builtins.input", side_effect=_input_returning("n")),  # not first-time
            patch.object(
                wizard._orchestrator,
                "_detect_hardware",
                return_value={
                    "gpu_available": False,
                    "gpu_name": None,
                    "vram_gb": None,
                    "cuda_version": None,
                },
            ),
        ):
            wizard._orchestrator._step_welcome(state)
        assert state.experience == "expert"
        assert state.config["model"]["backend"] == "transformers"
        captured = capsys.readouterr().out
        assert "No GPU detected" in captured

    def test_welcome_beginner_branch(self):
        state = wizard._WizardState()
        with (
            patch("builtins.input", side_effect=_input_returning("y")),  # first-time
            patch.object(
                wizard._orchestrator,
                "_detect_hardware",
                return_value={
                    "gpu_available": False,
                    "gpu_name": None,
                    "vram_gb": None,
                    "cuda_version": None,
                },
            ),
        ):
            wizard._orchestrator._step_welcome(state)
        assert state.experience == "beginner"
