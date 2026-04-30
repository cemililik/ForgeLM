# CLAUDE.md — Project Guidance for AI Agents

> **Audience:** Claude Code (and other AI coding agents) working on ForgeLM. Complements — does not replace — the human-facing [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/standards/](docs/standards/).

## What ForgeLM is (in one line)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML in, fine-tuned model + compliance artifacts out. Built for CI/CD pipelines, not notebooks. Covers SFT → DPO → SimPO → KTO → ORPO → GRPO, with integrated safety evaluation, EU AI Act compliance, and auto-revert on quality regression.

Not a framework for training from scratch. Not an inference engine. Not a GUI. Read [docs/product_strategy.md](docs/product_strategy.md) for the 5-minute background.

## What you must read before editing code

**Every time, in this order:**

1. **[docs/standards/README.md](docs/standards/README.md)** — index of all engineering standards
2. **The specific standard** matching what you're about to change:
   - Python code → [coding.md](docs/standards/coding.md) + [architecture.md](docs/standards/architecture.md)
   - **Any `re.compile` / regex change → [regex.md](docs/standards/regex.md)** (ReDoS exposure, fixture fragmentation, the 8 hard rules distilled from Phase 11/11.5/12 review cycles)
   - Error paths → [error-handling.md](docs/standards/error-handling.md)
   - Anything with output → [logging-observability.md](docs/standards/logging-observability.md)
   - Tests → [testing.md](docs/standards/testing.md)
   - Docs → [documentation.md](docs/standards/documentation.md) + [localization.md](docs/standards/localization.md)
   - PR / review → [code-review.md](docs/standards/code-review.md)
   - Release → [release.md](docs/standards/release.md)
3. **[CONTRIBUTING.md](CONTRIBUTING.md)** — the human-facing summary
4. **The relevant roadmap file** — if implementing a planned phase, find it under [docs/roadmap/](docs/roadmap/)

Do not invent conventions. If you cannot find the pattern for what you're about to add, ask the user — don't guess.

## Skills

When a task maps to a common pattern, invoke the matching skill from [.claude/skills/](.claude/skills/):

| Task | Skill |
|---|---|
| Adding a YAML config field | [add-config-field](.claude/skills/add-config-field/SKILL.md) |
| Adding a larger trainer / evaluator / module feature | [add-trainer-feature](.claude/skills/add-trainer-feature/SKILL.md) |
| Writing tests | [add-test](.claude/skills/add-test/SKILL.md) |
| Updating bilingual docs (EN ↔ TR) | [sync-bilingual-docs](.claude/skills/sync-bilingual-docs/SKILL.md) |
| Reviewing a PR (own or peer) | [review-pr](.claude/skills/review-pr/SKILL.md) |
| Cutting a release | [cut-release](.claude/skills/cut-release/SKILL.md) |

Each skill's `SKILL.md` has the full checklist. Follow it; don't skip steps to save time.

## Repository structure at a glance

```
ForgeLM/
├── forgelm/                 # Source code (17 single-file modules)
│   ├── cli.py               # Entry point
│   ├── config.py            # Pydantic schemas (19 models)
│   ├── trainer.py           # TRL wrapper (SFT/DPO/SimPO/KTO/ORPO/GRPO)
│   ├── model.py             # HF + PEFT model loading
│   ├── data.py              # Dataset loading + format detection
│   ├── safety.py            # Llama Guard + harm categories + auto-revert
│   ├── compliance.py        # EU AI Act Articles 9-17 + Annex IV
│   ├── webhook.py           # Slack/Teams notifications
│   ├── grpo_rewards.py      # Built-in GRPO format/length shaping reward fallback
│   └── ...                  # benchmark, judge, merging, synthetic, wizard, ...
├── tests/                   # pytest, 47 test modules
├── docs/
│   ├── roadmap.md           # Public roadmap (short index)
│   ├── roadmap/             # Detailed phase files + archive
│   ├── reference/           # User-facing API/config reference
│   ├── guides/              # User-facing tutorials
│   ├── design/              # Design specs (internal)
│   ├── standards/           # Engineering standards (this project's rulebook)
│   ├── qms/                 # Quality management SOPs (EU AI Act Art. 17)
│   ├── analysis/            # Research, code reviews, external repo analyses
│   └── marketing/           # Local-only (gitignored): marketing + strategy
├── config_template.yaml     # Canonical YAML example — CI dry-runs this
├── pyproject.toml           # Build, deps, ruff, pytest, coverage config
├── CHANGELOG.md             # Keep-a-Changelog format
├── README.md                # User-facing project summary
├── CONTRIBUTING.md          # Human contributor guide
└── CLAUDE.md                # This file
```

## Non-negotiable project principles

These come from the standards documents; summarized here for quick reference:

1. **Config-driven.** Behaviour is determined by validated YAML. No env-var sniffing for behaviour (only for secrets). No hardcoded feature flags.
2. **Reliability before features.** Every new capability ships with tests, docs, and CI coverage. "I'll add tests later" = the PR is not ready.
3. **Optional dependencies as extras.** Heavy deps (`bitsandbytes`, `unsloth`, `deepspeed`, `lm-eval`, `wandb`, `mergekit`) live under `[project.optional-dependencies]` and raise `ImportError` with an install hint when missing.
4. **Exit codes are a public contract.** 0/1/2/3/4 — see [error-handling.md](docs/standards/error-handling.md). CI/CD pipelines depend on these.
5. **Append-only audit log.** Every decision gate emits a structured event. Never edit or delete entries.
6. **No silent failures.** No bare `except:`, no `except Exception: pass`, no `|| true` in CI, no logging-and-swallowing for anything except explicitly-non-fatal paths (webhooks, cleanup).
7. **Bilingual where it counts.** User-facing docs are EN + TR mirrors. Code, CLI output, logs, config keys are English only.
8. **Config-driven features are opt-in.** Enterprise features (compliance export, human approval, safety eval) are opt-in; new users aren't burdened.

## What ForgeLM is not

Reinforced in [docs/marketing/strategy/05-yapmayacaklarimiz.md](docs/marketing/strategy/05-yapmayacaklarimiz.md). Do not propose or implement:

- **Web UI / GUI.** Config-driven is the identity. Dashboard for Pro CLI only.
- **Custom inference engine.** Hand off to Ollama / vLLM / TGI / llama.cpp.
- **Custom model architectures.** HuggingFace owns that.
- **Custom quantization kernels.** bitsandbytes / AWQ / GPTQ / HQQ own that.
- **Pretraining pipelines.** Fine-tuning only.
- **GPU marketplace or serving infra.** User brings their own GPU.
- **LLM leaderboards or community adapter zoos.** HF Hub already exists.

If a task pushes in any of those directions, raise it with the user before implementing.

## Common pitfalls (from prior analysis)

Learned the hard way from [docs/analysis/QKV-Core/](docs/analysis/QKV-Core/) and [docs/analysis/Trion/](docs/analysis/Trion/) external-repo reviews:

- **Documentation drift** — marketing claims that code doesn't back up. Every README claim must point to real code.
- **Silent import fallbacks** — `try: import X; except: X = None` hides missing deps behind mysterious `AttributeError` later.
- **CI `|| true`** — fake green status. Outlawed.
- **Stub code tagged "Production Ready"** — `NotImplementedError("Planned for Phase N", issue=#42)` only, never silent stubs.
- **Single-language comment drift** — mixing Turkish + Spanish + English in code comments. English only in code.
- **Zero-byte or misplaced files** — leftover artifacts from refactors. Clean up.

## How to work on a task

Default workflow for a non-trivial change:

1. **Understand first.** Read the relevant standard. Read the similar existing code.
2. **Plan second.** If the task is multi-step, use `TodoWrite` to track your plan.
3. **Invoke the right skill.** If the task maps to one, follow the SKILL.md end-to-end.
4. **Code third.** Smallest possible diff. One concern per change.
5. **Test immediately.** Write the test before or alongside the code, never after merge.
6. **Verify before opening PR.** Run the self-review command:

   ```bash
   ruff format . && ruff check . && pytest tests/ && \
     forgelm --config config_template.yaml --dry-run
   ```

   All four must pass.

## Etiquette when communicating with the user

- **State results directly.** No filler like "Great question!" or "Let me help you with that."
- **Brief updates during work.** One sentence per tool call max. Silence is worse than terse.
- **Surface decision points.** If you encounter something that requires a judgement call beyond the stated task, stop and ask. Don't silently expand scope.
- **Flag trade-offs.** If your implementation picks A over B for non-obvious reasons, say so in your summary.
- **Turkish is welcome.** User writes in Turkish; respond in Turkish unless technical content is clearly cleaner in English. Code and file content: English only.

## When in doubt

1. Check the relevant [docs/standards/](docs/standards/) file.
2. Check for a matching skill in [.claude/skills/](.claude/skills/).
3. Find the closest existing pattern in the codebase and follow it.
4. Ask the user rather than guess.

## Memory and context

- The `docs/marketing/` directory is gitignored (internal strategy). Content there is real; treat it as a source of truth for direction but don't reference it in public-facing code or docs.
- The external-repo analyses under `docs/analysis/` are research artifacts. Cite them when explaining decisions, but the decisions themselves live in the standards.
- The roadmap ([docs/roadmap.md](docs/roadmap.md)) is what ships. The marketing strategy roadmap ([docs/marketing/marketing_strategy_roadmap.md](docs/marketing/marketing_strategy_roadmap.md)) is what gets announced. Don't conflate the two.

---

**If you've read this far and you're about to start work:** open the relevant standard + skill now. Then begin.
