"""Phase 11.5 wizard guards: keep the wizard's view of supported document
extensions in lockstep with the ingestion module.

The wizard duplicates :data:`forgelm.ingestion.SUPPORTED_EXTENSIONS` as
``forgelm.wizard._INGEST_SUPPORTED_EXTENSIONS`` so the directory-pre-check
inside :func:`forgelm.wizard._directory_has_ingestible_files` does not pay
the ingestion module's import cost when the user is bringing a JSONL straight
in. That duplication is silent drift waiting to happen — this test fails
loudly if a future change to ``SUPPORTED_EXTENSIONS`` does not also touch
the wizard copy.
"""

from __future__ import annotations

from forgelm import ingestion, wizard


def test_wizard_extensions_match_ingestion() -> None:
    assert set(wizard._INGEST_SUPPORTED_EXTENSIONS) == set(ingestion.SUPPORTED_EXTENSIONS), (
        "forgelm.wizard._INGEST_SUPPORTED_EXTENSIONS drifted from "
        "forgelm.ingestion.SUPPORTED_EXTENSIONS — keep them in sync or "
        "import directly."
    )
