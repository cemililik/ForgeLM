# Localization Standard

> **Scope:** Which parts of ForgeLM get translated, how translations are paired with originals, and what stays English only.
> **Enforced by:** Review + (future) CI script checking `-tr.md` ↔ `.md` structural sync.

## The policy in one line

**User-facing documentation is bilingual (EN + TR). Code, CLI output, config keys, logs, and internal dev docs are English only.**

## Supported languages

- **EN + TR (authored).** All user-facing docs and user-manual pages are written and reviewed in both English and Turkish. EN+TR mirror parity is mandatory for the doc tree — see "Structural mirror rule" below.
- **DE / FR / ES / ZH (site UI translated; user-manual content English-fallback).** The site language picker exposes all six languages, and `site/js/translations.js` carries the marketing/product copy in DE/FR/ES/ZH. The user-manual content (`docs/usermanuals/...`) is **only authored in EN + TR**; when a deferred-language user picks DE/FR/ES/ZH, the manual side falls back to English via the i18n chain (`tableForLang(...) → DEFAULT='en'`). `tools/build_usermanuals.py` therefore emits JS bags only for the authored set (`en`, `tr`); the deferred languages reuse the EN bag through the fallback path.

A language is "site-translated" when its strings live in `site/js/translations.js`. A language is "manual-authored" only when `docs/usermanuals/<lang>/` content is reviewed by a native or near-native speaker.

Rationale:

- ForgeLM's market includes a significant Turkish-speaking segment (banking + regulatory + research) served by Turkish-language docs.
- Code in multiple languages fragments the community beyond a ceiling that ForgeLM doesn't need to cross.
- Tooling (ruff, pytest, HF error messages) is English; forcing localized mixing creates confusion.

## What's translated

| Path | TR mirror? | Reason |
|---|---|---|
| `README.md` | Yes (`README.md` has TR section inline or separate file) | Entry point |
| `docs/product_strategy.md` | Yes | Stakeholder-facing vision |
| `docs/roadmap.md` | Yes | Public planning |
| `docs/reference/architecture.md` | Yes | End-user architecture reference |
| `docs/reference/configuration.md` | Yes | End-user config reference |
| `docs/reference/usage.md` | Yes | End-user how-to |
| `docs/reference/data_preparation.md` | Yes | End-user data prep |
| `docs/reference/distributed_training.md` | Yes | End-user distributed |
| `docs/reference/compliance_summary.md` | No (yet) | English only for now — Turkish translation planned as Phase 10 task |
| `docs/guides/*.md` | No (yet) | Turkish guides are an open task |
| `docs/design/*.md` | No | Internal design history |
| `docs/standards/*.md` | No | Contributor-facing |
| `docs/qms/*.md` | No | QMS templates in English (regulated orgs translate internally) |
| `docs/marketing/**` | Mixed (strategy/ is TR, operational is EN) | Local-only; author's choice |
| `docs/analysis/**` | Mixed | Analysis documents in whichever language suits the source |
| `docs/roadmap/**` | No (yet) | English only; TR mirror summary at `docs/roadmap-tr.md` |

Anything not in the "Yes" set is **English only**. Don't translate preemptively.

## File naming

**Pattern:** `<name>.md` (English) paired with `<name>-tr.md` (Turkish) in the same directory.

- ✅ `configuration.md` + `configuration-tr.md`
- ❌ `configuration.en.md` + `configuration.tr.md`
- ❌ `configuration.md` + `yapilandirma.md`

Rationale: simpler to search, simpler to CI-check sync, consistent with what exists.

## Structural mirror rule

TR mirrors must have the **same sections, in the same order, with the same number of sections** as their EN counterpart. Two reasons:

1. A reader switching languages should find the same content in the same place.
2. CI (future) can check "does every EN heading have a TR heading?" as a cheap drift detector.

**What may differ:**

- Wording within a section.
- Idioms and examples adapted for Turkish readers.
- Small TR-specific notes (e.g., BDDK / KVKK references) in a dedicated subsection.

**What must match:**

- H1 title corresponds (`# ForgeLM Roadmap` ↔ `# ForgeLM Yol Haritası`).
- H2 count and order.
- Tables of contents, lists of files, and rule lists.
- Code blocks (content is language-neutral).
- Links (same targets, wrapped in TR link text).

## What to do when the EN doc changes

| EN change | TR action |
|---|---|
| Typo fix or wording tweak | Optional: update TR for parity if obvious |
| Section added | **Required:** add matching section to TR in same PR |
| Section removed | **Required:** remove matching section from TR in same PR |
| Structural reorganization | **Required:** restructure TR in same PR |
| Link target changed (file moved) | **Required:** update TR link target in same PR |

If you can't do the TR update in the same PR (e.g., you don't write Turkish), open a tracking issue labeled `translation-debt` and reference it in the PR. This is a non-blocking exception that the reviewer decides on.

## CLI and code

**English only.** Specifically:

- All `logger.info/warning/error` messages
- All `argparse` help strings
- All user-facing exception messages
- All docstrings
- All YAML config keys (`trainer_type`, not `egitici_turu`)
- All JSON output field names

**Reason:** CLI is the UX that Ahmet and Sarah (our two primary personas from [marketing/04_personas.md](../marketing/04_personas.md)) share. MLOps engineers worldwide read English errors. CLI strings are the single most viral part of the tool — screenshots, stackoverflow, LLM training data.

Exception: wizard prompts may be translated if ever we ship a localized wizard, but that's behind a `--lang=tr` flag and not the default. Currently not planned.

## Terminology

For the parts we do translate, keep terminology consistent. A small glossary:

| English | Turkish | Notes |
|---|---|---|
| fine-tuning | ince ayar | Preferred over "ince-ayarlama" |
| training | eğitim | |
| model | model | Cognate |
| config / configuration | yapılandırma / config | Either; prefer "yapılandırma" in prose, `config` in code references |
| pipeline | boru hattı / pipeline | Either; prefer transliterated "pipeline" in dev-heavy docs |
| safety evaluation | güvenlik değerlendirmesi | |
| audit trail | denetim izi | |
| compliance | uyumluluk | |
| quantization | quantization | Not commonly translated |
| attention | dikkat | |
| layer (ML) | katman | |
| tokenizer | tokenleştirici / tokenizer | Either; technical audiences prefer "tokenizer" |
| LoRA / PEFT / etc. | unchanged | Acronyms |
| EU AI Act | AB Yapay Zekâ Yasası / EU AI Act | First mention spell it out, then abbreviate |

When in doubt, look at sibling TR docs and match the most frequent choice. Don't invent new terminology mid-series.

## Quality bar for Turkish

The audience is technical. Priorities:

1. **Correct information** (same facts as EN).
2. **Plain, technical Turkish.** Not literary. Not Osmanlı.
3. **Transliterated technical terms where Turkish equivalents are awkward.** "Pipeline çalıştır" reads better than "boru hattını çalıştırın" in a CLI doc.
4. **No machine-translation output.** Google Translate / DeepL output pasted without review is worse than English only. If you can't rewrite a machine-translated passage into natural Turkish, don't add it.

## When a Turkish reader encounters English content

Link from the TR doc back to the EN with "bu konunun detayı (İngilizce):" (details in English). Don't translate placeholder content just to avoid the English link.

## Future (not today)

- Spanish translations — not planned for 2026. The marketing docs mention a Spanish-speaking contributor but Spanish market entry isn't in roadmap.
- Localized CLI output behind a language flag — not planned.
- Automatic translation in CI — not trustworthy enough, doesn't save review time.

If a new language becomes strategic, update this document first, then start translations.
