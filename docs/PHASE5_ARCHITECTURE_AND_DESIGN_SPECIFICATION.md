# REVIVE — Phase 5 Architecture and Design Specification
## Intervention Decision Engine

**Version:** 1.0.0  
**Phase:** 5 — Intervention & Action Decision Engine  
**Status:** Implementation Specification  
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`  
**Package Path:** `app/intervention/`  

---

## 1. Overview & Objective

Phase 5 answers:
> **"Given the customer's current revenue risk and observable root-cause diagnosis, should REVIVE intervene, and if so, which bounded intervention should it select?"**

Phase 5 produces a deterministic, side-effect-free decision object (`InterventionDecision`). It does **not** call Razorpay APIs, send customer communications, modify database states, or execute real-world actions.

---

## 2. Inputs & Forbidden Fields

### Permitted Inputs
- Phase 3 risk score, `revenue_at_risk`, `risk_tier`, `prediction_timestamp`
- Phase 4 `CustomerDiagnosis` (`diagnosis`, `confidence`, `actionability`, `supporting_evidence`)
- Observable customer journey and plan data available $\le T_{\text{prediction}} = 72\text{h}$

### Forbidden Fields (Runtime Inference)
- `ground_truth.jsonl`
- `true_root_cause`, `generation_segment`, `natural_conversion`
- `conversion_after_intervention`, `recoverable`, `maximum_recoverable_revenue`
- Any event timestamp $> T_{\text{prediction}}$

---

## 3. Intervention Taxonomy

The engine evaluates 7 bounded actions (`app/intervention/schemas.py`):
1. **`NO_ACTION`**: Non-intervention baseline.
2. **`PRODUCT_GUIDANCE`**: In-app tooltip or feature walkthrough.
3. **`REMINDER`**: Email/SMS trial or activity prompt.
4. **`CHECKOUT_ASSISTANCE`**: Pre-filled checkout link / plan selection help.
5. **`PAYMENT_RECOVERY`**: Payment failure notification & alternate retry link.
6. **`TRIAL_EXTENSION`**: Grant 3-day trial extension.
7. **`HUMAN_REVIEW`**: Flag high-value ambiguous cases for Merchant Success Queue.

---

## 4. Deterministic Eligibility & Safety Rules

### Eligibility Gates
- **`NO_ACTION`**: `risk_score < 0.30` OR `diagnosis == ALREADY_CONVERTED` OR `diagnosis == INSUFFICIENT_EVIDENCE` OR `actionability == Actionability.NONE`.
- **`HUMAN_REVIEW`**: `revenue_at_risk >= ₹2,500.00` AND (`diagnosis == MIXED_SIGNALS` OR `actionability == REQUIRES_REVIEW`). High revenue alone does NOT trigger human review.
- **Active Eligibility**: `risk_score >= 0.30` AND `actionability == Actionability.CANDIDATE` AND `confidence >= 0.30`.

### Safety Rules (Contraindications)
- **S1 (No Double Conversion):** `ALREADY_CONVERTED` customers are strictly barred from active interventions.
- **S2 (Payment Evidence Required):** `PAYMENT_RECOVERY` requires `PAYMENT_FAILURE` or `PAYMENT_ATTEMPT` evidence.
- **S3 (Checkout Evidence Required):** `CHECKOUT_ASSISTANCE` requires `CHECKOUT_STARTED` evidence.
- **S4 (Trial Extension Timing):** `TRIAL_EXTENSION` is barred if hours until expiry $> 48\text{h}$.
- **S5 (Positive Expected Value):** Active interventions are barred if Expected Value ($EV$) $\le 0.0$.

---

## 5. Deterministic Expected Value & Tie-Breaking

For candidate action $a$:

$$EV(a) = \left[ P_{\text{recovery\_assumption}}(a \mid \text{diag}, c) \times \text{revenue\_at\_risk} \right] - C_{\text{direct}}(a) - \text{incentive\_penalty\_assumption}(a) - C_{\text{harm\_assumption}}(a \mid \text{diag}, c)$$

- **`recovery_probability_assumption`**: Versioned simulation assumptions (`assumption_version = "v1.0.0"`), not empirical probabilities.
- **`incentive_penalty_assumption`**: Configurable economic penalty assumption for trial extension/discount actions (e.g., 10% of plan price).
- **Tie-Breaking:** If $|EV(a_1) - EV(a_2)| < 0.01$, select lower direct cost action, then alphabetical order.

---

## 6. Evaluation Funnel

Offline evaluator (`scripts/evaluate_interventions.py`) reports a 10-stage decision funnel:
1. Total Population
2. At-Risk Population ($\ge 0.30$)
3. Diagnosable/Actionable Population
4. Eligible Intervention Population
5. `NO_ACTION` Count & Rate
6. `HUMAN_REVIEW` Count & Rate
7. Automated Intervention Count & Rate
8. Per-Action Distribution
9. Safety Policy Compliance Rate ($100\%$)
10. Evidence-Action Consistency Rate ($100\%$)
