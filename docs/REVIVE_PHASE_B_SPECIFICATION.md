# REVIVE — Phase B Specification
## Controlled High-Volume Evaluation, Decision Accuracy & Incremental Revenue Proof

**Version:** 1.0.0
**Phase:** B — Controlled High-Volume Evaluation & Revenue Proof
**Status:** SPECIFICATION FOR IMPLEMENTATION
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Dependency:** Phase A complete and live-verified
**Primary objective:** Prove REVIVE creates measurable incremental revenue at batch scale while preserving decision quality, safety, throughput, and transparent exception handling.

---

## 1. Executive Objective

Phase B converts REVIVE from a system that can execute and measure an individual recovery into a system that can **prove, at scale, that its decisions create economic value**.

The official Razorpay AI Buildathon Track 03 currently states that the bar is not merely identifying revenue loss; the builder must show **measured money recovered across a batch**, with **compliant escalation, stopping rules, and an audit trail**.

Source of truth:
- https://razorpay.com/buildathon/

Phase B therefore has five proof obligations:

1. **High-volume processing** — process a large, reproducible batch.
2. **Decision quality** — quantify diagnosis/decision correctness instead of calling every successful outcome “AI accuracy”.
3. **Economic value** — compare REVIVE against a clearly defined control/baseline and report incremental revenue.
4. **Safety/governance** — demonstrate stop, no-action, escalation, eligibility, and exception behavior.
5. **Operational transparency** — expose throughput, failures, retries, and unresolved cases rather than hiding them.

---

# 2. Current-State Grounding

The existing REVIVE evaluator already provides a deterministic batch pipeline and reuses the existing Phase 1–9 components. The current `BatchRecoveryEvaluator` supports configurable customer counts and seeds, generates synthetic journeys, loads the risk model, uses the existing diagnosis/AI/intervention/execution components, and can report expected and measured recovery. The current CLI defaults to 100 customers and writes an optional JSON result. The existing evaluator also uses the mock AI provider and mock Razorpay dispatcher for offline deterministic evaluation.

Relevant existing locations:
- `app/evaluation/batch.py`
- `scripts/evaluate_batch_recovery.py`
- `app/simulation/*`
- `app/evaluation/*`
- `app/risk/*`
- `app/diagnosis/*`
- `app/ai/*`
- `app/intervention/*`
- `app/execution/*`
- `app/outcome/*`

The current simulator already maintains hidden ground-truth records containing:
- `generation_segment`
- `natural_conversion`
- `conversion_after_intervention`
- `recoverable`
- `maximum_recoverable_revenue`
- `true_root_cause`

These fields are explicitly hidden from observable runtime inference and may only be used for **post-hoc evaluation/scoring**, never for treatment decisions.

The existing simulation has already been demonstrated at 20,000 customers in prior project validation, with a fixed seed and a large event volume. Phase B must build on that capability rather than reinventing the simulator.

---

# 3. Non-Goals

Phase B is **not**:

- another Razorpay integration phase;
- a replacement for the live Razorpay Phase A proof;
- a requirement to perform thousands of real Razorpay payments;
- a redesign of Risk, Diagnosis, AI, Intervention, Execution, or Outcome engines;
- a frontend/dashboard redesign;
- a requirement to introduce Redis, Kafka, a production database, or distributed infrastructure;
- a claim that synthetic results equal production results;
- permission to expose hidden simulator ground truth to the agent at inference time.

The single real Razorpay Payment Link → webhook → recovered-revenue proof remains the **real-world infrastructure demonstration**. Phase B supplies the **scale/economic evaluation proof**.

---

# 4. Core Experimental Design

## 4.1 Target cohort

The primary Phase B benchmark is:

- **20,000 total journeys**
- **10,000 Control**
- **10,000 REVIVE Treatment**

The implementation MUST keep cohort size configurable so smaller smoke tests can be run before the full benchmark.

Recommended execution levels:

- Smoke: 100 journeys
- Validation: 1,000 journeys
- Benchmark: 20,000 journeys

