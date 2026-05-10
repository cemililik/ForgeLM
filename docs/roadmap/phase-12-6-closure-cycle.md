# Phase 12.6 — Closure Cycle (38 fazlar across 5 waves)

> **Status:** ✅ Done — Faz 33 release publish remains as POST-WAVE.
> **Bundled into:** [v0.5.5 release](releases.md#v055-closure-cycle-bundle-phase-22-wizard-site-documentation-sweep-2026-05-10).
> **Source review:** v0.5.0 master code review (175 findings: 8 Critical + 67 Major + 60 Minor + 40 Nit) — distilled into the Faz 1-38 task list below.
> **Target:** ★★★★★ across all 8 quality dimensions before v0.5.5 PyPI publish.

## Why this exists as a single phase entry

The v0.5.0 master code review surfaced **175 findings** plus **4 user-added scope items** (Library API support, ISO 27001 / SOC 2 alignment, GDPR right-to-erasure full implementation, Article 14 real staging). Rather than stretch these across 5 sequential patch releases, the maintainer chose **Path B — full Faz 1-38 sweep into a single v0.5.5 tag**:

- Bisectable PR-per-faz history
- One coherent surface (every faz feeds the same release candidate)
- 5/5 quality bar reached before publish, not after

The 38 fazlar were merged across **5 integration waves** (Wave 0/1 through Wave 5). Each wave landed via a dedicated PR onto `development`, then into `main`. This file is the index that maps every faz to its wave, integration PR, and merge SHA.

## Scope (in / out)

**In scope:**

- All 175 master-review findings (Critical → Nit)
- 4 user-added scope items: Library API, ISO 27001 / SOC 2, GDPR full implementation, Article 14 real staging + `forgelm approve`
- 5 ghost-feature drift items surfaced during Wave 4 + 5 (GH-001 doctor, GH-002/003 air-gap pre-cache, GH-004/005/009 verification toolbelt, GH-007 approvals listing, GH-014 reverse-pii)
- Documentation final pass: `docs/` EN+TR, `docs/usermanuals/{en,tr}/`, `site/*`, all 10 standards files, README + CONTRIBUTING + CLAUDE.md, roadmap + roadmap-tr.md

**Explicitly out of scope:**

- DE / FR / ES / ZH user-manual translation (deferred to a future cycle — bilingual policy formalised in [`docs/standards/localization.md`](../standards/localization.md))
- Cloud SaaS product (separate offering)
- New roadmap features: Phase 13 (Pro CLI) and Phase 14 (Pipeline Chains) work
- Marketing / GTM expansion

## Wave timeline

| Wave | Branch | Integration PR | Merge SHA | Date | Net new tests |
|---|---|---|---|---|---|
| **Wave 0** (foundation) | `closure/wave1-integration` (early bundle) | PR #19 → `main` | (see PR #19) | 2026-04-30 | baseline |
| **Wave 1** (foundation residuals) | `closure/wave1-integration` (continuation) | PR #21 → `development` | (see PR #21) | 2026-05-02 | +0 (refactor) |
| **Wave 2a** | `closure/wave2a-integration` | PR #28 → `development` | (see PR #28) | 2026-05-04 | → 1160 |
| **Wave 2b** | `closure/wave2b-integration` | PR #30 → `development` | `b05edb5` | 2026-05-05 | 1160 → 1298 (+138) |
| **Wave 3** | `closure/wave3-integration` | PR #31 → `development` | `b87c872` | 2026-05-05 | 1298 → 1374 (+76) |
| **Wave 4** | `closure/wave4-integration` | PR #33 → `development` | `01e40ba` | 2026-05-06 | 1374 → 1411 (+37) |
| **Wave 5** | `closure/wave5-integration` | PR #34 → `development` merged `8f9f951` | `8f9f951` | 2026-05-06 | 1411 → ~1442 (+31) |
| **Faz 33** (POST-WAVE) | release commit | tag `v0.5.5` → `main` | (post-Wave-5) | TBD | n/a |

## Faz inventory (38 entries)

| # | Faz | Wave | Status |
|---|---|---|---|
| 1 | Site & doc honesty + count drift sweep | Wave 0 (PR #19) | ✅ |
| 2 | CI gates & standards drift cleanup | Wave 0 (PR #19) | ✅ |
| 3 | Operator identity + audit forensic completeness | Wave 0 (PR #19) | ✅ |
| 4 | Performance: lazy torch + safety/judge batching + paragraph chunker | Wave 0 (PR #19) | ✅ |
| 5 | Notebook PyPI pin + nightly grep guard | Wave 0 (PR #19) | ✅ |
| 6 | `forgelm verify-audit` subcommand + library function | Wave 0 (PR #19) | ✅ |
| 7 | `safe_post` HTTP discipline extension | Wave 0 (PR #19) | ✅ |
| 8 | Webhook lifecycle vocabulary | Wave 0 (PR #19) | ✅ |
| 9 | Article 14: honesty fix + real staging + `forgelm approve` | Wave 1 | ✅ |
| 10 | Pydantic Literal sweep (6 remaining fields) | Wave 1 | ✅ |
| 11 | Wizard `_print` indirection + drop coverage omit | Wave 1 | ✅ |
| 12 | Fixture consolidation (`tests/_helpers/`) | Wave 1 | ✅ |
| 13 | `--data-audit` deprecation discipline | Wave 1 | ✅ |
| 14 | `data_audit/` package split (5-PR series D-1..D-5) | Wave 1 | ✅ |
| 15 | `cli/` package split (6-PR series C-1..C-6) | Wave 1 | ✅ |
| 16 | Pydantic `description=` migration with CI guard (4 PR) | Wave 2b (PR #30) | ✅ |
| 17 | `--workers N` audit determinism | Wave 2a (PR #28) | ✅ |
| 18 | Library API support — Analysis & design | Wave 2a (PR #28) | ✅ |
| 19 | Library API support — Implementation | Wave 2b (PR #30) | ✅ |
| 20 | GDPR right-to-erasure — Analysis & design | Wave 2a (PR #28) | ✅ |
| 21 | GDPR right-to-erasure — Implementation | Wave 2b (PR #30) | ✅ |
| 22 | ISO 27001 / SOC 2 Type II — Analysis & gap assessment | Wave 4 (PR #33) | ✅ |
| 23 | ISO 27001 / SOC 2 Type II — Implementation | Wave 4 (PR #33) | ✅ |
| 24 | Bilingual TR mirror sweep + `tools/check_bilingual_parity.py` | Wave 3 (PR #31) | ✅ |
| 25 | Site picker honesty + site-as-tested-surface CI guard | Wave 1 | ✅ |
| 26 | QMS bilingual EN+TR mirror + `tools/check_anchor_resolution.py` | Wave 4 (PR #33) | ✅ |
| 27 | Silent `except Exception:` sweep | Wave 1 | ✅ |
| 28 | Remaining Major + Minor cleanup | Wave 3 (PR #31) | ✅ |
| 29 | Nit sweep (40-item mass-edit) | Wave 1 | ✅ |
| 30 | Final documentation + site finalization (EN+TR only) | Wave 4 partial + Wave 5 full sweep | ✅ |
| 31 | Cross-OS release-tag matrix workflow | Wave 1 | ✅ |
| 32 | `.pre-commit-config.yaml` (optional) | Wave 1 | ✅ |
| 33 | **v0.5.5 RELEASE** (CHANGELOG, version bump, tag, PyPI) | POST-WAVE | ⏳ |
| 34 | `forgelm doctor` env-check subcommand (GH-001) | Wave 2a (PR #28) | ✅ |
| 35 | Air-gap pre-cache (`cache-models` + `cache-tasks`) (GH-002, GH-003) | Wave 2b (PR #30) | ✅ |
| 36 | Compliance verification toolbelt (`safety-eval`, `verify-annex-iv`, `verify-gguf`) (GH-004/005/009) | Wave 2b (PR #30) | ✅ |
| 37 | `forgelm approvals` listing subcommand (GH-007) | Wave 2a (PR #28) | ✅ |
| 38 | `forgelm reverse-pii` GDPR Article 15 subcommand (GH-014) | Wave 3 (PR #31) | ✅ |

**Total:** 38 fazlar / ~52 PRs (multi-PR series counted separately).

## Wave-by-wave outcomes

### Wave 0 / 1 (PR #19, PR #21)

Foundation + the bulk of the master-review backlog — fazlar 1-15, 25, 27, 29, 31, 32. Site honesty fixes, CI gates, audit log forensic completeness, performance pass, the two big package splits (`data_audit/` 5-PR series, `cli/` 6-PR series).

### Wave 2a (PR #28, 2026-05-04)

5 fazlar: 17 (`audit --workers N`), 18 (Library API design), 20 (GDPR design), 34 (`doctor`), 37 (`approvals`).

### Wave 2b (PR #30, 2026-05-05, merge `b05edb5`)

5 fazlar: 16 (Pydantic `description=` migration), 19 (Library API implementation), 21 (GDPR erasure implementation), 35 (air-gap pre-cache), 36 (compliance verification toolbelt). Suite 1160 → 1298 (+138). 6 absorption rounds + 4-agent final review + 4 followup absorption commits.

### Wave 3 (PR #31, 2026-05-05, merge `b87c872`)

3 fazlar: 24 (bilingual TR mirror sweep + `tools/check_bilingual_parity.py`), 28 (curated Tier 1+2 cleanup), 38 (`reverse-pii`). Suite 1298 → 1374 (+76). Behaviour changes: high-risk + unacceptable + safety-disabled now `ConfigError` (F-compliance-110); webhook timeout 5s → 10s default (F-compliance-106).

### Wave 4 (PR #33, 2026-05-06, merge `01e40ba`)

4 fazlar: 22 + 23 (ISO 27001 / SOC 2 alignment design + implementation), 26 (QMS bilingual mirror + `tools/check_anchor_resolution.py` + `compliance_summary.md` rewrite), 30 partial (Tier 1 ghost-feature drift + stat blocks). Suite 1374 → 1411 (+37: 16 supply-chain + 21 anchor checker). Bilingual parity scope 9/9 → 23/23 pairs.

### Wave 5 (PR #34 merged `8f9f951`, 2026-05-06)

Faz 30 full sweep: residual ghost-feature drift (GH-011 benchmarks, GH-016 `--export-bundle`, GH-018 deploy-targets `kserve`/`triton`, GH-020 ingest flag drift); Task A doc-triplet completion (~12 features × {guide, reference, usermanual} × {EN, TR} ≈ 50 new files — landed in commit `2a32842`); Task J `tools/check_cli_help_consistency.py` (commit `c7bedc9`); Task N anchor-checker `--strict` flip + 36-baseline cleanup (commit `fbb082d`); Tasks B/C `_meta.yaml` + `build_usermanuals.py` rebuild; Task D site/* finalization; Tasks E/F/G README + CONTRIBUTING + CLAUDE + roadmap + standards final pass; Tasks H/I/K/L/M parity strict + site-claim CI + config regen + locale policy + diagrams.

### Faz 33 (POST-WAVE)

The actual v0.5.5 PyPI publish:

1. `pyproject.toml` `version = "0.5.5"` — already bumped during Wave 5 Task D (`4610dc6`) so `check_site_claims.py --strict` can pin the site → code version parity. Faz 33 only confirms it remains `0.5.5` and adds the date to the `[0.5.5]` CHANGELOG section.
2. CHANGELOG `[Unreleased]` → `[0.5.5] — YYYY-MM-DD`
3. `git tag -s v0.5.5 -m "v0.5.5 — Closure Cycle Bundle"`
4. `git push origin main v0.5.5`
5. `publish.yml` runs: build → cross-OS matrix (12 combos) → publish (OIDC trusted publishing, no API token)

The cut-release skill ([`.claude/skills/cut-release/SKILL.md`](../../.claude/skills/cut-release/SKILL.md)) walks the maintainer through the sequence step-by-step.

## Quality dimensions reached

Per the closure plan §1 baseline + §9 exit criteria:

| Dimension | Pre-Wave-0 | Post-Wave-5 target |
|---|---|---|
| Business | ★★★½ | ★★★★★ |
| Code | ★★★½ | ★★★★★ |
| Compliance | ★★★★ | ★★★★★ |
| Documentation | ★★★½ | ★★★★★ |
| Localization | ★★★ | ★★★★★ (EN+TR; DE/FR/ES/ZH user-manual deferred by user decision) |
| Performance | ★★★★ | ★★★★★ |
| Security | ★★★★ | ★★★★★ |
| Testing & CI/CD | ★★★½ | ★★★★★ |

## Related

- [`releases.md`](releases.md) — v0.5.5 release notes
- [`risks-and-decisions.md`](risks-and-decisions.md) — closure-cycle decision log entries
- [`CHANGELOG.md`](../../CHANGELOG.md) — `[0.5.5]` section (finalized at release; per-PR closure entries collapse into the v0.5.5 release notes)
