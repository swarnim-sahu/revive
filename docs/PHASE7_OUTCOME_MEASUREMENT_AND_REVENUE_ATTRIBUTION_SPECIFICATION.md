# REVIVE — PHASE 7
# Outcome Measurement & Revenue Attribution Specification

**Version:** 1.0.0
**Phase:** 7 — Outcome Measurement & Revenue Attribution
**Status:** Final Specification — Implementation Complete
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Previous Phase:** Phase 6 — Execution & Workflow Engine

---

## 1. PURPOSE

Phase 7 closes the REVIVE intervention loop.

Phase 1–6 establish the ability to:
1. observe customer behavior,
2. estimate revenue risk,
3. diagnose observable risk conditions,
4. select a bounded intervention,
5. execute that intervention safely, and
6. maintain an auditable execution record.

Phase 7 determines what happened after execution and measures the resulting business outcome.

The core question is:

> Did the customer recover, what revenue was realized, and how much of that outcome can legitimately be attributed to the REVIVE intervention?

Phase 7 MUST distinguish observed outcome, temporal association, intervention-attributable outcome, incremental recovery, gross recovered revenue, intervention cost, and net recovered revenue.

A customer converting after an intervention MUST NOT automatically be interpreted as a customer converted because of the intervention.

---

## 2. PHASE 6 → PHASE 7 BOUNDARY

Phase 6 is responsible for accepting an authorized `InterventionDecision`, executing the selected action, enforcing execution safety, retries, escalation, cooldown, idempotency, test-mode isolation, and producing an execution audit record.

Phase 7 consumes the resulting execution record and observes subsequent customer/payment events.

Phase 7 MUST NOT modify the Phase 5 intervention decision, re-score the customer retrospectively, change the executed action, execute another intervention, use hidden ground-truth fields during runtime outcome measurement, or rewrite the original execution record.

```text
Phase 5
Intervention Decision
        |
        v
Phase 6
Execution + Audit
        |
        v
Phase 7
Outcome Observation
        |
        v
Outcome Resolution
        |
        v
Attribution
        |
        v
Revenue Measurement
```

---

## 3. CORE DESIGN PRINCIPLES

### 3.1 Temporal Integrity
Outcome measurement MUST occur after the relevant execution timestamp.

### 3.2 Evidence Grounding
Outcome classifications MUST be derived from observable events and authoritative payment-state information available at measurement time.

### 3.3 No Automatic Causality
Temporal ordering alone does not establish causal attribution.

```text
Intervention
    +
Conversion afterwards
```

is evidence of temporal association, not necessarily incremental causation.

### 3.4 Deterministic Resolution
Given identical execution records, observable events, payment-state inputs, attribution configuration, and measurement timestamps, Phase 7 MUST produce identical outcome and attribution results.

### 3.5 Auditability
Every outcome MUST be traceable to the evidence that caused its classification.

### 3.6 Conservative Attribution
When evidence is insufficient to establish attribution, Phase 7 MUST prefer `UNKNOWN` or `UNATTRIBUTED` over unsupported claims of recovery.

---

## 4. PHASE 7 INPUTS

Phase 7 consumes:

### 4.1 Execution Audit Records
Produced by Phase 6, including customer ID, execution ID, decision ID, intervention action, execution status, execution timestamp, attempt information, payload information where applicable, and execution result.

### 4.2 Observable Customer Events
Examples: payment attempted, payment failed, payment succeeded, subscription created, checkout started, checkout abandoned, feature usage, session activity.

### 4.3 Payment-System Events
In a future Razorpay integration, these may originate from Razorpay webhooks, Razorpay API verification, payment records, order state, and subscription state.

### 4.4 Revenue Information
Where available: payment amount, currency, captured amount, subscription value, applicable revenue-at-risk reference, and intervention cost.

---

## 5. EXTERNAL PAYMENT SYSTEM INTEGRATION

REVIVE MUST treat Razorpay as an external payment infrastructure/data source rather than as the intelligence layer.

```text
REVIVE
   |
   v
Razorpay
   |
   +---- Webhooks ----+
   |                  |
   +---- API ---------+
                      |
                      v
              Phase 7 Outcome
                 Ingestion
```

### 5.1 Webhooks
Razorpay webhook events SHOULD be the primary asynchronous mechanism for observing payment-state changes.

### 5.2 API Verification
Razorpay API queries MAY be used when immediate verification is required, webhook delivery is unavailable, an event requires authoritative state confirmation, or reconciliation is necessary.

### 5.3 Production Safety
The Phase 7 simulator MUST NOT contact production Razorpay endpoints. Live integration MUST remain an explicit future deployment concern.

---

## 6. OUTCOME TAXONOMY

Initial canonical outcomes:

| Outcome | Meaning |
|---|---|
| `RECOVERED` | Customer completed a qualifying recovery event after intervention |
| `CONVERTED` | Customer completed the qualifying subscription/conversion event |
| `NOT_RECOVERED` | Observation window completed without qualifying recovery |
| `EXPIRED` | Trial ended without qualifying recovery |
| `ALREADY_CONVERTED` | Customer was already converted before the intervention |
| `NO_OBSERVABLE_OUTCOME` | No sufficient outcome evidence exists |
| `UNKNOWN` | Evidence is contradictory or insufficient for deterministic classification |

The implementation MUST NOT collapse `UNKNOWN` into success or failure.

---

## 7. OUTCOME OBSERVATION WINDOWS

Each executed intervention MUST have a defined observation window.

The default Phase 7 implementation SHOULD support 24-hour, 72-hour, 7-day, and 14-day final observation windows.

Observation durations MUST be configuration-driven and MUST NOT be hard-coded throughout the codebase.

---

## 8. OUTCOME RESOLUTION

Outcome resolution MUST operate only on events occurring within the applicable observation window.

A payment that occurred before `T_execution` MUST NOT be classified as intervention recovery.

A payment occurring after the observation window MUST NOT retroactively alter a closed outcome unless the outcome is explicitly marked as provisional.

---

## 9. PRE-EXISTING OUTCOME PROTECTION

Before attributing any recovery, Phase 7 MUST determine whether the qualifying outcome already existed before execution.

```text
Payment succeeded
      |
      v
Intervention executed
```

This MUST NOT be classified as intervention recovery.

Such cases MUST be classified as `ALREADY_CONVERTED` or another appropriate non-attributable state.

---

## 10. OUTCOME EVIDENCE

Every resolved outcome MUST retain evidence references.

An outcome record SHOULD contain customer ID, execution ID, observation start, observation end, outcome type, evidence event IDs, evidence timestamps, payment identifiers where applicable, resolution timestamp, and resolver version.

The system MUST be able to explain why the outcome was assigned.

---

## 11. ATTRIBUTION MODEL

Phase 7 MUST explicitly separate:

### 11.1 Observed Outcome
What happened after execution.

### 11.2 Temporal Association
The outcome occurred after the intervention and inside the configured observation window.

### 11.3 Incremental Attribution
Evidence that the intervention caused an outcome that otherwise would not have occurred.

Only the first two can be established from temporal ordering alone. The third requires a counterfactual methodology.

---

## 12. INITIAL ATTRIBUTION LEVELS

Phase 7 SHOULD initially use:

```text
DIRECTLY_OBSERVED
TEMPORALLY_ASSOCIATED
ATTRIBUTION_SUPPORTED
ATTRIBUTION_UNCERTAIN
UNATTRIBUTED
```

The implementation MUST NOT represent `TEMPORALLY_ASSOCIATED` as definitively causal.

---

## 13. COUNTERFACTUAL / INCREMENTALITY MODEL

The conceptual quantity is:

```text
Incremental Recovery
=
Observed Outcome
-
Expected Counterfactual Outcome
```

The counterfactual represents the estimated outcome that would have occurred without the intervention.

Phase 7 MUST NOT claim causal impact solely from post-intervention conversion.

---

## 14. PHASE 7 INITIAL COUNTERFACTUAL STRATEGY

The initial implementation SHOULD remain conservative:

1. record observed outcomes,
2. record temporal association,
3. preserve intervention and customer context,
4. calculate attributable revenue only where the configured attribution rule permits it,
5. identify cases requiring future causal analysis.

Future versions MAY introduce randomized holdout groups, treatment/control cohorts, propensity-score methods, uplift modeling, heterogeneous treatment effect estimation, and causal inference models.

These are outside the initial deterministic implementation unless separately approved.

---

## 15. AI / ML BOUNDARY

### 15.1 Current AI/ML Component

Phase 3 already contains the primary predictive ML component:

```text
Revenue Risk Model
```

Its purpose is to predict the probability that a customer's future subscription revenue is at risk.

The existing model MUST remain the authoritative risk score provider.

### 15.2 Phase 7
Phase 7 MUST NOT use an LLM to determine whether revenue was recovered.

Outcome resolution MUST remain deterministic and evidence-based.

Attribution MUST initially use deterministic/statistical methods.

### 15.3 Future AI
Future versions MAY use machine learning for counterfactual estimation, treatment-effect estimation, uplift modeling, customer-response modeling, intervention effectiveness prediction, and outcome segmentation.

Any such model MUST be separately versioned and evaluated.

### 15.4 LLM Boundary
An LLM MAY eventually be used for analyst-facing explanations, summarization, natural-language reporting, and investigation assistance.

An LLM MUST NOT be authoritative for payment state, revenue amount, intervention authorization, execution, outcome classification, or causal attribution.

---

## 16. REVENUE MEASUREMENT