The benchmark is the formal Phase B acceptance run.

---

## 4.2 Fairness requirement

The control and treatment comparison must be based on the **same underlying customer population**, not two independently generated populations with different random draws.

Use a deterministic shared cohort or paired-customer design:

```text
Seeded population
       ↓
same customer / plan / initial observable journey
       ↓
 ┌───────────────┬────────────────┐
 │ CONTROL       │ REVIVE         │
 │ baseline      │ AI + policy    │
 │ experience    │ intervention   │
 └───────────────┴────────────────┘
       ↓
different counterfactual treatment path
       ↓
same evaluation horizon
```

The experiment must record a stable `case_id`/`customer_id` so that every treatment case has a corresponding control case.

---

# 5. Control Definition

The control represents what would happen **without REVIVE intervention**.

Control must not:

- receive REVIVE-generated interventions;
- benefit from REVIVE's AI decision;
- have its conversion outcome rewritten by the treatment logic.

The control conversion outcome must be based on the hidden counterfactual `natural_conversion` after the observation horizon.

Control revenue is therefore the baseline revenue that would have occurred without REVIVE.

At minimum, each control case must expose:

- `control_converted`
- `control_gross_revenue`
- `control_net_revenue`
- `control_revenue_at_risk`
- `control_case_status`

---

# 6. REVIVE Treatment Definition

Every treatment journey must pass through the existing REVIVE decision chain:

```text
Synthetic observable journey
        ↓
Risk
        ↓
Diagnosis
        ↓
AI layer / evidence synthesis
        ↓
Intervention candidate evaluation
        ↓
Policy / eligibility gates
        ↓
Selected action
        ↓
Execution simulation
        ↓
Outcome observation
        ↓
Attribution / revenue accounting
```

The treatment decision MUST NOT use hidden ground truth.

Ground truth is permitted only after the decision/treatment is finalized, for evaluation.

---

# 7. Treatment Outcome Semantics

The evaluation must distinguish:

### A. Natural conversion

A customer who would have converted without REVIVE.

This is **not incremental recovery**, even if the treatment path also converts.

This is the existing simulator's `natural_conversion` concept.

### B. Incremental recovery opportunity

A customer for whom:

```text
conversion_after_intervention = True
AND
natural_conversion = False
```

The existing simulator defines this as:

```text
recoverable = True
```

This represents the true incremental-revenue opportunity.

### C. Non-recoverable case

A customer that would not convert naturally and would not convert following an appropriate intervention.

No recovered revenue should be attributed.

### D. No-action / safely stopped case

Cases where REVIVE correctly chooses not to intervene because intervention is unnecessary, unsafe, uneconomical, unsupported, already converted, or otherwise blocked by policy.

These MUST NOT be counted as AI failures simply because no intervention occurred.

---

# 8. Primary Economic Metrics

The Phase B report MUST include both absolute and comparative economics.

## 8.1 Control metrics

- Control customer count
- Control conversion rate
- Control gross revenue
- Control net revenue
- Control revenue-at-risk total

## 8.2 Treatment metrics

- Treatment customer count
- Treatment conversion rate
- Treatment gross observed revenue
- Treatment attributable revenue
- Treatment intervention cost
- Treatment net recovered revenue
- Treatment expected recovery
- Treatment measured recovery

## 8.3 Incremental value metrics

### Incremental conversion

```text
Treatment conversion rate
−
Control conversion rate
```

### Incremental revenue

```text
Treatment realized/attributable revenue
−
Control baseline revenue
```

### Incremental recoverable revenue captured

For cases with hidden `recoverable = True`:

```text
Recovered attributable revenue
/
Maximum recoverable revenue
```

### Recovery lift

Report both percentage-point lift and relative lift where meaningful.

### ROI

At minimum:

```text
(Net treatment value − control baseline value)
/
Treatment intervention cost
```

Any ROI definition used in the output MUST be documented with its numerator/denominator and must not double-count gross revenue and net revenue.

---

