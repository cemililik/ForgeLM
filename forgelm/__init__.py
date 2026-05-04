"""ForgeLM — config-driven, enterprise-grade LLM fine-tuning toolkit.

This is the package facade.  The CLI surface is exposed via the
``forgelm`` console script (and ``python -m forgelm.cli``); the Python
**library API** that integrators reach via ``from forgelm import ...``
is documented in
``docs/analysis/code_reviews/library-api-design-202605021414.md`` and
finalised here in Phase 19.

Lazy-import discipline (Phase 19):

- ``import forgelm`` is *cheap*: no torch, no transformers, no trl, no
  datasets at import time.  Only ``importlib.metadata`` and a tiny
  module-level state dict are touched.
- Heavy attributes (``ForgeTrainer``, ``audit_dataset``,
  ``setup_authentication``, etc.) are resolved on first attribute
  access via the module-level ``__getattr__`` hook (PEP 562); each
  resolved value is cached in ``globals()`` so subsequent accesses are
  zero-cost.
- ``dir(forgelm)`` lists the full public surface even before any
  attribute has been accessed (so IDE autocomplete + ``help(forgelm)``
  see every name immediately).

Stability tiers (per design §4):

- **Stable** symbols — semver-protected; signature changes require a
  major version bump of ``__api_version__`` (see
  :mod:`forgelm._version`).
- **Experimental** symbols — ``forgelm.WebhookNotifier`` etc.; surface
  may change without a major bump but operator copy in the design
  document calls out the lifecycle.
- **Internal** — anything not in ``__all__`` is internal and may
  change at any time.

PEP 561 type-hint distribution: the ``forgelm/py.typed`` marker file
ships in the wheel so ``mypy --strict`` / ``pyright`` consumers see
the in-source type hints without needing a separate stubs package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._version import __api_version__, __version__
from .config import ConfigError, ForgeConfig, load_config

# Public stable surface.  Order matches design §2.1 §4 tier listing
# (Stable first, then Experimental).  Anything absent from this list is
# internal — operators may import it but the package gives no
# stability guarantee.
__all__ = [
    # Versioning.
    "__version__",
    "__api_version__",
    # Configuration.
    "load_config",
    "ForgeConfig",
    "ConfigError",
    # Training entry point.
    "ForgeTrainer",
    "TrainResult",
    # Data preparation + audit.
    "prepare_dataset",
    "get_model_and_tokenizer",
    "audit_dataset",
    "AuditReport",
    # PII / secrets / dedup utility belt.
    "detect_pii",
    "mask_pii",
    "detect_secrets",
    "mask_secrets",
    "compute_simhash",
    # Compliance / audit log.
    "AuditLogger",
    "verify_audit_log",
    "VerifyResult",
    # Phase 36 verification toolbelt (library entries).
    "verify_annex_iv_artifact",
    "VerifyAnnexIVResult",
    "verify_gguf",
    "VerifyGgufResult",
    # Webhook notifier (experimental — surface may change).
    "WebhookNotifier",
    # Auxiliary.
    "setup_authentication",
    "manage_checkpoints",
    "run_benchmark",
    "BenchmarkResult",
    "SyntheticDataGenerator",
]


# Mapping from public symbol name → ``(submodule_path, attr_name)``.
# Centralised so adding a new lazy export is one row, the
# ``__getattr__`` hook stays a generic dispatcher, and ``__dir__`` can
# enumerate the surface without triggering imports.
_LAZY_SYMBOLS: dict[str, tuple[str, str]] = {
    "ForgeTrainer": ("forgelm.trainer", "ForgeTrainer"),
    "TrainResult": ("forgelm.results", "TrainResult"),
    "prepare_dataset": ("forgelm.data", "prepare_dataset"),
    "get_model_and_tokenizer": ("forgelm.model", "get_model_and_tokenizer"),
    "audit_dataset": ("forgelm.data_audit", "audit_dataset"),
    "AuditReport": ("forgelm.data_audit", "AuditReport"),
    "detect_pii": ("forgelm.data_audit", "detect_pii"),
    "mask_pii": ("forgelm.data_audit", "mask_pii"),
    "detect_secrets": ("forgelm.data_audit", "detect_secrets"),
    "mask_secrets": ("forgelm.data_audit", "mask_secrets"),
    "compute_simhash": ("forgelm.data_audit", "compute_simhash"),
    "AuditLogger": ("forgelm.compliance", "AuditLogger"),
    "verify_audit_log": ("forgelm.compliance", "verify_audit_log"),
    "VerifyResult": ("forgelm.compliance", "VerifyResult"),
    "verify_annex_iv_artifact": ("forgelm.cli.subcommands._verify_annex_iv", "verify_annex_iv_artifact"),
    "VerifyAnnexIVResult": ("forgelm.cli.subcommands._verify_annex_iv", "VerifyAnnexIVResult"),
    "verify_gguf": ("forgelm.cli.subcommands._verify_gguf", "verify_gguf"),
    "VerifyGgufResult": ("forgelm.cli.subcommands._verify_gguf", "VerifyGgufResult"),
    "WebhookNotifier": ("forgelm.webhook", "WebhookNotifier"),
    "setup_authentication": ("forgelm.utils", "setup_authentication"),
    "manage_checkpoints": ("forgelm.utils", "manage_checkpoints"),
    "run_benchmark": ("forgelm.benchmark", "run_benchmark"),
    "BenchmarkResult": ("forgelm.benchmark", "BenchmarkResult"),
    "SyntheticDataGenerator": ("forgelm.synthetic", "SyntheticDataGenerator"),
}


# ``TYPE_CHECKING`` is False at runtime so this block never executes;
# but type checkers (mypy, pyright) read it to understand the public
# surface without losing the lazy-import semantics.  Without these
# imports, ``mypy --strict`` on a downstream consumer's
# ``from forgelm import ForgeTrainer`` would raise "Module has no
# attribute ForgeTrainer" because the attribute is only synthesised at
# runtime via ``__getattr__``.
if TYPE_CHECKING:  # pragma: no cover — type-only imports
    from .benchmark import BenchmarkResult, run_benchmark  # noqa: F401
    from .cli.subcommands._verify_annex_iv import (  # noqa: F401
        VerifyAnnexIVResult,
        verify_annex_iv_artifact,
    )
    from .cli.subcommands._verify_gguf import VerifyGgufResult, verify_gguf  # noqa: F401
    from .compliance import AuditLogger, VerifyResult, verify_audit_log  # noqa: F401
    from .data import prepare_dataset  # noqa: F401
    from .data_audit import (  # noqa: F401
        AuditReport,
        audit_dataset,
        compute_simhash,
        detect_pii,
        detect_secrets,
        mask_pii,
        mask_secrets,
    )
    from .model import get_model_and_tokenizer  # noqa: F401
    from .results import TrainResult  # noqa: F401
    from .synthetic import SyntheticDataGenerator  # noqa: F401
    from .trainer import ForgeTrainer  # noqa: F401
    from .utils import manage_checkpoints, setup_authentication  # noqa: F401
    from .webhook import WebhookNotifier  # noqa: F401


def __getattr__(name: str):
    """PEP 562 lazy attribute resolver for the public surface.

    Looks ``name`` up in :data:`_LAZY_SYMBOLS`, imports the source
    submodule, fetches the attribute, and caches the result back into
    the module's ``globals()`` so subsequent accesses skip this hook
    entirely (zero-cost after first touch).  Anything not in the
    lazy-symbols table raises :class:`AttributeError` so typos surface
    as ``AttributeError: module 'forgelm' has no attribute 'XYZ'``
    instead of a confusing ``ImportError`` deep in the resolver.
    """
    target = _LAZY_SYMBOLS.get(name)
    if target is None:
        raise AttributeError(f"module 'forgelm' has no attribute {name!r}")
    module_path, attr_name = target
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, attr_name)
    # Cache the resolved value so the hook never fires again for this
    # name.  globals() write is intentional — it's the documented PEP
    # 562 mechanism for one-shot lazy resolution.
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Surface the full public API in ``dir(forgelm)`` even before any
    attribute has been accessed.  Important for IDE autocomplete and
    ``help(forgelm)`` discovery.
    """
    # Combine the eager-resolved names + the lazy-symbols catalogue.
    # ``__all__`` is the source of truth.
    return sorted(set(__all__) | set(globals().keys()))
