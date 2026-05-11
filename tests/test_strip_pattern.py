"""Phase 15 Wave 2 Task 11 unit tests — operator strip-pattern + ReDoS guard."""

from __future__ import annotations

import re

import pytest

from forgelm._strip_pattern import (
    DEFAULT_TIMEOUT_S,
    StripPatternError,
    apply_strip_patterns,
    compile_strip_patterns,
    validate_strip_pattern,
)


class TestValidateStripPattern:
    def test_accepts_simple_pattern(self):
        assert validate_strip_pattern(r"^WATERMARK \d+$") == r"^WATERMARK \d+$"

    def test_rejects_empty(self):
        with pytest.raises(StripPatternError, match="non-empty"):
            validate_strip_pattern("")

    def test_rejects_invalid_regex_syntax(self):
        with pytest.raises(StripPatternError, match="not a valid"):
            validate_strip_pattern("[unclosed")

    def test_rejects_nested_unbounded_quantifier(self):
        # Classic ReDoS shape: (a+)+ — nested unbounded quantifier.
        with pytest.raises(StripPatternError, match="ReDoS"):
            validate_strip_pattern("(a+)+b")

    def test_rejects_dotall_lazy_with_backref(self):
        # rule 6: .*? + back-reference under DOTALL is the S5852 shape.
        with pytest.raises(StripPatternError, match="DOTALL"):
            validate_strip_pattern(r"(?s)(a).*?\1")

    def test_rejects_overlong_pattern(self):
        # 3 KB pattern exceeds the 2 KB safety bound.
        with pytest.raises(StripPatternError, match="too long"):
            validate_strip_pattern("a" * 3000)

    def test_accepts_anchored_negated_class(self):
        # The canonical "strip header line" pattern shape.
        assert validate_strip_pattern(r"^[A-Z ]+CONFIDENTIAL[A-Z ]*$")


class TestCompileStripPatterns:
    def test_compile_returns_raw_plus_compiled_pairs(self):
        pairs = compile_strip_patterns([r"^WATERMARK$", r"^FOOTER$"])
        assert len(pairs) == 2
        assert all(isinstance(p[1], re.Pattern) for p in pairs)
        assert pairs[0][0] == r"^WATERMARK$"

    def test_compile_propagates_validation_error(self):
        with pytest.raises(StripPatternError):
            compile_strip_patterns([r"(a+)+b"])


class TestApplyStripPatterns:
    def test_apply_strips_matching_lines(self):
        patterns = compile_strip_patterns([r"^WATERMARK \d+$"])
        text = "Body\nWATERMARK 1\nMore body.\nWATERMARK 2\nFinal."
        out, subs = apply_strip_patterns(text, patterns)
        assert subs == 2
        assert "WATERMARK" not in out

    def test_apply_no_patterns_returns_input_unchanged(self):
        text = "Body text"
        assert apply_strip_patterns(text, [])[0] == "Body text"

    def test_apply_empty_text_returns_zero(self):
        patterns = compile_strip_patterns([r"^X$"])
        out, subs = apply_strip_patterns("", patterns)
        assert out == ""
        assert subs == 0

    def test_apply_chains_patterns_in_order(self):
        patterns = compile_strip_patterns([r"^A$", r"^B$"])
        text = "A\nB\nKeep\nA\nB"
        out, subs = apply_strip_patterns(text, patterns)
        assert subs == 4
        assert "Keep" in out

    def test_default_timeout_constant_documented(self):
        # Operator-facing constant — 5s is the documented default in
        # `forgelm/_strip_pattern.py` + CLI help text.
        assert DEFAULT_TIMEOUT_S == 5


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