Phase 7 MUST distinguish:

### Gross Observed Revenue
Revenue actually observed after the intervention.

### Attributable Revenue
Revenue assigned to the intervention according to the configured attribution methodology.

### Intervention Cost
Direct cost associated with the intervention.

### Net Recovered Revenue

```text
Net Recovered Revenue
=
Attributable Revenue
-
Intervention Cost
```

The system MUST preserve all components rather than storing only the final net value.

---

## 17. REVENUE-AT-RISK RECONCILIATION

Phase 7 SHOULD retain the original Phase 3 revenue-at-risk value.

It MUST NOT rewrite the original prediction after observing the outcome.

```text
Predicted Revenue At Risk
             vs
Observed Revenue
             vs
Attributed Recovered Revenue
```

This creates a measurable evaluation boundary between prediction and realized business outcome.

---

## 18. INTERVENTION COST

The cost model MUST be explicit and configuration-driven.

Possible costs include direct execution cost, incentive cost, customer-friction penalty, payment recovery cost, and operational cost.

The implementation MUST NOT silently assume that all interventions have zero cost.

---

## 19. OUTCOME RECORD

A canonical Phase 7 outcome record SHOULD contain:

```text
customer_id
execution_id
decision_id
observation_start
observation_end
outcome
outcome_confidence
attribution_status
attribution_method
evidence_event_ids
payment_reference
gross_revenue
attributable_revenue
intervention_cost
net_recovered_revenue
revenue_at_risk_at_decision
resolution_timestamp
resolver_version
```

The exact schema is subject to implementation review.

---

## 20. AUDIT / LINEAGE

Phase 7 MUST preserve:

```text
Customer
   ↓
Risk Snapshot
   ↓
Diagnosis
   ↓
Intervention Decision
   ↓
Execution
   ↓
Observed Events
   ↓
Outcome
   ↓
Attribution
   ↓
Revenue
```

Every revenue attribution result MUST be traceable to its underlying evidence.

---

## 21. DETERMINISM

Given identical execution records, event records, payment-state inputs, configuration, and observation timestamps, Phase 7 MUST produce byte-for-byte equivalent serialized outcome records wherever serialization order is defined.

No wall-clock timestamps may be introduced into deterministic evaluation.

---

## 22. LEAKAGE PREVENTION

Runtime Phase 7 MUST NOT consume:

- `ground_truth.jsonl`
- `true_root_cause`
- `natural_conversion`
- `recoverable`
- hidden simulator outcome labels
- any other future-only simulator metadata unavailable in a real production environment.

Ground truth MAY be used by offline evaluation tooling, but MUST remain physically and logically separate from runtime outcome resolution.

---

## 23. EVALUATION METRICS

Phase 7 evaluation SHOULD report:

### Outcome Metrics
- outcome observation coverage,
- conversion rate,
- recovery rate,
- unresolved outcome rate.

### Attribution Metrics
- attributable outcome rate,
- attribution-supported rate,
- uncertain attribution rate,
- unattributed rate.

### Revenue Metrics
- gross observed revenue,
- attributable revenue,
- intervention cost,
- net recovered revenue,
- recovery efficiency,
- ROI.

### Prediction Evaluation
Where applicable:
- revenue-at-risk calibration,
- predicted vs realized revenue,
- recovery among predicted high-risk customers.

### Safety
- future information leakage rate,
- evidence completeness,
- lineage completeness,
- deterministic reproducibility.

---

## 24. OFFLINE GROUND-TRUTH EVALUATION

Offline evaluation MAY compare Phase 7 outputs against simulator ground truth.

Such evaluation MUST be clearly labeled `OFFLINE EVALUATION` and MUST NOT be confused with runtime outcome determination.

Runtime:

```text
Observable events → Outcome
```

Offline evaluation:

```text
Observable events + hidden ground truth → Evaluation
```

These are separate paths.

---

## 25. FAILURE HANDLING

Phase 7 MUST support missing events, duplicate events, contradictory payment states, delayed webhook delivery, missing payment references, incomplete customer linkage, partial observation windows, and unknown outcomes.

Failure MUST NOT silently become success.

---

## 26. IDEMPOTENCY

Processing the same execution/outcome input multiple times MUST NOT create duplicate outcome records.

Outcome resolution SHOULD be keyed by a stable identity derived from:

```text
customer_id
+
execution_id
+
observation_window
```

---

## 27. RECONCILIATION

Phase 7 SHOULD support reconciliation between:

```text
REVIVE observed payment events
        vs
Razorpay authoritative payment state
```

Discrepancies MUST be recorded rather than silently overwritten.

---

## 28. SECURITY

Payment identifiers and customer information MUST be handled as sensitive operational data.

The Phase 7 simulator MUST use synthetic payment references.

No production credentials may be committed to the repository.

No production Razorpay endpoint may be contacted by local evaluation scripts.