# 9. Critical Anti-Cherry-Picking Rule

The benchmark report MUST present:

- all 20,000 cases in the primary aggregate;
- control and treatment side by side;
- every case-level outcome category;
- failures and exceptions.

It is NOT acceptable to report only successful REVIVE recoveries.

The benchmark MUST NOT filter out inconvenient cases before computing headline metrics.

Any secondary filtered analysis MUST state its filter and retain the unfiltered primary result.

---

# 10. Decision Accuracy Metrics

“AI accuracy” MUST NOT be a single ambiguous number.

Phase B must separately report:

## 10.1 Diagnosis accuracy

Compare Phase 4 predicted diagnosis with hidden `true_root_cause` mapped through the existing diagnosis evaluator.

Required:

- overall accuracy;
- macro precision;
- macro recall;
- macro F1;
- per-class metrics;
- confusion matrix;
- insufficient-evidence/uncertainty rate.

The existing `DiagnosisEvaluator` already provides the basis for this type of measurement.

## 10.2 Intervention appropriateness

For each non-NO_ACTION decision, determine whether the selected action is compatible with the diagnosed/root-cause context and existing safety/evidence rules.

Report:

- appropriate intervention rate;
- inappropriate intervention rate;
- unnecessary intervention rate;
- safety-policy violation rate.

Do NOT define an intervention as “correct” merely because money was eventually recovered.

## 10.3 No-action correctness

Report cases where REVIVE chose:

```text
NO_ACTION
```

or another safe stop/escalation path and compare that result with the hidden counterfactual.

This is required because a good recovery agent must know when **not** to intervene.

---

# 11. Decision Funnel

Phase B MUST retain and aggregate the existing decision funnel.

At minimum:

1. Total population
2. At-risk population
3. Diagnosable/actionable population
4. Eligible intervention population
5. NO_ACTION count/rate
6. HUMAN_REVIEW count/rate
7. Automated intervention count/rate
8. Safety policy compliance rate
9. Evidence-action consistency rate
10. Execution success/failure
11. Outcome resolution
12. Attributable recovery

The existing Phase 5 evaluator already establishes a bounded action taxonomy and safety checks.

Current bounded actions include:

- `NO_ACTION`
- `PRODUCT_GUIDANCE`
- `REMINDER`
- `CHECKOUT_ASSISTANCE`
- `PAYMENT_RECOVERY`
- `TRIAL_EXTENSION`
- `HUMAN_REVIEW`

These must not be expanded merely to improve benchmark numbers.

---

# 12. Safety, Stopping & Escalation

Phase B MUST explicitly measure governance behavior.

Required metrics:

- stop/no-action rate;
- human escalation rate;
- blocked/ineligible action rate;
- cooldown cases;
- unsafe action attempts;
- unnecessary intervention rate;
- execution failure rate;
- retryable failure count;
- terminal failure count.

The benchmark MUST demonstrate that:

```text
low confidence
    → uncertainty / stop / escalation

high-value ambiguous case
    → human review where existing policy requires it

already converted
    → no active recovery intervention

insufficient evidence
    → no unjustified action

negative/non-positive EV
    → no active intervention
```

Existing Phase 5 safety rules remain authoritative.

---

# 13. Exception & Failure Report

Every case that does not complete the normal treatment path MUST be classifiable.

Required exception categories include at minimum:

- generation failure;
- invalid input;
- missing model artifact;
- risk evaluation failure;
- diagnosis failure;
- AI failure;
- AI fallback;
- intervention evaluation failure;
- policy block;
- execution failure;
- outcome measurement failure;
- attribution failure;
- unresolved/unknown.

Each exception record MUST contain:

```text
case_id
stage
status
failure_type
retryable
safe_action_taken
financial_impact
human_escalation_required
reason
```

No exception may simply disappear from the final benchmark.

---

# 14. Throughput & Performance Measurement

Phase B MUST measure operational scale.

Required:

- total cases;
- total events processed;
- total runtime;
- cases/second;
- events/second;
- average case latency;
- p95 case latency if practical;
- stage-level latency where practical;
- peak in-memory footprint if practical;
- failures per 1,000 cases.

Throughput MUST be calculated from actual wall-clock benchmark execution, not estimated from a smaller run.

The benchmark must record:

```text
start_time
end_time
elapsed_seconds
customers_processed
events_processed
cases_per_second
events_per_second
```

---

# 15. Deterministic Reproducibility

A benchmark run must be reproducible.

Every result must record:

- experiment ID;
- seed;
- total population;
- control count;
- treatment count;
- simulator version;
- policy version;
- assumption version;
- risk model artifact/version;
- Python version;
- package/environment metadata where practical;
- benchmark timestamp;
- code/git revision if available.

Running the benchmark twice with the same deterministic configuration MUST produce equivalent aggregate results.

Any intentionally nondeterministic component MUST be explicitly identified and isolated.

---

# 16. AI Layer Integrity

Phase B is an evaluation phase, not permission to replace the existing AI architecture.

The evaluator MUST distinguish:

```text
AI-generated/AI-assisted decision
```

from:

```text
deterministic policy enforcement
```

The final report must make clear which layer produced each signal.

The current offline batch evaluator uses a mock AI provider for deterministic tests. Phase B may continue to use the deterministic mock AI path for the benchmark **unless the implementation specification explicitly establishes a separate real-model benchmark**.

No network-based LLM call is required for the 20,000-case benchmark.

Do not convert the benchmark into a hidden API-cost experiment.

---

# 17. Ground-Truth Isolation

The following fields MUST NEVER enter the treatment decision path:

```text
generation_segment
natural_conversion
conversion_after_intervention
recoverable
maximum_recoverable_revenue
true_root_cause
```

They may be retained in an offline evaluation-only structure and used after the treatment decision is complete.

The final public-facing benchmark artifact MUST separate:

```text
observable decision evidence
```

from:

```text
hidden evaluation labels
```

A reviewer should be able to see what REVIVE knew when it made the decision.

---

# 18. Batch Result Schema

Phase B should produce a structured benchmark result with at least:

```text
experiment_metadata
control_summary
treatment_summary
incremental_value_summary
decision_accuracy_summary
decision_funnel
safety_summary
exception_summary
throughput_summary
outcome_distribution
attribution_distribution
per_case_results
```

Per-case records should include only fields necessary for audit/evaluation and MUST NOT expose simulator secrets/ground truth as observable runtime inputs.

---

# 19. Required Comparison Table

The final benchmark report MUST contain a compact comparison similar to:

| Metric | Control | REVIVE | Increment / Lift |
|---|---:|---:|---:|
| Cases | 10,000 | 10,000 | — |
| Conversion rate | … | … | … |
| Gross revenue | … | … | … |
| Intervention cost | ₹0 | … | … |
| Net revenue | … | … | … |
| Attributable recovery | — | … | … |
| Incremental revenue | — | — | … |
| Unnecessary intervention rate | — | … | … |
| Escalation rate | — | … | … |
| Safety compliance | — | … | … |

Exact values must be produced by the benchmark rather than hardcoded.

---

# 20. Required “Exception Ledger”

The final output MUST include a separate machine-readable and human-readable exception ledger.

Example:

```text
Case       Stage          Status       Retryable   Action
cus_0012   Diagnosis      FAILED       yes         retry
cus_0048   Intervention   BLOCKED      no          NO_ACTION
cus_0081   Execution      FAILED       yes         retry
cus_0127   Outcome        UNRESOLVED    no          HUMAN_REVIEW
```

The ledger must reconcile with aggregate counts.

For example:

```text
Total cases
=
successful cases
+
stopped cases
+
escalated cases
+
failed cases
+
unresolved cases
```

No double counting.

---

# 21. Required Financial Reconciliation

The benchmark MUST satisfy accounting checks.

At minimum:

```text
control revenue
+
treatment incremental revenue
=
combined economic comparison
```

and within treatment:

```text
gross observed revenue
−
intervention cost
=
net treatment revenue
```

Any difference between:

- gross observed revenue,
- attributable revenue,
- recovered revenue,
- net recovered revenue,
- incremental revenue

must have a documented reason.

Do not label all observed post-treatment payments as incremental recovery.

The existing Outcome/Attribution engine remains authoritative for attributable revenue.

---

# 22. Performance Acceptance Targets

Phase B should establish **measured** performance rather than arbitrary claims.

The implementation MUST support:

- at least 20,000 total cases;
- a complete control/treatment comparison;
- a structured per-case result;
- exception accounting;
- deterministic re-run;
- machine-readable output;
- throughput calculation.

No hard minimum recovery lift should be hardcoded into the product merely to “pass” the benchmark.

The benchmark is successful when it produces credible evidence.

A negative or weak economic result MUST remain visible rather than being suppressed.

---

# 23. Expected Deliverables

Implementation of Phase B is expected to produce:

1. A controlled experiment runner.
2. A deterministic 20,000-case benchmark mode.
3. Control and treatment evaluation.
4. Incremental revenue metrics.
5. Decision/diagnosis accuracy metrics.
6. Safety/stop/escalation metrics.
7. Throughput metrics.
8. Exception ledger.
9. Machine-readable benchmark JSON.
10. Human-readable benchmark report.
11. Deterministic regression tests.
12. Documentation explaining how to reproduce the benchmark.

A dashboard UI change is not required for Phase B unless it becomes necessary to expose the benchmark evidence.

---

# 24. Frozen Boundaries

Unless an implementation review proves an existing defect requires a narrowly scoped change, do NOT modify:

```text
app/risk/*
app/diagnosis/*
app/ai/*
app/intervention/*
app/execution/*
app/outcome/*
frontend/*
REVIVE_BUILD_CONSTITUTION.md
```

Phase B should primarily extend the **evaluation/orchestration/reporting layer**.

Potentially affected areas may include:

```text
app/evaluation/*
scripts/*
tests/*
docs/*
```

and only other files demonstrated to be necessary.

The existing production Razorpay integration from Phase A is considered frozen for this phase.

---

# 25. Testing Strategy

Before running the 20,000-case benchmark, implementation must support deterministic tests at small scale.

Required testing levels:

### Unit / component tests

Validate:

- control/treatment assignment;
- metric calculations;
- reconciliation;
- exception classification;
- throughput measurement;
- result serialization.

### Small integration test

Run a deterministic cohort such as:

```text
100 cases
50 control
50 treatment
```

and verify all accounting identities.

### Reproducibility test

Run the same small experiment twice with the same seed and verify equivalent results.

### Benchmark test

Run:

```text
20,000 total
10,000 control
10,000 treatment
```

and verify successful completion.

The benchmark MUST NOT be the only test.

---

# 26. Benchmark CLI Requirements

The exact CLI design is an implementation decision, but the final system MUST support a command equivalent to:

```bash
py scripts/run_phase_b_evaluation.py \
    --customers 20000 \
    --control 10000 \
    --treatment 10000 \
    --seed 42 \
    --output reports/phase_b/
```

The command should produce at least:

```text
reports/phase_b/
    experiment.json
    summary.json
    cases.jsonl
    exceptions.jsonl
    report.md
```

Exact filenames may vary during implementation if the same capabilities are preserved.

---

# 27. Required Human-Readable Report Sections

The generated report MUST contain:

1. Experiment definition.
2. Population and cohort counts.
3. Control vs REVIVE results.
4. Incremental revenue.
5. Decision/diagnosis accuracy.
6. Intervention distribution.
7. Safety and governance.
8. Outcome/attribution distribution.
9. Exception ledger summary.
10. Throughput.
11. Reproducibility metadata.
12. Financial reconciliation.
13. Limitations and interpretation.

The report should answer, in one place:

> “How much better did REVIVE do than doing nothing, how confident are we in its decisions, how safely did it operate, and what happened to the cases it could not resolve?”

---

