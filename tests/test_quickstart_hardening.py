"""Regression tests for the Phase 10.5 quickstart hardening pass.

Each test class targets a specific defect surfaced in PR review against
:mod:`forgelm.quickstart`. Kept in a separate module from
``test_quickstart.py`` so parallel agents can edit either file without
conflicts.
"""

from __future__ import annotations

import pytest
import yaml

from forgelm.quickstart import (
    TEMPLATES,
    _default_output_path,
    _materialize_config,
    auto_select_model,
    get_template,
    run_quickstart,
    template_assets,
)

# ---------------------------------------------------------------------------
# Fix #1 — bundled dataset must not be overwritten by a subsequent run
# ---------------------------------------------------------------------------


class TestPerRunDatasetIsolation:
    def test_two_runs_yield_distinct_directories(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        first = run_quickstart("customer-support", available_vram_gb=24.0)
        second = run_quickstart("customer-support", available_vram_gb=24.0)
        assert first.config_path.parent != second.config_path.parent
        assert first.dataset_path != second.dataset_path

    def test_user_edits_to_first_run_dataset_survive_second_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        first = run_quickstart("customer-support", available_vram_gb=24.0)

        sentinel = '{"messages": [{"role": "user", "content": "EDITED-BY-USER"}]}\n'
        # Simulate the user editing their copy of the seed dataset between runs.
        from pathlib import Path

        edited = Path(first.dataset_path)
        edited.write_text(sentinel, encoding="utf-8")

        run_quickstart("customer-support", available_vram_gb=24.0)

        assert edited.read_text(encoding="utf-8") == sentinel, (
            "second quickstart run must not touch the first run's dataset"
        )


# ---------------------------------------------------------------------------
# Fix #2 — _materialize_config tolerates ``model: null`` / ``data: null``
# ---------------------------------------------------------------------------


class TestMaterializeConfigNullSafety:
    def test_null_model_section_is_replaced_not_crashed(self, tmp_path, monkeypatch):
        # Build a template-shaped YAML where `model:` is null and feed it via
        # the template loader by monkeypatching template_assets.
        fake_cfg = tmp_path / "config.yaml"
        fake_cfg.write_text("model: null\ndata: null\n", encoding="utf-8")

        from forgelm import quickstart as qs

        def _fake_assets(name):
            return fake_cfg, None

        monkeypatch.setattr(qs, "template_assets", _fake_assets)
        tpl = get_template("customer-support")
        # Use tmp_path-based string instead of "/tmp/..." — Sonar flags the
        # latter as a publicly-writable race-condition surface even though
        # the path is never actually opened here (just rendered into YAML).
        ds_path = str(tmp_path / "data.jsonl")
        cfg = _materialize_config(tpl, "my-org/m", ds_path)
        assert cfg["model"] == {"name_or_path": "my-org/m"}
        assert cfg["data"] == {"dataset_name_or_path": ds_path}

    def test_non_mapping_model_value_raises_clear_error(self, tmp_path, monkeypatch):
        fake_cfg = tmp_path / "config.yaml"
        fake_cfg.write_text("model: 42\n", encoding="utf-8")

        from forgelm import quickstart as qs

        def _fake_assets(name):
            return fake_cfg, None

        monkeypatch.setattr(qs, "template_assets", _fake_assets)
        tpl = get_template("customer-support")
        with pytest.raises(ValueError, match="non-mapping value for 'model'"):
            _materialize_config(tpl, "my-org/m", str(tmp_path / "data.jsonl"))


# ---------------------------------------------------------------------------
# Fix #3 — CPU / no-GPU returns the fallback model for every template
# ---------------------------------------------------------------------------


class TestNoGpuPicksFallbackForEveryTemplate:
    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_returns_fallback_when_vram_is_none(self, name):
        tpl = TEMPLATES[name]
        model, reason = auto_select_model(tpl, available_vram_gb=None)
        assert model == tpl.fallback_model, f"{name} did not downsize on no-GPU host"
        assert "no GPU detected" in reason
        assert "fallback" in reason.lower() or "cpu" in reason.lower()


# ---------------------------------------------------------------------------
# Fix #4 — _default_output_path is collision-free across rapid calls
# ---------------------------------------------------------------------------


class TestDefaultOutputPathUnique:
    def test_two_immediate_calls_produce_distinct_paths(self):
        a = _default_output_path("customer-support")
        b = _default_output_path("customer-support")
        assert a != b
        # And the per-run directory differs — not just the filename.
        assert a.parent != b.parent

    def test_default_output_path_is_per_run_subdirectory(self):
        path = _default_output_path("customer-support")
        # New scheme: configs/<template>-<slug>/config.yaml
        assert path.name == "config.yaml"
        assert path.parent.name.startswith("customer-support-")
        assert path.parent.parent.name == "configs"


# ---------------------------------------------------------------------------
# Fix #5 — generated YAML carries a provenance header
# ---------------------------------------------------------------------------


class TestProvenanceHeader:
    def test_header_documents_template_and_generator(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run_quickstart("customer-support", available_vram_gb=24.0)
        with open(result.config_path, encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(10))
        assert "generated by forgelm quickstart" in head
        assert "customer-support" in head
        # The body must remain valid YAML even with the header in front.
        with open(result.config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["model"]["name_or_path"] == result.chosen_model

    def test_header_contains_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run_quickstart("code-assistant", available_vram_gb=24.0)
        text = result.config_path.read_text(encoding="utf-8")
        for needle in (
            "template:",
            "generated_at:",
            "forgelm_version:",
            "chosen_model:",
            "selection_reason:",
        ):
            assert needle in text, f"provenance header missing '{needle}'"


# ---------------------------------------------------------------------------
# Smoke: bundled template still resolves through the new directory scheme
# ---------------------------------------------------------------------------


class TestBundledTemplateStillResolves:
    def test_bundled_dataset_lives_alongside_generated_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run_quickstart("customer-support", available_vram_gb=24.0)
        from pathlib import Path

        ds = Path(result.dataset_path)
        assert ds.parent == result.config_path.parent
        # The bundled source must remain untouched at its package location.
        _, bundled = template_assets("customer-support")
        assert bundled is not None and bundled.is_file()