---

## 29. NON-GOALS

Phase 7 does NOT implement:

- new risk models,
- new diagnosis logic,
- intervention selection,
- intervention execution,
- live payment execution,
- automatic policy modification,
- automatic model retraining,
- autonomous LLM decision-making.

---

## 30. ACCEPTANCE CRITERIA

Phase 7 is complete only when:

1. Every executed intervention can be associated with an observation window.
2. Outcomes are resolved exclusively from allowed observable evidence.
3. Pre-existing outcomes cannot be falsely attributed.
4. Outcome resolution is deterministic.
5. Attribution is explicitly separated from temporal association.
6. Revenue attribution is separated from gross observed revenue.
7. Intervention costs are accounted for.
8. Net recovered revenue can be calculated.
9. Outcome lineage is complete.
10. Duplicate outcome processing is idempotent.
11. Unknown/ambiguous outcomes remain unresolved rather than being forced into success.
12. Runtime has zero hidden ground-truth leakage.
13. Offline evaluation remains separated from runtime measurement.
14. AI/ML does not become an uncontrolled authority over payment or attribution decisions.
15. Razorpay integration boundaries are explicitly isolated from the simulator.
16. Automated tests cover the complete Phase 7 contract.
17. Manual behavioral tests cover representative success, failure, ambiguity, attribution, and idempotency cases.
18. A 20,000-customer evaluation can be executed reproducibly.
19. Documentation matches the implemented behavior.
20. Git diff/checks are clean before Phase 7 closure.

---

## 31. PHASE 7 COMPLETION GATE

Phase 7 MUST NOT be considered complete merely because the tests pass.

Closure requires:

```text
Specification
      ↓
Implementation
      ↓
Automated Tests
      ↓
Manual Behavioral Tests
      ↓
20,000-Customer Evaluation
      ↓
Leakage Audit
      ↓
Attribution Audit
      ↓
Revenue Reconciliation
      ↓
Git Hygiene
      ↓
Commit
      ↓
Push
      ↓
Phase 7 CLOSED
```

---

## 32. FINAL ARCHITECTURAL PRINCIPLE

REVIVE MUST NOT claim:

> "The customer converted, therefore REVIVE recovered the revenue."

Instead:

> "REVIVE observed the outcome, established its temporal relationship to the intervention, applied an explicit attribution methodology, and reported only the revenue that the evidence and attribution model justify."

This distinction is fundamental to the credibility of the system.

---

# APPENDIX A — AI / ML ARCHITECTURE

The current REVIVE predictive AI component is the Phase 3 `risk_model.joblib`, implemented with scikit-learn.

```text
Customer behavior
       ↓
Feature engineering
       ↓
scikit-learn risk model
       ↓
Risk probability
       ↓
Revenue at risk
```

This is the authoritative predictive model in the current system.

An LLM is NOT part of the critical decision path. It MUST NOT be authoritative for risk authorization, diagnosis, intervention selection, execution, payment verification, outcome classification, revenue calculation, or causal attribution.

A future LLM MAY support analyst-facing explanations, summarization, natural-language reporting, and investigation assistance.

Once sufficient intervention/outcome data exists, REVIVE MAY introduce uplift modeling, treatment-effect estimation, counterfactual modeling, heterogeneous treatment effect estimation, and causal inference.

The initial Phase 7 implementation MUST NOT claim causal inference that the available data cannot support.

---

# APPENDIX B — RAZORPAY INTEGRATION ARCHITECTURE

Razorpay is an external payment infrastructure/data source, not the intelligence layer.

```text
                REVIVE
                   │
          ┌────────┴────────┐
          │                 │
       AI/ML              Policy
          │                 │
          └────────┬────────┘
                   ↓
               Execution
                   ↓
              RAZORPAY
                   ↓
        Webhooks / API state
                   ↓
              Phase 7
                   ↓
          Outcome + Revenue
```

Razorpay webhooks SHOULD be the primary asynchronous mechanism for observing payment-state changes.

Razorpay API queries MAY be used for immediate verification, webhook reconciliation, authoritative state confirmation, and payment/order/subscription lookup.

The simulator MUST use synthetic payment references and `sim://`-style endpoints. Production Razorpay endpoints MUST NOT be contacted by local tests or evaluation scripts.

The final separation is:

```text
AI predicts.
Rules decide.
Execution executes.
Razorpay processes payments.
Phase 7 measures outcomes.
Statistical/causal methods estimate incrementality.
```

---

## PHASE 7 STATUS

**Architecture:** Defined
**Implementation:** Complete
**Testing:** Complete (125 tests passed)
**Evaluation:** Complete (20,000 customers evaluated)
**Production Razorpay Integration:** Sandboxed / Simulated
**Phase Status:** FINAL — IMPLEMENTATION COMPLETE
