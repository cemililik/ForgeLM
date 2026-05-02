"""Faz 10: parse-time Literal validation sweep.

Each enum-shaped string field that was tightened from `str` to `Literal[...]`
must accept every documented value and raise `pydantic.ValidationError`
with the offending field name in the message for any other input.
"""

import pytest
from pydantic import ValidationError

from forgelm.config import (
    ComplianceMetadataConfig,
    DistributedConfig,
    LoraConfigModel,
    SafetyConfig,
    TrainingConfig,
)


class TestLoraBiasLiteral:
    @pytest.mark.parametrize("value", ["none", "all", "lora_only"])
    def test_valid_bias(self, value):
        lora = LoraConfigModel(bias=value)
        assert lora.bias == value

    def test_invalid_bias_raises(self):
        with pytest.raises(ValidationError, match="bias"):
            LoraConfigModel(bias="bogus")


class TestFsdpBackwardPrefetchLiteral:
    @pytest.mark.parametrize("value", ["backward_pre", "backward_post"])
    def test_valid_prefetch(self, value):
        d = DistributedConfig(fsdp_backward_prefetch=value)
        assert d.fsdp_backward_prefetch == value

    def test_invalid_prefetch_raises(self):
        with pytest.raises(ValidationError, match="fsdp_backward_prefetch"):
            DistributedConfig(fsdp_backward_prefetch="forward_pre")


class TestFsdpStateDictTypeLiteral:
    @pytest.mark.parametrize("value", ["FULL_STATE_DICT", "SHARDED_STATE_DICT"])
    def test_valid_state_dict_type(self, value):
        d = DistributedConfig(fsdp_state_dict_type=value)
        assert d.fsdp_state_dict_type == value

    def test_invalid_state_dict_type_raises(self):
        with pytest.raises(ValidationError, match="fsdp_state_dict_type"):
            DistributedConfig(fsdp_state_dict_type="full_state_dict")


class TestSafetyScoringLiteral:
    @pytest.mark.parametrize("value", ["binary", "confidence_weighted"])
    def test_valid_scoring(self, value):
        s = SafetyConfig(scoring=value)
        assert s.scoring == value

    def test_invalid_scoring_raises(self):
        with pytest.raises(ValidationError, match="scoring"):
            SafetyConfig(scoring="weighted")


class TestRiskClassificationLiteral:
    @pytest.mark.parametrize("value", ["high-risk", "limited-risk", "minimal-risk"])
    def test_valid_classification(self, value):
        c = ComplianceMetadataConfig(risk_classification=value)
        assert c.risk_classification == value

    def test_invalid_classification_raises(self):
        with pytest.raises(ValidationError, match="risk_classification"):
            ComplianceMetadataConfig(risk_classification="unknown")


class TestGaloreOptimLiteral:
    @pytest.mark.parametrize(
        "value",
        [
            "galore_adamw",
            "galore_adamw_8bit",
            "galore_adafactor",
            "galore_adamw_layerwise",
            "galore_adamw_8bit_layerwise",
            "galore_adafactor_layerwise",
        ],
    )
    def test_valid_optim(self, value):
        t = TrainingConfig(galore_optim=value)
        assert t.galore_optim == value

    def test_invalid_optim_raises(self):
        with pytest.raises(ValidationError, match="galore_optim"):
            TrainingConfig(galore_optim="adamw")


class TestGaloreProjTypeLiteral:
    @pytest.mark.parametrize("value", ["std", "reverse_std", "right", "left", "full"])
    def test_valid_proj_type(self, value):
        t = TrainingConfig(galore_proj_type=value)
        assert t.galore_proj_type == value

    def test_invalid_proj_type_raises(self):
        with pytest.raises(ValidationError, match="galore_proj_type"):
            TrainingConfig(galore_proj_type="diagonal")
