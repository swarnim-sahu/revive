# REVIVE — Phase C Specification
## Command Center, Explainability, Audit Visibility & Failure Demonstration

**Version:** 1.0.0
**Phase:** C — Command Center & Operational Trust Surface
**Status:** SPECIFICATION FOR IMPLEMENTATION
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Dependencies:** Phase A live Razorpay proof + Phase B controlled evaluation
**Primary objective:** Turn the already-working REVIVE backend, real Razorpay recovery proof, and controlled evaluation evidence into a truthful, inspectable command center that a fresh evaluator can use to understand risk, diagnosis, decision, guardrail, execution, outcome, exceptions, and measured business impact.

---

# 1. Executive Objective

Phase C is the **presentation, observability, explainability, and operator-trust layer** of REVIVE.

Phase A proved that a real Razorpay Test Mode Payment Link can produce a real `payment_link.paid` webhook that reaches REVIVE through the public tunnel and is correctly attributed by the outcome pipeline.

Phase B proved that REVIVE can run a large paired control/treatment evaluation and produce reproducible economic, decision-quality, safety, exception, and throughput evidence.

Phase C must make those capabilities **visible and inspectable in one command center**.

The final product should allow a fresh evaluator to answer, without reading source code:

> Who is at risk?
>
> Why are they at risk?
>
> What evidence supports the diagnosis?
>
> What did REVIVE recommend?
>
> Which alternatives were considered?
>
> Why was the selected action allowed or blocked?
>
> What actually executed?
>
> What happened afterward?
>
> How much revenue was attributable/recovered?
>
> What did REVIVE refuse to do?
>
> What failed?
>
> What happened after the failure?
>
> What does the control-vs-treatment experiment show?
>
> Can every important number be traced to an authoritative machine-readable source?

The current Razorpay Track 03 requirement is to build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow; its stated bar is measured money recovered across a batch with compliant escalation, stopping rules, and an audit trail.

Source:
- https://razorpay.com/buildathon/

---

# 2. Current-State Grounding

The current REVIVE constitution already defines the final product as a bounded AI revenue-recovery agent and explicitly requires a command center UI after audit/failure handling.

The constitution's Definition of Done requires a fresh evaluator to be able to:

1. clone the public repository;
2. follow setup;
3. generate/load evaluation data;
4. run the application;
5. inspect a customer at risk;
6. understand why revenue is at risk;
7. observe an intervention decision;
8. see the policy gate;
9. execute a Test Mode recovery;
10. inspect the audit trail;
11. reproduce failure;
12. observe graceful failure handling;
13. run batch evaluation;
14. see treatment/control results;
15. understand incremental revenue calculation.

Therefore Phase C is not cosmetic frontend work. It is the surface that makes the already-existing evidence accessible to a reviewer.

The current frontend already contains:

- a REVIVE command-center shell;
- benchmark summary cards;
- expected vs measured recovery;
- risk/diagnosis summaries;
- an execution/governance section;
- a customer queue;
- customer filtering;
- a customer detail interaction.

The existing dashboard API already exposes:

- dataset summary;
- risk summary;
- diagnosis summary;
- policy summary;
- expected recovery;
- measured recovery;
- outcome distribution;
- attribution distribution;
- execution summary.

The current customer evidence API exposes:

- risk score/tier;
- revenue at risk;
- diagnosis/confidence;
- AI status/confidence;
- fallback state;
- eligibility;
- selected action;
- expected value;
- decision reason;
- execution status;
- failure reason;
- outcome;
- attribution;
- attributable revenue;
- net recovered revenue;
- payment reference;
- evidence event IDs.

Phase C must **extend and integrate** this surface rather than replace it with an unrelated frontend architecture.

---

# 3. Phase C Scope

Phase C has six tightly related objectives:

1. **Authoritative Command Center**
   - Show current benchmark/evaluation status and authoritative business metrics.

2. **Customer Explainability**
   - Make the DETECT → DIAGNOSE → DECIDE → GUARD → RECOVER → MEASURE path visible for a selected customer.

3. **Policy & Safety Transparency**
   - Show why an action was allowed, blocked, stopped, or escalated.

4. **Audit Trail Visibility**
   - Expose the decision/execution/outcome lineage in chronological form.

5. **Exception / Failure Center**
   - Show why REVIVE did not act or why an action failed, and what happened next.

6. **Benchmark Evidence Surface**
   - Show Phase B control-vs-treatment evidence without fabricating or hardcoding metrics.

---

# 4. Non-Goals

Phase C MUST NOT become a generic frontend redesign.

Do NOT build:

- a generic chatbot;
- a marketing/CRM product;
- arbitrary payment manipulation;
- a new autonomous agent;
- a second AI orchestration framework;
- a RAG/vector-database subsystem;
- a microservice architecture solely for UI;
- dozens of new intervention types;
- a live production deployment;
- a real-money payment flow;
- a real merchant messaging system;
- fake “live” metrics;
- a dashboard that hardcodes benchmark numbers;
- frontend animations whose only purpose is decoration;
- a UI representation that claims synthetic results are production results.

The constitution explicitly excludes generic chatbot behavior, unrestricted autonomy, unnecessary infrastructure, and fabricated metrics.

---

# 5. Core Product Principle

The Command Center must follow:

```text
AUTHORITATIVE BACKEND STATE
        ↓
SAFE READ-ONLY API / ARTIFACT ADAPTER
        ↓
COMMAND CENTER
        ↓
HUMAN INSPECTION
```

Never:

```text
UI
  ↓
invented calculation
  ↓
displayed number
```

The UI MUST NOT recalculate business truth when an authoritative backend value already exists.

---

# 6. Source-of-Truth Hierarchy

