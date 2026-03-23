# SOP: Incident Response for AI Models

> Standard Operating Procedure — [YOUR ORGANIZATION]
> EU AI Act Reference: Article 17(1)(h)(i)

## 1. Purpose

Define the procedure for handling safety incidents, model failures, and corrective actions for deployed fine-tuned models.

## 2. Incident Classification

| Severity | Definition | Response Time | Example |
|----------|-----------|--------------|---------|
| **Critical** | Model produces harmful, discriminatory, or dangerous output | Immediate (< 1 hour) | Safety classifier failure, harmful content generation |
| **High** | Model produces incorrect output affecting business decisions | < 4 hours | Wrong policy information, incorrect financial data |
| **Medium** | Model quality degradation detected | < 24 hours | Accuracy drop below threshold, increased hallucination |
| **Low** | Minor quality issue, cosmetic | < 1 week | Formatting errors, occasional irrelevant responses |

## 3. Incident Response Procedure

### 3.1 Detection

Incidents may be detected by:
- Runtime monitoring alerts (if `monitoring.alert_on_drift: true`)
- User/deployer reports
- Periodic quality audits
- ForgeLM webhook failure notifications

### 3.2 Immediate Actions

**For Critical/High:**
1. [ ] **Stop**: Remove model from production or switch to fallback
2. [ ] **Document**: Record incident details (input, output, timestamp, impact)
3. [ ] **Notify**: Alert AI Officer and affected stakeholders
4. [ ] **Preserve**: Save model artifacts and logs for investigation

### 3.3 Investigation

1. [ ] Reproduce the issue with the reported input
2. [ ] Check `audit_log.jsonl` for training run details
3. [ ] Review `safety_results.json` from the original training
4. [ ] Compare model behavior against baseline
5. [ ] Identify root cause (data issue, training issue, deployment issue)

### 3.4 Corrective Action

| Root Cause | Action |
|-----------|--------|
| Training data issue | Fix data → retrain → re-evaluate → redeploy |
| Safety regression | Revert to previous model version |
| Configuration error | Fix config → retrain with corrected parameters |
| Deployment error | Fix deployment, model is fine |

### 3.5 Post-Incident

1. [ ] Document root cause and resolution
2. [ ] Update risk assessment if new risks identified
3. [ ] Update safety test prompts to cover the incident scenario
4. [ ] Review and update this SOP if needed
5. [ ] For EU AI Act: report serious incidents to relevant authority within **15 days**

## 4. Serious Incident Reporting (EU AI Act)

Under Article 73, providers must report serious incidents to market surveillance authorities. A "serious incident" includes:
- Death or serious damage to health
- Serious infringement of fundamental rights
- Serious disruption to critical infrastructure

**Report to:** National market surveillance authority of the affected EU member state
**Timeline:** Within 15 days of becoming aware

## 5. Review

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [DATE] | [AUTHOR] | Initial version |