# 28. Evidence Hierarchy

Phase B results MUST distinguish:

### Level 1 — Deterministic unit evidence
Tests that individual calculations and policies behave correctly.

### Level 2 — Batch synthetic evidence
20,000-case control/treatment benchmark.

### Level 3 — Real infrastructure evidence
Phase A live Razorpay Test Mode recovery proof.

Do not present the synthetic benchmark as if it were live merchant production performance.

The final story is:

```text
Real payment infrastructure proof
+
large-scale controlled synthetic proof
=
credible end-to-end evidence
```

---

# 29. Review Gates Before Phase B Closure

Phase B cannot be marked CLOSED until all are true:

- [ ] 20,000-case benchmark completes.
- [ ] Control = 10,000 and treatment = 10,000.
- [ ] Same deterministic population underlies both groups.
- [ ] REVIVE treatment uses no hidden ground truth.
- [ ] Diagnosis accuracy is reported separately from intervention success.
- [ ] Incremental revenue vs control is reported.
- [ ] Intervention cost is included.
- [ ] Unnecessary intervention rate is reported.
- [ ] Stop/no-action behavior is reported.
- [ ] Escalation behavior is reported.
- [ ] All exceptions are accounted for.
- [ ] Throughput is measured from actual runtime.
- [ ] Repeated deterministic runs are reproducible.
- [ ] Machine-readable and human-readable reports are produced.
- [ ] Financial reconciliation passes.
- [ ] Existing Phase 1–A behavior remains regression-safe.
- [ ] No frozen engine was modified without explicit justification.

---

# 30. Phase B Closure Evidence

The final implementation report MUST include:

```text
Experiment ID
Seed
Population
Control population
Treatment population

Control conversion
Treatment conversion
Conversion lift

Control revenue
Treatment revenue
Incremental revenue

Revenue at risk
Expected recovery
Measured recovery
Attributable recovery
Intervention cost
Net recovery

Diagnosis accuracy
Precision / Recall / F1

Intervention appropriateness
Unnecessary intervention rate

Safety compliance
Stop rate
Escalation rate

Exceptions
Retryable failures
Terminal failures
Unresolved cases

Total runtime
Cases/sec
Events/sec

Reproducibility verification
Regression test result
```

No hardcoded benchmark result may be embedded in code.

---

# 31. Implementation Workflow

This specification is intentionally **not an implementation prompt**.

The required workflow is:

```text
PHASE B SPEC
    ↓
Read-only review by Antigravity
    ↓
Implementation plan / risk assessment
    ↓
Implementation
    ↓
Targeted deterministic tests
    ↓
Full regression tests
    ↓
Small 100-case control/treatment run
    ↓
Review results
    ↓
Full 20,000-case benchmark
    ↓
Review benchmark + exceptions + reconciliation
    ↓
Final diff review
    ↓
Commit
```

Antigravity must not commit or push automatically.

No live Razorpay test is required for Phase B.

---

# 32. Design Principle

The central Phase B rule is:

> **REVIVE must prove incremental value, not merely activity.**

A large number of “recovered” customers is insufficient.

The benchmark must answer:

```text
What would have happened without REVIVE?
                vs.
What happened with REVIVE?
                ↓
How much incremental revenue did REVIVE create?
                ↓
What did it cost?
                ↓
Were the decisions accurate and safe?
                ↓
What happened to every exception?
```

That is the evidence required to turn the existing REVIVE engine into a defensible revenue-recovery system at scale.

---

## Authoritative Source Notes

1. Razorpay AI Buildathon — Track 03: AI Revenue Recovery
   https://razorpay.com/buildathon/

2. Existing REVIVE batch evaluator:
   `app/evaluation/batch.py`

3. Existing REVIVE diagnosis evaluator:
   `app/evaluation/` diagnosis evaluation implementation

4. Existing hidden evaluation ground truth:
   `app/simulation/ground_truth.py`

5. Existing intervention decision taxonomy and safety rules:
   `app/intervention/schemas.py`
   `app/intervention/`