Phase C must establish explicit source precedence.

## 6.1 Customer operational state

For customer-specific operational information, authoritative sources remain existing backend domain objects and existing APIs.

Examples:

- risk score → Risk layer result;
- diagnosis → Diagnosis layer result;
- selected action → InterventionDecision;
- policy result → deterministic policy engine;
- execution status → execution/audit records;
- payment result → Razorpay webhook/outcome evidence;
- attribution → OutcomeEngine/Attribution.

The frontend must not reconstruct these independently.

## 6.2 Phase B benchmark

For comparative benchmark metrics:

```text
reports/phase_b/summary.json
reports/phase_b/experiment.json
reports/phase_b/report.md
```

or a backend API that exposes these authoritative results.

Do not copy the benchmark values into TypeScript constants.

## 6.3 Real Razorpay proof

The real Razorpay proof must be labeled explicitly as:

```text
Razorpay Test Mode
```

and must never be represented as production merchant revenue.

---

# 7. Primary Command Center Layout

The main command center should have five high-value regions.

## Region A — Revenue Recovery Overview

Show:

- Revenue at Risk;
- Expected Recovery;
- OutcomeEngine Attributable Recovery;
- Net Recovered Revenue;
- Genuine Incremental Recovery Revenue;
- Net Revenue Delta vs Control;
- Intervention Cost;
- recovery/conversion lift where available;
- benchmark cohort status;
- data freshness/source.

The UI must visually distinguish:

```text
EXPECTED
OBSERVED / ATTRIBUTED
COUNTERFACTUAL / EVALUATED
CONTROL COMPARISON
```

Never present them as interchangeable.

---

## Region B — Recovery Pipeline

Present:

```text
DETECT
  ↓
DIAGNOSE
  ↓
DECIDE
  ↓
GUARD
  ↓
RECOVER
  ↓
MEASURE
```

For the selected customer, each stage must expose:

- status;
- key output;
- authoritative source;
- relevant timestamp where applicable.

Example:

```text
DETECT
Risk: 0.91
Tier: HIGH
Revenue at Risk: ₹999
        ↓
DIAGNOSE
Payment friction
Confidence: 0.87
        ↓
DECIDE
PAYMENT_RECOVERY
Expected Value: ₹746.25
        ↓
GUARD
ELIGIBLE
Policy: v1.0.0
        ↓
RECOVER
Payment Link dispatched
Status: EXECUTED
        ↓
MEASURE
RECOVERED
DIRECTLY_OBSERVED
Attributable: ₹999
```

Numbers must come from the backend record, not from manually constructed demo strings.

---

# 8. Customer Evidence View

Selecting a customer must show a detailed evidence drawer/page.

Required sections:

## Customer identity

- customer ID;
- plan;
- merchant context where safe;
- relevant timestamps.

## Risk

- risk score;
- risk tier;
- revenue at risk;
- risk explanation.

## Evidence

Show only evidence actually available to the model/decision layer.

Examples:

- event IDs;
- behavior signals;
- checkout/payment signals;
- subscription/trial signals;
- timestamps.

Do NOT display hidden simulator ground truth.

Forbidden examples:

```text
true_root_cause
natural_conversion
recoverable
conversion_after_intervention
maximum_recoverable_revenue
generation_segment
```

The UI must preserve the same ground-truth boundary enforced in backend evaluation.

---

# 9. Diagnosis Explanation

The UI must make diagnosis understandable to a human reviewer.

Show:

- diagnosis category;
- diagnosis confidence;
- actionability;
- supporting evidence;
- AI status;
- whether fallback was used;
- explanation of uncertainty where available.

Do NOT invent an explanation from the diagnosis label.

The explanation must be derived from actual `supporting_evidence`, decision reasoning, and existing structured output.

Use wording such as:

```text
Why is revenue at risk?

PAYMENT_FRICTION

Evidence supporting the diagnosis:
- ...
- ...
- ...

Confidence:
87%

AI status:
SUCCESS / FALLBACK / FAILED
```

Never imply that a confidence score is proof of correctness.

---

# 10. Decision Comparison View

The customer detail should show the candidate interventions considered by the existing InterventionEngine where available.

Show:

```text
Candidate Action
Expected Value
Eligibility
Policy Status
Selected?
Rejection Reason
```

The UI should make visible that REVIVE does not simply jump to one action.

Example conceptual view:

```text
NO_ACTION                 EV ₹0        NOT SELECTED
REMINDER                  EV ₹120      NOT SELECTED
CHECKOUT_ASSISTANCE       EV ₹420      NOT SELECTED
PAYMENT_RECOVERY          EV ₹746.25   SELECTED
```

The exact candidate data must come from the existing `InterventionDecision`.

No client-side re-ranking.

No new AI reasoning in the browser.

---

# 11. Guardrail / Policy View

The UI must have a dedicated safety panel.

Show:

- eligibility status;
- policy version;
- assumption version;
- monetary constraints;
- consent/eligibility state where available;
- rejection reasons;
- stopping conditions;
- whether escalation was required.

The conceptual rule must be visible:

```text
LLM / AI recommends
        ↓
Deterministic policy authorizes
        ↓
Execution infrastructure acts
```

The UI must never suggest that the AI itself authorized the payment action.

---

# 12. Execution & Recovery View

Show the actual execution lineage:

- execution ID;
- decision ID;
- selected action;
- payload/reference ID;
- execution status;
- attempt count;
- fallback state;
- API status;
- payment reference where present;
- webhook event ID where present;
- outcome status.

For successful Razorpay Test Mode recovery:

```text
Payment Link
    ↓
Payment
    ↓
payment_link.paid
    ↓
Webhook
    ↓
Outcome
    ↓
Attribution
```

