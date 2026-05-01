"""C-55: regex-based MoE expert name resolver.

Three-architecture fixture coverage for ``_EXPERT_NAME_PATTERNS`` in
:mod:`forgelm.model`. State-dict key samples are minimal but match the
published listings for Mixtral, Qwen 3 MoE, DeepSeek-V3, and Phi-MoE so a
future architecture-renaming PR fails here rather than silently making
every expert trainable.
"""

from __future__ import annotations


class TestExpertNamePatterns:
    def test_mixtral_8x7b_state_dict_keys(self):
        from forgelm.model import _expert_index_in_name

        # Mixtral-8x7B published key shape:
        # model.layers.{L}.block_sparse_moe.experts.{E}.{w1|w2|w3}.weight
        names = [
            "model.layers.0.block_sparse_moe.experts.0.w1.weight",
            "model.layers.0.block_sparse_moe.experts.3.w2.weight",
            "model.layers.7.block_sparse_moe.experts.7.w3.weight",
        ]
        assert _expert_index_in_name(names[0], 8) == 0
        assert _expert_index_in_name(names[1], 8) == 3
        assert _expert_index_in_name(names[2], 8) == 7

    def test_qwen3_moe_state_dict_keys(self):
        from forgelm.model import _expert_index_in_name

        # Qwen 3 MoE published key shape:
        # model.layers.{L}.mlp.experts.{E}.{up_proj|down_proj|gate_proj}.weight
        names = [
            "model.layers.2.mlp.experts.0.up_proj.weight",
            "model.layers.2.mlp.experts.31.down_proj.weight",
            "model.layers.5.mlp.experts.63.gate_proj.weight",
        ]
        assert _expert_index_in_name(names[0], 64) == 0
        assert _expert_index_in_name(names[1], 64) == 31
        assert _expert_index_in_name(names[2], 64) == 63

    def test_deepseek_v3_state_dict_keys(self):
        from forgelm.model import _expert_index_in_name

        # DeepSeek-V3 published key shape uses ``mlp.experts.{E}.``.
        names = [
            "model.layers.0.mlp.experts.0.gate_proj.weight",
            "model.layers.10.mlp.experts.127.up_proj.weight",
            "model.layers.10.mlp.experts.255.down_proj.weight",
        ]
        assert _expert_index_in_name(names[0], 256) == 0
        assert _expert_index_in_name(names[1], 256) == 127
        assert _expert_index_in_name(names[2], 256) == 255

    def test_phi_moe_flat_naming(self):
        from forgelm.model import _expert_index_in_name

        # Phi-MoE / GShard-style flat ``expert_{E}.``.
        names = [
            "model.layers.0.mlp.expert_0.gate.weight",
            "model.layers.4.mlp.expert_15.up.weight",
        ]
        assert _expert_index_in_name(names[0], 16) == 0
        assert _expert_index_in_name(names[1], 16) == 15

    def test_nested_expert_under_experts(self):
        from forgelm.model import _expert_index_in_name

        # Hypothetical nested form: experts.expert_{E}.
        assert _expert_index_in_name("model.experts.expert_2.weight", 8) == 2

    def test_non_expert_name_returns_none(self):
        from forgelm.model import _expert_index_in_name

        # Embedding / attention / norm parameters must not match any pattern.
        assert _expert_index_in_name("model.embed_tokens.weight", 8) is None
        assert _expert_index_in_name("model.layers.0.self_attn.q_proj.weight", 8) is None
        assert _expert_index_in_name("model.layers.0.input_layernorm.weight", 8) is None

    def test_expert_index_outside_range_returns_none(self):
        from forgelm.model import _expert_index_in_name

        # State-dict key claims expert 12 but config says 8 experts; the
        # resolver must reject rather than silently accept.
        assert _expert_index_in_name("model.layers.0.mlp.experts.12.up_proj.weight", 8) is None

    def test_unicode_digit_is_not_matched(self):
        from forgelm.model import _expert_index_in_name

        # ASCII flag rejects exotic Unicode digit characters so we do not
        # mis-resolve adversarial / corrupted state-dict keys.
        # U+0660 = Arabic-Indic digit zero. ASCII \d does not match it.
        assert _expert_index_in_name("model.experts.٠.weight", 8) is None

    def test_unfamiliar_expert_name_logs_info(self, caplog):
        import logging

        from forgelm.model import _LOGGED_UNKNOWN_EXPERT_NAMES, _expert_index_in_name

        # Clear the module-level sentinel so prior tests with unrecognized names
        # (e.g. the Arabic-digit test) don't suppress this run's log emission.
        _LOGGED_UNKNOWN_EXPERT_NAMES.discard("_UNKNOWN_EXPERT_LAYOUT_")

        with caplog.at_level(logging.INFO, logger="forgelm.model"):
            result = _expert_index_in_name("model.weird_expert_layout.weight", 8)
        assert result is None
        # Name contains "expert" but no pattern matched — operator must see it.
        assert "Unrecognized MoE expert parameter naming" in caplog.text

    def test_pattern_registry_uses_ascii_flag(self):
        import re

        from forgelm.model import _EXPERT_NAME_PATTERNS

        for pattern in _EXPERT_NAME_PATTERNS:
            assert pattern.flags & re.ASCII, f"Pattern {pattern.pattern!r} must use re.ASCII"
