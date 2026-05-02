"""Phase 10: parse-time Literal validation sweep.

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
    @pytest.mark.parametrize(
        "value",
        ["unknown", "minimal-risk", "limited-risk", "high-risk", "unacceptable"],
    )
    def test_valid_classification(self, value):
        c = ComplianceMetadataConfig(risk_classification=value)
        assert c.risk_classification == value

    def test_invalid_classification_raises(self):
        with pytest.raises(ValidationError, match="risk_classification"):
            ComplianceMetadataConfig(risk_classification="not-a-risk-tier")

    def test_minimal_risk_default(self):
        # Default stays "minimal-risk" so existing configs validate unchanged
        # after the value-set extension (Phase 10 closure: 3 → 5 EU AI Act
        # tiers covering Article 5 prohibited + unknown/unclassified).
        c = ComplianceMetadataConfig()
        assert c.risk_classification == "minimal-risk"


class TestRiskCategoryLiteral:
    """``RiskAssessmentConfig.risk_category`` mirrors ``risk_classification``.

    The two fields are deliberately kept in lockstep (single source of truth
    for the EU AI Act tier list); changing one without the other would
    silently drift the validation of the two halves of a compliance config.
    """

    @pytest.mark.parametrize(
        "value",
        ["unknown", "minimal-risk", "limited-risk", "high-risk", "unacceptable"],
    )
    def test_valid_category(self, value):
        from forgelm.config import RiskAssessmentConfig

        r = RiskAssessmentConfig(risk_category=value)
        assert r.risk_category == value

    def test_invalid_category_raises(self):
        from forgelm.config import RiskAssessmentConfig

        with pytest.raises(ValidationError, match="risk_category"):
            RiskAssessmentConfig(risk_category="not-a-risk-tier")

    def test_minimal_risk_default(self):
        # Mirror of TestRiskClassificationLiteral.test_minimal_risk_default —
        # the two fields share the RiskTier alias and must therefore share
        # the default; surfaces any future divergence between them.
        from forgelm.config import RiskAssessmentConfig

        r = RiskAssessmentConfig()
        assert r.risk_category == "minimal-risk"


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