Make the distinction between:

```text
execution succeeded
```

and:

```text
money was actually recovered
```

explicit.

A successful API call alone must never be displayed as successful revenue recovery.

---

# 13. Audit Trail Viewer

Phase C must expose the complete chronological audit lineage for a selected recovery case.

Minimum fields:

- audit ID;
- timestamp;
- customer ID;
- decision ID;
- execution ID;
- action;
- policy decision;
- execution status;
- attempt;
- fallback state;
- external reference;
- outcome status;
- attribution;
- recovered revenue.

Visualize as a chronological event timeline:

```text
Tprediction
  ↓
Risk scored
  ↓
Diagnosis produced
  ↓
Decision created
  ↓
Policy approved
  ↓
Execution dispatched
  ↓
External payment result
  ↓
Webhook received
  ↓
Outcome measured
  ↓
Revenue attributed
```

If a step did not occur, display that honestly as:

```text
NOT EXECUTED
BLOCKED
PENDING
FAILED
NOT OBSERVED
```

Never insert a synthetic success event to make the timeline look complete.

---

# 14. Exception / “Why REVIVE Didn't Act” Center

Phase C MUST add a visible exception view.

This is one of the strongest ways to demonstrate bounded behavior.

Required categories include, where present:

- insufficient evidence;
- already converted;
- below risk threshold;
- non-positive EV;
- policy blocked;
- cooldown;
- intervention limit reached;
- opportunity expired;
- API failure;
- retry budget exhausted;
- human review;
- terminal failure.

Show:

```text
WHY REVIVE DIDN'T ACT
```

with aggregate counts/rates.

For a selected case:

```text
Decision:
NO_ACTION

Why:
Customer had already converted before prediction snapshot.

Policy:
STOP

Financial impact:
₹0

Retryable:
NO
```

The exact reason must come from the authoritative record.

---

# 15. Failure Demonstration Surface

The constitution requires the final demonstration to intentionally show one failure and the correct recovery/fallback behavior.

Phase C must therefore make one deterministic failure scenario inspectable.

The failure UI must show:

```text
Recovery Action
      ↓
ACTION FAILED
      ↓
Failure Classified
      ↓
Retry Policy Checked
      ↓
Retry / Fallback / Escalation / Stop
      ↓
Final State
```

Show:

- failure reason;
- retryable flag;
- retry count;
- whether retry happened;
- fallback action;
- escalation;
- final customer state;
- financial exposure;
- audit history.

The failure scenario MUST be deterministic and reproducible.

Do NOT rely on accidental network failures for the demo.

Do NOT create a new real payment just to demonstrate failure.

---

# 16. Phase B Evidence Center

The command center must include a dedicated benchmark/evaluation section.

At minimum show:

## Population

- paired experimental units;
- control arm evaluations;
- treatment arm evaluations;
- total arm evaluations;
- seed;
- evaluation timestamp.

## Economics

- control baseline revenue;
- treatment modeled revenue;
- net revenue delta vs control;
- genuine incremental recovery revenue;
- OutcomeEngine attributable recovery;
- intervention cost;
- ROI.

## Conversion

- control conversion;
- treatment modeled conversion;
- natural conversion;
- genuine incremental recovery;
- observed unrecoverable conversion.

## Decision quality

- diagnosis accuracy;
- macro precision/recall/F1;
- intervention appropriateness;
- no-action safety metrics.

## Safety

- safety compliance;
- stop/no-action rate;
- escalation rate;
- unnecessary intervention rate.

## Exceptions

- total exceptions;
- retryable;
- terminal;
- escalated;
- financial exposure.

## Performance

- paired units/sec;
- arm evals/sec;
- total events/sec;
- runtime.

The UI must clearly label Phase B as:

```text
SYNTHETIC CONTROLLED EVALUATION
```

and must not imply these numbers are live production merchant metrics.

---

# 17. Control-vs-Treatment Visualization

Create a concise comparison view:

```text
                         CONTROL        REVIVE
Cases                    10,000         10,000
Conversion Rate           37.21%         42.20%
Net Revenue             ₹13.40M         ₹15.41M
Net Revenue Delta             —          ₹2.02M
Genuine Recovery             —          ₹1.42M
Intervention Cost             ₹0         ₹14K
```

Exact figures MUST be read from the authoritative Phase B result source.

The visualization must also expose:

```text
Why the metrics differ
```

and link to the methodological explanation.

Do not show a single “REVIVE ROI” number without its definition.

---

# 18. Benchmark Methodology Disclosure

The UI must include a compact “Methodology” panel.

At minimum:

- 10,000 paired experimental units;
- 10,000 control evaluations;
- 10,000 treatment evaluations;
- deterministic seed;
- synthetic response model;
- deterministic/mock AI path for high-volume evaluation;
- hidden ground truth used only post-hoc for evaluation;
- fixed observation horizon;
- genuine incremental recovery definition;
- OutcomeEngine attribution definition;
- limitations.

The UI must use plain language.

Example:

> “Phase B is a deterministic synthetic evaluation. Ground-truth labels are hidden from REVIVE during decision-making and used only after the decision for evaluation. These figures are not production merchant results.”

---

# 19. Real Razorpay Proof Panel

Phase A's successful real Test Mode proof should have a dedicated evidence card.

Show:

- Test Mode label;
- Payment Link status;
- webhook event type;
- webhook event ID;
- reference ID;
- correlated customer;
- Plan;
- outcome;
- attribution;
- attributable revenue;
- net recovered revenue;
- duplicate acknowledgement result.

Also show an explicit disclosure:

> “This proof used Razorpay Test Mode. It demonstrates external payment → webhook → REVIVE outcome integration; it is not a production-money claim.”

