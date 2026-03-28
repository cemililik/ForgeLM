# SOP: Change Management for AI Models

> Standard Operating Procedure — [YOUR ORGANIZATION]
> EU AI Act Reference: Article 17(1)(b)(c)

## 1. Purpose

Define the procedure for managing changes to fine-tuned models, training configurations, and evaluation criteria.

## 2. Change Categories

| Category | Examples | Approval Required |
|----------|---------|------------------|
| **Major** | New base model, new trainer type, risk category change | AI Officer + ML Lead |
| **Minor** | Hyperparameter tuning, LoRA rank change, dataset update | ML Lead |
| **Patch** | Bug fix, config formatting, documentation | ML Engineer (self-approve) |

## 3. Change Procedure

### 3.1 Propose

1. Create a branch from `development`: `git checkout -b change/description development`
2. Modify the training config (YAML)
3. Document the change rationale in the PR description
4. Run dry-run: `forgelm --config new_config.yaml --dry-run`

### 3.2 Review

1. Open a Pull Request against `development` (release PRs go to `main`)
2. PR must include:
   - [ ] Config diff showing what changed
   - [ ] Rationale for the change
   - [ ] Expected impact on model quality/safety
   - [ ] For **Major** changes: updated risk assessment
3. Reviewer checks:
   - [ ] Config validates (`--dry-run` passes)
   - [ ] Safety evaluation enabled (for high-risk models)
   - [ ] No secrets or tokens in config

### 3.3 Execute

1. Merge PR (requires approval per branch protection rules)
2. CI/CD pipeline triggers training: `forgelm --config job.yaml`
3. ForgeLM auto-generates compliance artifacts for the new run
4. New `audit_log.jsonl` entries trace the change

### 3.4 Validate

1. Compare new model metrics against previous version
2. Review benchmark scores, safety scores, judge scores
3. If `require_human_approval: true`: explicit approval before deployment

### 3.5 Rollback

If the new model is worse:
- ForgeLM `auto_revert` handles automatic rollback during training
- For post-deployment rollback:
  1. Redeploy previous model version
  2. Document rollback in incident log
  3. Investigate root cause

## 4. Version Tracking

Every training run produces:
- `compliance_report.json` with ForgeLM version, config hash, timestamps
- `model_integrity.json` with artifact SHA-256 checksums
- `audit_log.jsonl` with full event history

Use these to trace any model back to its exact training configuration and data.

## 5. Review

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [DATE] | [AUTHOR] | Initial version |
