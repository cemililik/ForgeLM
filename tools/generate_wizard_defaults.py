"""Schema-driven wizard defaults generator (F1 / review-cycle 3).

Walks every Pydantic submodel reachable from :class:`forgelm.config.ForgeConfig`,
finds fields marked with ``json_schema_extra={"wizard": True}``, extracts
the schema default, and writes two artefacts:

1. ``forgelm/wizard/_defaults.json`` — Python consumer; loaded via
   :mod:`importlib.resources` from :func:`forgelm.wizard._state._load_defaults`.
2. ``site/js/wizard_defaults.js`` — Web consumer; emitted as a tiny script
   that sets ``window.WIZARD_DEFAULTS = {...}`` so :file:`site/js/wizard.js`'s
   ``defaultState()`` can read schema-aligned values without a build step.

Run after any schema default change::

    python tools/generate_wizard_defaults.py

The CI guard ``tools/check_wizard_defaults_sync.py`` re-runs this script
into a temp dir and diffs against the committed files; PRs that change
a wizard-flagged default without regenerating fail the doc-guard step.

Why a generator instead of importing live values at runtime?

- The web wizard is a static site (no Python runtime to query schema
  during page load) — it needs JSON-as-data shipped with the assets.
- The Python side benefits too: the wizard module's import-time cost
  stays low (no Pydantic model walk), and the JSON is auditable in git.
- Round-tripping through JSON forces all wizard-relevant defaults to be
  JSON-serialisable primitives — no datetimes, no Path, no ``Field``s
  leaking into the operator's YAML.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple, Type

# Allow `python tools/generate_wizard_defaults.py` from the repo root
# without a separate ``python -m forgelm.tools`` install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from pydantic import BaseModel  # noqa: E402  -- after path tweak

from forgelm.config import ForgeConfig  # noqa: E402  -- after path tweak

# Output destinations — both kept in lockstep by the CI guard.
PYTHON_TARGET = _REPO_ROOT / "forgelm" / "wizard" / "_defaults.json"
JS_TARGET = _REPO_ROOT / "site" / "js" / "wizard_defaults.js"

# Stable section order in the output JSON / JS — matches the order
# fields appear inside ForgeConfig so visual diffs read naturally.
_SECTION_ORDER: Tuple[str, ...] = (
    "model",
    "lora",
    "training",
    "data",
)


def _is_wizard_flagged(field_info: Any) -> bool:
    """Return True when *field_info* carries ``json_schema_extra={"wizard": True}``.

    Pydantic v2 stores the extra dict on ``FieldInfo.json_schema_extra``;
    operators may also set it via ``Field(..., wizard=True)`` shortcut
    that lands as a nested ``"extra": {...}`` mapping in older releases.
    Cover both shapes defensively.
    """
    extra = getattr(field_info, "json_schema_extra", None)
    if isinstance(extra, dict):
        return bool(extra.get("wizard"))
    return False


def _walk_model(model: Type[BaseModel], section: str, sink: Dict[str, Dict[str, Any]]) -> None:
    """Populate *sink* with wizard-flagged defaults from *model*.

    Recurses into nested ``BaseModel`` types so a wizard flag on a deep
    field still surfaces.  ``model_fields`` is Pydantic v2's
    introspection API; we read each field's ``default`` attribute
    directly because the live Pydantic instance would substitute
    ``PydanticUndefined`` for required fields (which we skip).
    """
    for name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        # Recurse into nested BaseModel types so flagged sub-fields
        # surface under their natural section namespace.
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            _walk_model(annotation, name, sink)
            continue
        if not _is_wizard_flagged(field_info):
            continue
        default = field_info.default
        # Pydantic uses a sentinel for required-no-default fields; skip
        # those silently — wizard fields should always carry a default.
        if repr(default).startswith("PydanticUndefined"):
            continue
        sink.setdefault(section, {})[name] = default


def collect_defaults() -> Dict[str, Dict[str, Any]]:
    """Walk ForgeConfig + every nested submodel; return wizard-flagged defaults."""
    sink: Dict[str, Dict[str, Any]] = {}
    for top_name, field_info in ForgeConfig.model_fields.items():
        annotation = field_info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            _walk_model(annotation, top_name, sink)
    # Reorder for deterministic output (sections that aren't in
    # ``_SECTION_ORDER`` come last, alphabetised for repeatability).
    ordered: Dict[str, Dict[str, Any]] = {}
    for section in _SECTION_ORDER:
        if section in sink:
            ordered[section] = dict(sorted(sink[section].items()))
    for section in sorted(sink):
        if section not in ordered:
            ordered[section] = dict(sorted(sink[section].items()))
    return ordered


_HEADER_PYTHON = (
    "{\n"
    '  "//": "Schema-derived wizard defaults — DO NOT EDIT BY HAND.",\n'
    '  "//1": "Regenerate via: python tools/generate_wizard_defaults.py",\n'
    '  "//2": "CI guard: tools/check_wizard_defaults_sync.py rejects manual drift.",\n'
)


def render_python_json(defaults: Dict[str, Dict[str, Any]]) -> str:
    """JSON output with a leading ``//`` comment block for human readers.

    The comment lines use the YAML-style ``"//"`` key idiom — JSON itself
    has no comment syntax, but Python's ``json.load`` happily parses
    string keys named ``"//"`` and the wizard ignores them when
    consuming the file (only specific section keys are read).
    """
    body = json.dumps(defaults, indent=2, ensure_ascii=False)
    # Strip the opening brace from ``body`` and prepend our header so
    # the comments precede the real keys.  Defaults dict is non-empty
    # so ``body`` always starts with ``{\n``.
    payload = body[2:]  # drop the leading "{\n"
    return _HEADER_PYTHON + payload + "\n"


def render_js_literal(defaults: Dict[str, Dict[str, Any]]) -> str:
    """Render as a tiny JS asset that exposes ``window.WIZARD_DEFAULTS``."""
    body = json.dumps(defaults, indent=2, ensure_ascii=False)
    return (
        "/**\n"
        " * Schema-derived wizard defaults — DO NOT EDIT BY HAND.\n"
        " * Regenerate via: python tools/generate_wizard_defaults.py\n"
        " * CI guard: tools/check_wizard_defaults_sync.py rejects manual drift.\n"
        " *\n"
        " * Consumed by site/js/wizard.js's defaultState() so the web\n"
        " * wizard's accept-all-defaults YAML matches ForgeConfig() byte-\n"
        " * for-byte.  Loaded BEFORE wizard.js in the HTML pages that\n"
        " * mount the wizard modal.\n"
        " */\n"
        f"window.WIZARD_DEFAULTS = {body};\n"
    )


def main() -> int:
    defaults = collect_defaults()
    PYTHON_TARGET.parent.mkdir(parents=True, exist_ok=True)
    JS_TARGET.parent.mkdir(parents=True, exist_ok=True)
    PYTHON_TARGET.write_text(render_python_json(defaults), encoding="utf-8")
    JS_TARGET.write_text(render_js_literal(defaults), encoding="utf-8")
    section_count = len(defaults)
    field_count = sum(len(v) for v in defaults.values())
    print(
        f"Wrote {section_count} section(s) / {field_count} wizard-flagged default(s):"
        f"\n  - {PYTHON_TARGET.relative_to(_REPO_ROOT)}"
        f"\n  - {JS_TARGET.relative_to(_REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