Do not expose webhook secrets, API keys, Basic Auth, zrok account tokens, or other credentials.

---

# 20. Data Freshness & Provenance

Every major metric block should make its source clear.

Possible source labels:

```text
LIVE TEST MODE
PHASE B BENCHMARK
CUSTOMER OPERATIONAL STATE
SYNTHETIC EVALUATION
```

Also expose:

- benchmark seed;
- benchmark timestamp;
- source artifact/API;
- model/policy version where relevant.

Avoid misleading labels such as:

```text
LIVE
```

when the data is actually a stored synthetic benchmark.

The existing frontend currently uses “BENCHMARK LIVE” language for its 100-customer view. Phase C should correct this ambiguity.

Prefer:

```text
BENCHMARK DATA
```

or:

```text
LAST EVALUATION
```

for stored evaluation data.

---

# 21. Read-Only Safety Boundary for the UI

The Phase C command center should be **read-only by default**.

The UI must NOT directly trigger:

- payment creation;
- arbitrary payment capture;
- refund;
- monetary adjustment;
- new intervention;
- policy override.

The successful live Razorpay operation remains a controlled workflow driven by the backend execution path.

Phase C is an inspection/control-room surface, not a replacement payment console.

---

# 22. Optional Operator Controls

Simple non-financial controls are allowed where useful:

- refresh;
- filter;
- search;
- inspect;
- compare;
- expand audit;
- export benchmark report;
- select benchmark seed/run.

Any mutation capability must be explicitly justified and must not bypass deterministic policy.

---

# 23. API Requirements

Reuse existing API contracts first.

Only add APIs that are necessary to surface information already present in authoritative backend state.

Potential read-only endpoints:

```text
GET /api/dashboard/summary
GET /api/dashboard/customers
GET /api/dashboard/customers/{customer_id}
GET /api/dashboard/benchmark
GET /api/dashboard/audit/{execution_id}
GET /api/dashboard/exceptions
GET /api/dashboard/failure-scenarios/{scenario_id}
GET /api/dashboard/razorpay-proof
```

These are conceptual names; use the smallest API surface that fits the current codebase.

Do not introduce endpoints purely to duplicate existing data.

---

# 24. Phase B Data Integration

Where possible, Phase C should consume the already-generated Phase B result schema.

Preferred pattern:

```text
Phase B
  ↓
authoritative benchmark artifact/result
  ↓
backend adapter
  ↓
typed API response
  ↓
frontend
```

Avoid:

```text
frontend
  ↓
hardcoded benchmark numbers
```

The benchmark seed and source must be visible.

---

# 25. API Response Safety

All new presentation-layer schemas MUST use explicit typed models.

Prefer:

```text
extra = forbid
```

where consistent with existing API conventions.

Do not leak:

- ground truth;
- secrets;
- Authorization headers;
- internal credential values;
- simulator-only fields;
- hidden model inputs.

A response should expose only the minimum fields required for human inspection.

---

# 26. Customer Detail Response Safety

The customer detail response may contain:

```text
customer_id
risk_score
risk_tier
revenue_at_risk
diagnosis
diagnosis_confidence
ai_status
ai_confidence
fallback_used
eligibility_status
selected_action
expected_value
decision_reason
supporting evidence
candidate action scores
rejection reasons
execution status
attempt count
failure reason
outcome
attribution status
attributable revenue
net recovered revenue
payment reference
audit references
event IDs
timestamps
version metadata
```

It must never include raw hidden ground truth.

---

# 27. Visual Information Hierarchy

The UI should prioritize the actual Track 03 value proposition.

Recommended hierarchy:

```text
1. Revenue at Risk / Recovery Impact
2. High-Risk Customer Queue
3. Why This Customer Is At Risk
4. What REVIVE Decided
5. Why Policy Allowed/Blocked It
6. What Actually Happened
7. Audit Timeline
8. Why REVIVE Did Not Act / Failure
9. Control vs REVIVE Evidence
10. Methodology / Limitations
```

Avoid decorative content above these sections.

---

# 28. Customer Queue Requirements

The queue should make prioritization useful without pretending the UI itself is the ranking engine.

At minimum support:

- search by customer ID;
- risk tier filter;
- diagnosis filter;
- execution status filter;
- outcome filter;
- sort by risk score;
- optional sort by revenue at risk;
- optional sort by expected value.

Current filtering behavior may be reused.

The backend remains authoritative for each record.

---

# 29. “Why REVIVE” Language

The interface should use the following conceptual language:

### Why at risk?

Driven by observable signals.

### Why this intervention?

Driven by diagnosis, candidate scoring, expected value, and policy constraints.

### Why not intervene?

Driven by policy, evidence, state, economics, stopping rules, or escalation.

### Did it work?

Driven by external/payment outcome evidence and the OutcomeEngine.

### Was it incremental?

Driven by post-hoc control/counterfactual evaluation.

These statements must never be collapsed into one generic AI explanation.

---

# 30. Failure-State UX

Every failed state must have a structured explanation.

Example:

```text
STATUS
FAILED

WHAT FAILED
Payment Link dispatch

WHY
Connection reset / API error / policy block

RETRYABLE
YES

RETRY ATTEMPTS
1 / 2

NEXT ACTION
Retry scheduled

REVENUE STILL AT RISK
₹999

AUDIT
View execution history
```

Use the actual failure record.

For terminal failures:

```text
RETRYABLE
NO

FINAL ACTION
STOP / ESCALATE

REASON
Policy prohibits another attempt
```

---

# 31. “No Action” UX

NO_ACTION deserves first-class treatment.

Example:

```text
NO ACTION

Why:
Customer already converted before prediction snapshot.

Expected Value:
₹0

Policy:
STOP

Intervention Cost Avoided:
₹X

Audit:
Available
```

This communicates that restraint is part of the product.

---

# 32. Accessibility / Usability

Phase C should support:

- keyboard navigation;
- readable contrast;
- semantic headings;
- meaningful labels;
- non-color indicators for state;
- responsive behavior on laptop-sized screens.

Do not spend time on mobile-app-level design unless required.

The buildathon presentation is expected to be a desktop workflow.

---

# 33. Performance Requirements

The command center should load the summary quickly enough for a live demo.

Targets:

- initial dashboard render: reasonable local-dev response;
- avoid unnecessary full-dataset refetches;
- avoid rendering thousands of customer rows at once;
- use pagination or virtualization if the API grows;
- cache immutable benchmark data where appropriate;
- customer detail should load independently from the main summary.

Do not introduce a state-management library unless current patterns cannot support the required behavior.

---

# 34. Deterministic Demo State

The Phase C demo must be reproducible.

Provide a documented deterministic demo selection containing:

1. a genuinely high-risk customer;
2. a recoverable/intervention case;
3. a NO_ACTION case;
4. a failure case;
5. a completed recovery case;
6. a case with auditable external Test Mode proof where possible.

Do not fabricate demo records.

Prefer selecting records from deterministic evaluation fixtures or stored/derived authoritative results.

---

# 35. Failure Reproduction Workflow

Document a deterministic failure reproduction path.

It must explain:

```text
Scenario
→ trigger
→ expected failure
→ policy/retry response
→ final state
→ audit evidence
```

This reproduction must not require real money.

A simulated/controlled failure is sufficient for Phase C demonstration.

The UI must clearly label a failure scenario as simulated/controlled when it is not a live external failure.

---

# 36. Real Razorpay Boundary

Do not move any real Razorpay logic into the frontend.

The existing backend remains responsible for:

- credentials;
- webhook verification;
- Payment Link creation;
- external API calls;
- execution;
- outcome processing.

Phase C only observes the resulting state.

---

# 37. Phase A / Phase B / Phase C Relationship

The product narrative becomes:

```text
PHASE A
External payment infrastructure proof
    ↓
Real Razorpay Test Mode payment
    ↓
Webhook
    ↓
REVIVE outcome attribution

PHASE B
Scale proof
    ↓
10,000 paired units
    ↓
Control vs Treatment
    ↓
Incremental-recovery evidence

PHASE C
Trust / presentation proof
    ↓
Command Center
    ↓
Why risk?
Why this action?
Why stop?
What happened?
What failed?
What was recovered?
How is the benchmark calculated?
```

This division must remain explicit.

---

# 38. Do Not Duplicate Phase B Metrics

Phase C must not implement another benchmark engine.

The UI must consume the Phase B authoritative output.

Do not recreate:

- conversion taxonomy;
- incremental revenue calculation;
- exception reconciliation;
- throughput calculations;
- diagnosis evaluation;
- control assignment.

If a metric cannot be obtained from the existing Phase B result, identify the missing authoritative source instead of rebuilding its business logic in the UI.

---

# 39. Do Not Duplicate Phase A Logic

Phase C must not:

- validate webhook signatures itself;
- parse Razorpay payloads itself;
- determine payment timestamps itself;
- calculate attribution itself.

All of that remains backend domain logic.

The UI consumes the resulting typed state.

---

# 40. Proposed Implementation Areas

Primary implementation areas:

```text
frontend/*
app/api/*
tests/*
docs/*
scripts/*

```

Potential changes may include:

```text
frontend/src/
frontend/src/components/
frontend/src/App.tsx
frontend/src/styles/
app/api/schemas.py
app/api/dashboard.py
tests/test_api.py
```

Exact paths MUST be determined from the current repository.

Do not assume these exact filenames exist.

---

# 41. Testing Requirements

Phase C must have focused tests for:

1. dashboard summary rendering/data contract;
2. customer list loading;
3. customer detail loading;
4. risk evidence rendering;
5. diagnosis evidence rendering;
6. candidate intervention rendering;
7. policy/guardrail rendering;
8. execution status rendering;
9. outcome/attribution rendering;
10. audit timeline rendering;
11. exception summary rendering;
12. failure scenario rendering;
13. Phase B benchmark rendering;
14. control-vs-treatment comparison;
15. forbidden ground-truth field isolation;
16. secret isolation;
17. stale/missing benchmark handling;
18. deterministic demo selection;
19. API failure/retry UI behavior;
20. read-only/no-financial-mutation boundary.

Do not create brittle tests based purely on CSS classes or pixel layout.

Prefer semantic DOM assertions and API contract tests.

---

# 42. Backend API Test Requirements

Any new API endpoint must have tests covering:

- success;
- 404 where applicable;
- malformed IDs;
- empty result;
- backend exception;
- response schema;
- forbidden field isolation;
- secret isolation.

No test may require real Razorpay credentials or external calls.

---

# 43. Frontend State Tests

The frontend must correctly distinguish:

```text
LOADING
SUCCESS
EMPTY
ERROR
STALE / UNAVAILABLE
```

Do not display stale benchmark numbers as if they were live.

A disconnected API should show a clear state such as:

```text
REVIVE API UNAVAILABLE
Last known benchmark: ...
```

if cached information is intentionally used.

---

# 44. Benchmark Source Failure Behavior

If the Phase B artifact/API is unavailable:

The UI must NOT:

- invent values;
- display zero as if zero revenue were measured;
- silently fall back to an unrelated 100-customer benchmark;
- label stale data as current.

Instead show:

```text
BENCHMARK UNAVAILABLE

Source:
Phase B Evaluation

Reason:
...

Last available evaluation:
...
```

where source metadata is known.

---

# 45. Phase B Metric Presentation Rules

The following terms must remain distinct in the UI:

```text
Net Revenue Delta vs Control
Genuine Incremental Recovery Revenue
OutcomeEngine Attributable Recovery Revenue
Net Recovered Revenue
Intervention Cost
```

Never label all of them “Revenue Recovered”.

The UI should provide tooltips/notes defining each.

---

# 46. Phase A Metric Presentation Rules

Use explicit labels:

```text
Razorpay Test Mode
Webhook Received
Outcome Observed
Attribution Status
Attributable Revenue
```

Never use:

```text
Production Revenue
Guaranteed Recovery
Live Merchant Revenue
```

for the Test Mode proof.

---

# 47. Audit Trust Requirements

Audit data must be chronological and immutable from the UI's perspective.

The frontend must not let an operator edit an audit record.

If audit history is append-only in backend state, present it as such.

The UI should show the difference between:

```text
attempt 1
attempt 2
fallback
duplicate
terminal
```

where applicable.

---

# 48. Merchant Trust Messaging

Use restrained language.

Good:

> “RECOVERED — DIRECTLY_OBSERVED”

Good:

> “Genuine incremental recovery — counterfactual evaluation”

Good:

> “NO_ACTION — policy stopped intervention”

Bad:

> “AI saved this customer”

Bad:

> “Guaranteed ₹999 recovery”

Bad:

> “100% accurate”

Even when the current synthetic benchmark reports 100% safety compliance, label the exact measured metric and cohort rather than generalizing it to production.

---

# 49. No Hardcoded Benchmark Values

Forbidden:

```typescript
const recoveredRevenue = 2500307;
```

or equivalent.

Allowed:

```text
API response / Phase B artifact
    ↓
typed state
    ↓
formatted display
```

The UI must automatically reflect a newly regenerated Phase B benchmark.

---

# 50. No Hidden Ground Truth in Presentation APIs

Presentation APIs must not quietly load:

```text
ground_truth.jsonl
```

just to explain why the model made a decision.

They may show post-hoc evaluation labels only where the UI section is explicitly labeled:

```text
COUNTERFACTUAL EVALUATION
```

and the source is an evaluation artifact rather than the treatment decision path.

For ordinary customer operational views, hidden labels remain excluded.

---

# 51. Explainability Boundary

The UI is an explanation surface, not a new reasoning engine.

Do not ask a browser-side LLM to generate:

```text
why this customer is risky
```

from raw events.

Use the already-produced structured evidence/reasoning from the backend.

If a future phase adds real Gemini evaluation, Phase C should still display the structured output, not invent a parallel explanation.

---

# 52. Required Demo Sequence

The command center must support this five-minute sequence:

```text
1. PROBLEM
   Show revenue at risk.

2. DETECTION
   Select a high-risk customer.

3. DIAGNOSIS
   Show evidence and diagnosis.

4. DECISION
   Show candidate actions and chosen action.

5. GUARDRAIL
   Show policy approval/rejection.

6. EXECUTION
   Show execution status.

7. RECOVERY
   Show actual Test Mode recovery evidence where available.

8. MEASUREMENT
   Show attributable/genuine recovery evidence.

9. FAILURE
   Open a controlled failure case.

10. RECOVERY FROM FAILURE
    Show retry/fallback/escalation/stop.

11. AUDIT
    Show the full timeline.

12. SCALE
    Open Phase B benchmark.

13. CONTROL VS REVIVE
    Show economic comparison.

14. LIMITATIONS
    Show synthetic/mock-AI disclosure.
```

The sequence should require minimal navigation and no source-code reading.

---

# 53. Operator Drill-Down Depth

A reviewer should be able to go from:

```text
portfolio
    ↓
customer
    ↓
decision
    ↓
policy
    ↓
execution
    ↓
outcome
    ↓
audit
```

without losing the selected customer context.

Where an external payment exists:

```text
outcome
    ↓
webhook event
```

should be visible.

Where a benchmark result exists:

```text
customer
    ↓
counterfactual evaluation classification
```

may be visible only in a clearly labeled evaluation context.

---

# 54. Benchmark Evidence Drill-Down

The Phase B section should permit:

```text
overview
   ↓
metric
   ↓
definition
   ↓
methodology
   ↓
source artifact
```

At minimum:

- clicking `Genuine Incremental Recovery Revenue` explains the definition;
- clicking `Net Revenue Delta vs Control` shows its formula;
- clicking conversion lift shows control and treatment denominators;
- clicking safety compliance shows measured cohort and policy scope;
- clicking throughput shows runtime and event-count definition.

---

# 55. Export / Evidence Capture

Phase C should support evidence capture without exposing secrets.

Useful read-only actions:

- copy selected customer ID;
- copy decision/execution IDs;
- download/display Phase B summary;
- copy benchmark methodology;
- export audit timeline as JSON/Markdown if easy.

Do not introduce a large export subsystem.

---

# 56. Production-Like Behavior

Even though this is a buildathon system, the command center should behave like a small production application:

- typed API contracts;
- explicit error states;
- no silent fallbacks;
- no client-side financial authority;
- observable data source;
- deterministic behavior;
- safe defaults;
- clear failure messages.

---

# 57. Frozen Business Engines

Unless a proven defect directly blocks Phase C, do not modify:

```text
app/risk/*
app/diagnosis/*
app/ai/*
app/intervention/*
app/execution/*
app/outcome/*
app/integrations/razorpay/*
REVIVE_BUILD_CONSTITUTION.md
```

Phase C should primarily touch:

```text
frontend/*
app/api/*
tests/*
docs/*
```

and only other layers when strictly necessary to expose existing authoritative state.

---

# 58. Phase A and Phase B Immutability

Phase C must treat these as **evidence-producing dependencies**, not code to casually refactor.

Do not change:

- Razorpay webhook semantics;
- payment timestamp semantics;
- Phase B conversion taxonomy;
- Phase B counterfactual definitions;
- Phase B economic formulas.

If the UI cannot consume an existing output, add the smallest read-only adapter rather than changing the underlying business semantics.

---

# 59. Required Demo Fixture Strategy

Create/document deterministic selectors for:

### Case A — High-risk + actionable
Shows why REVIVE intervenes.

### Case B — NO_ACTION
Shows why REVIVE correctly stops.

### Case C — Successful recovery
Shows an observed/attributable recovery.

### Case D — Failure
Shows controlled failure + correct retry/fallback/escalation/stop.

### Case E — Phase B benchmark
Shows control vs treatment.

Case selection must be deterministic by ID/seed/filter.

No hardcoded “success” outcomes should be inserted solely for the demo.

---

# 60. UI Status Taxonomy

Use explicit status vocabulary consistent with backend semantics.

Examples:

```text
AT_RISK
ACTIONABLE
ELIGIBLE
NO_ACTION
ESCALATED
EXECUTED
FAILED
RETRYING
STOPPED
RECOVERED
ALREADY_CONVERTED
UNATTRIBUTED
DIRECTLY_OBSERVED
DUPLICATE_ACKNOWLEDGED
```

Where possible, display the backend's canonical value rather than mapping it to a vague marketing term.

---

# 61. Security Requirements

The frontend must never receive:

- API keys;
- API secrets;
- webhook secrets;
- Basic Authorization headers;
- zrok account tokens;
- environment variable contents.

Do not log secrets in the browser console.

Do not put secrets into URLs.

Do not expose full raw webhook payloads if they contain sensitive fields unnecessary for inspection.

---

# 62. Performance & Network Boundaries

Avoid:

```text
one request per table row
```

for the initial page.

Prefer:

```text
summary request
+
customer list request
+
detail request on selection
```

Benchmark artifact data can be loaded separately.

---

# 63. Testing / Acceptance Matrix

Phase C acceptance should cover:

| Capability | Acceptance |
|---|---|
| Summary | Loads authoritative metrics |
| Customer queue | Loads deterministic safe records |
| Customer detail | Shows full evidence chain |
| Risk | Score/tier/revenue at risk displayed |
| Diagnosis | Diagnosis + evidence + confidence displayed |
| Decision | Candidate/selected action visible |
| Guardrail | Eligibility + reason visible |
| Execution | Attempt/status visible |
| Outcome | Observed outcome visible |
| Attribution | Revenue meaning clearly labeled |
| Audit | Chronological trail visible |
| Exceptions | Why REVIVE didn't act visible |
| Failure | Controlled failure reproducible |
| Phase B | Benchmark metrics visible |
| Control vs Treatment | Comparison visible |
| Methodology | Limitations visible |
| Safety | Ground truth and secrets excluded |
| Errors | API failures handled without fake data |
| Read-only boundary | No financial mutation from UI |

---

# 64. Manual Validation Requirements

Before Phase C is considered complete, manually verify:

### A. Dashboard
- API reachable;
- dashboard renders;
- source label correct;
- no stale “live” wording for stored benchmark data.

### B. Customer
- select a real deterministic customer;
- inspect risk;
- inspect diagnosis;
- inspect action;
- inspect policy;
- inspect execution;
- inspect outcome.

### C. Audit
- timeline is chronological;
- IDs agree across records;
- no missing transition is falsely shown as success.

### D. Exception
- open a NO_ACTION case;
- see why it stopped.

### E. Failure
- reproduce deterministic controlled failure;
- verify retry/fallback/stop behavior.

### F. Phase B
- compare control vs treatment;
- verify numbers match the authoritative Phase B artifact;
- verify formula explanations.

### G. Phase A
- view the stored real Test Mode proof;
- verify the payment/webhook/outcome lineage.

---

# 65. Manual Test Rule

As with Phase A and Phase B:

```text
Antigravity:
    code
    deterministic tests
    local validation

Human:
    manual product walkthrough
    final evidence validation
    commit
```

Do not let Antigravity declare Phase C complete solely from unit tests.

---

# 66. No Real Payment Required for Phase C

Phase A already contains the real Test Mode proof.

Phase C does NOT need another real Razorpay payment simply to validate the UI.

Where the UI displays the Phase A proof, use the already captured authoritative evidence.

A new real payment should only be performed later if a specific regression makes it necessary.

---

# 67. Required Documentation

Add/update documentation for:

1. running the command center;
2. starting backend;
3. starting frontend;
4. benchmark data source;
5. deterministic demo cases;
6. audit viewer;
7. failure reproduction;
8. Test Mode proof interpretation;
9. safety/ground-truth boundary;
10. known limitations.

The documentation must be usable by a fresh evaluator.

---

# 68. Definition of Done

Phase C is complete only when a fresh evaluator can:

- launch the application;
- see authoritative recovery KPIs;
- identify a customer at risk;
- understand why;
- inspect the evidence;
- inspect the intervention candidates;
- understand the selected decision;
- inspect the policy gate;
- inspect execution;
- inspect outcome/attribution;
- inspect the audit trail;
- understand a NO_ACTION decision;
- reproduce a controlled failure;
- see retry/fallback/escalation/stop behavior;
- open Phase B benchmark results;
- understand control-vs-treatment;
- distinguish genuine incremental recovery from attributed revenue;
- inspect Phase A real Test Mode proof;
- see all limitations;
- verify that no hidden ground truth/secrets are exposed.

---

# 69. Phase C Closure Checklist

All must be true:

- [ ] Command Center uses authoritative backend/API/artifact data.
- [ ] Existing frontend functionality remains regression-safe.
- [ ] Stored benchmark data is not mislabeled as live.
- [ ] Customer evidence is inspectable.
- [ ] AI/diagnosis reasoning is structured and evidence-backed.
- [ ] Candidate interventions are visible.
- [ ] Policy authorization is visible.
- [ ] Execution lineage is visible.
- [ ] Outcome/attribution distinction is visible.
- [ ] Audit timeline is visible.
- [ ] NO_ACTION reasoning is visible.
- [ ] Exception center is visible.
- [ ] Controlled failure is reproducible.
- [ ] Failure recovery/stop/escalation is visible.
- [ ] Phase B control/treatment evidence is visible.
- [ ] Phase A Test Mode proof is visible.
- [ ] Ground-truth fields remain isolated.
- [ ] Secrets remain isolated.
- [ ] UI has no financial mutation authority.
- [ ] Targeted tests pass.
- [ ] Full regression passes.
- [ ] Manual walkthrough passes.
- [ ] Fresh-evaluator setup documentation works.
- [ ] No frozen engine was changed without explicit justification.

---

# 70. Required Final Report

Antigravity must produce:

## A. Architecture
- current frontend architecture;
- new/modified presentation components;
- new/modified API contracts;
- data-source hierarchy.

## B. Implementation
- exact files added;
- exact files modified;
- exact frozen files verified untouched.

## C. Explainability
- customer risk explanation;
- diagnosis evidence;
- action comparison;
- policy explanation.

## D. Audit
- audit viewer;
- event lineage;
- failure visibility.

## E. Benchmark
- Phase B integration;
- control/treatment presentation;
- methodology disclosure.

## F. Tests
- targeted test count;
- targeted results;
- full regression;
- API contract tests.

## G. Manual Validation
- dashboard;
- customer drill-down;
- NO_ACTION;
- failure scenario;
- audit;
- Phase B;
- Phase A proof card.

## H. Security
- ground-truth isolation;
- secret isolation;
- read-only financial boundary.

## I. Final Verdict

Use exactly one:

```text
PHASE C READY FOR REVIEW
```

or

```text
PHASE C NEEDS CORRECTION
```

Do not claim Phase C complete merely because the UI renders.

---

# 71. Implementation Workflow

This document is the authoritative Phase C specification.

Required sequence:

```text
PHASE C SPECIFICATION
        ↓
Read-only inspection by Antigravity
        ↓
Gap analysis
        ↓
Implementation plan
        ↓
Implementation
        ↓
Targeted tests
        ↓
Full regression
        ↓
Manual smoke walkthrough
        ↓
Review of data-source accuracy
        ↓
Failure demonstration
        ↓
Final manual walkthrough
        ↓
Final diff review
        ↓
Commit
```

No automatic commit/push.

---

# 72. Final Design Principle

The command center exists to make REVIVE's core loop visible:

```text
DETECT
  ↓
DIAGNOSE
  ↓
DECIDE
  ↓
GUARD
  ↓
RECOVER
  ↓
MEASURE
```

The reviewer should be able to see not merely that REVIVE claims to recover revenue, but:

```text
WHAT IT KNEW
      ↓
WHAT IT THOUGHT
      ↓
WHAT IT RECOMMENDED
      ↓
WHAT POLICY ALLOWED
      ↓
WHAT ACTUALLY HAPPENED
      ↓
WHAT THE PAYMENT SYSTEM CONFIRMED
      ↓
WHAT REVENUE WAS ATTRIBUTABLE
      ↓
WHAT WAS ACTUALLY INCREMENTAL
      ↓
WHAT IT REFUSED TO DO
      ↓
WHAT FAILED
      ↓
WHAT HAPPENED NEXT
```

That is the purpose of Phase C.

---

# 73. Phase C Evidence Hierarchy

The final command center should visibly distinguish:

### Level 1 — Operational state
Current customer/risk/decision/execution data.

### Level 2 — Real Test Mode infrastructure proof
Actual Razorpay Test Mode payment → webhook → outcome evidence from Phase A.

### Level 3 — Controlled batch evidence
Phase B synthetic control/treatment benchmark.

The UI should never collapse these into a single “production performance” claim.

---

# 74. Submission Narrative Supported by Phase C

Phase C should enable the final reviewer story:

> **REVIVE identifies revenue at risk before it is lost, explains why, chooses the minimum bounded intervention, allows deterministic policy to authorize it, executes safely, verifies the external payment result, measures attributable and genuinely incremental recovery, shows where it stopped or failed, and provides evidence at both real-infrastructure and batch scale.**

This statement is a synthesis of the existing REVIVE product definition and the required Track 03 proof surface. It is not a claim that synthetic benchmark results equal production merchant performance.

---

## Authoritative Sources

1. Razorpay AI Buildathon — Track 03: AI Revenue Recovery
   https://razorpay.com/buildathon/

2. REVIVE product/architecture constitution
   `REVIVE_BUILD_CONSTITUTION.md`

3. Existing presentation API contracts
   `app/api/schemas.py`

4. Existing dashboard API tests
   `tests/test_api.py`

5. Existing command-center frontend
   `frontend/*`

6. Phase A live Razorpay integration and webhook proof
   `app/integrations/razorpay/*`
   `app/api/webhooks.py`
   associated Phase A tests/reports

7. Phase B controlled evaluation
   `app/evaluation/*`
   `scripts/run_phase_b_evaluation.py`
   `reports/phase_b/*`
