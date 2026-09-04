# REVIVE PHASE D SPECIFICATION

**Version:** 3.0.0
**Phase:** D — Selective Real Gemini Diagnosis & AI Evidence
**Status:** APPROVED DESIGN SPECIFICATION — IMPLEMENTATION PENDING
**Supersedes:** Phase D v2.0.0 as the active implementation target
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Dependencies:** Phase A Razorpay Test Mode proof + Phase B controlled evaluation + Phase C Command Center

---

## 1. Executive Purpose

Phase D v3 establishes the **AI diagnosis boundary** for REVIVE.

The purpose of Gemini is **not** to evaluate every customer in a large benchmark.

The purpose is to demonstrate that REVIVE can selectively invoke a real LLM when deterministic evidence is ambiguous, obtain a structured diagnosis hypothesis, and then return that hypothesis to REVIVE's deterministic policy boundary.

The intended architecture is:

```text
OBSERVE
   ↓
DETECT / RISK
   ↓
IS THE CASE SUFFICIENTLY DETERMINISTIC?
   ├── YES → deterministic diagnosis
   │
   └── NO / AMBIGUOUS → REAL GEMINI
                              ↓
                       structured diagnosis
                              ↓
                     deterministic policy
                              ↓
                            GUARD
                              ↓
                           EXECUTE
                              ↓
                     VERIFY / ATTRIBUTE
                              ↓
                            AUDIT
```

The critical design principle is:

> **AI proposes. Deterministic policy authorizes. Guarded execution acts. Payment/outcome evidence proves.**

Gemini is therefore a diagnosis-intelligence component, not an execution engine.

---

## 2. Why Phase D v3 Exists

The previous Phase D versions were designed around a 100-customer Gemini evaluation benchmark.

Real provider testing demonstrated that this approach is not the correct center of gravity for REVIVE:

- provider quotas and transient transport failures made large real-Gemini batches operationally unreliable;
- the business value of REVIVE is not dependent on sending an LLM request to every customer;
- many customer states already have clear deterministic observable diagnoses;
- some original benchmark labels were not validly distinguishable from the evidence available to an external model;
- forcing a large LLM benchmark encourages optimization around model-availability statistics instead of demonstrating the intended product architecture.

Phase D v3 therefore changes the **product demonstration objective**, while preserving useful Phase D infrastructure and historical evidence.

Historical Phase D v1/v2 artifacts remain historical. They must not be rewritten to retroactively claim that they were v3 experiments.

---

## 3. Phase D v3 Goals

Phase D v3 must prove:

### 3.1 Real provider integration

A genuine request to a configured Gemini model can be made and a genuine response can be captured.

### 3.2 Observable evidence grounding

Gemini receives only observable customer evidence.

No simulator-only labels or post-outcome ground truth may enter the model input.

### 3.3 Selective invocation

REVIVE does not need to invoke Gemini for every customer.

The system should identify a deterministic-vs-AI-review boundary and invoke Gemini only when:

- observable evidence is ambiguous;
- multiple meaningful signals conflict;
- deterministic diagnosis does not have sufficient distinctive evidence;
- or an explicitly configured AI-review condition is met.

The exact routing rule must be deterministic and auditable.

### 3.4 Structured diagnosis

Gemini produces a bounded diagnosis object containing diagnosis-oriented information only.

### 3.5 Deterministic authorization boundary

Gemini output must pass through existing deterministic intervention policy and execution guards before any action can occur.

### 3.6 Explainability

A reviewer must be able to see:

- observable evidence;
- why the case was routed to AI review;
- real Gemini model response;
- diagnosis;
- confidence;
- evidence cited by Gemini;
- deterministic policy result;
- whether execution was permitted.

### 3.7 Failure honesty

Provider failures must be shown as provider failures.

Fallback must be explicit.

The system must never turn provider failure into a fabricated Gemini success.

---

## 4. Non-Negotiable Safety Boundaries

Do not modify:

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

Phase D v3 must use an adapter/evaluation boundary around frozen production engines.

Gemini must never:

- create or dispatch payment links;
- retry payments;
- issue refunds;
- issue discounts;
- mutate subscriptions;
- mutate Razorpay state;
- change customer state;
- override policy;
- bypass guards;
- directly invoke execution;
- directly authorize a financial action.

No production customer data or production credentials are permitted.

---

## 5. Gemini's Exact Role in REVIVE

Gemini is responsible for **diagnostic interpretation**, not financial decision authority.

Gemini may answer:

> "Given the observable evidence, what diagnosis best explains this customer's current recovery state?"

Gemini may return:

- diagnosis;
- confidence;
- rationale;
- evidence used;
- uncertainty reasons.

Gemini must NOT return an executable intervention command.

The deterministic system remains authoritative for:

- eligibility;
- expected value;
- intervention selection;
- authorization;
- execution;
- retry policy;
- payment mutation;
- outcome verification;
- attribution.

---

## 6. Selective AI Review Router

Phase D v3 introduces a deterministic **AI Review Router**.

Its job is to decide:

```text
DETERMINISTIC
```

or:

```text
AI_REVIEW
```

for a customer case.

The router MUST be deterministic and independently auditable.

It must NOT use Gemini's opinion to decide whether Gemini should be invoked.

### 6.1 Deterministic routing principle

Prefer deterministic diagnosis when a strong observable rule exists.

Route to AI review when observable evidence is ambiguous, conflicting, or insufficient for a confident deterministic diagnosis.

Examples of legitimate AI-review triggers may include:

- multiple competing observable signals;
- conflicting activity patterns;
- ambiguous behavioral combinations;
- sufficient risk signal but no distinctive deterministic diagnosis;
- a case explicitly selected for AI demonstration.

The router must never use hidden simulator labels.

### 6.2 Router output

The router should expose:

```text
review_mode
routing_reason
observable_signal_summary
```

where:

```text
review_mode ∈ { DETERMINISTIC, AI_REVIEW }
```

The routing decision itself must be recorded in the evidence artifact.

---

## 7. Observable Evidence Contract

Gemini receives only observable evidence.

At minimum:

```text
customer_id
plan_name
plan_price_inr
billing_cycle

risk_score
risk_tier
revenue_at_risk

hours_until_trial_expiry
trial_active

payment_failed_observed
checkout_abandonment_observed

days_since_last_active
has_prior_conversion

lifetime_event_count
lifetime_session_count
lifetime_feature_use_count
lifetime_pricing_view_count
lifetime_checkout_start_count
lifetime_payment_attempt_count
lifetime_payment_success_count
lifetime_payment_failure_count

recent_observable_events
observable_evidence_descriptions
```

Additional observable fields may be added only when genuinely derived from customer journey history.

### 7.1 Forbidden information

The model input must never include:

```text
true_root_cause
natural_conversion
recoverable
generation_segment
conversion_after_intervention
counterfactual outcomes
post-treatment outcomes
hidden simulator segment names
```

Neither direct fields nor semantically equivalent encoded labels are allowed.

### 7.2 No post-outcome leakage

The Gemini prompt must represent the customer's state at the evaluation snapshot.

Do not provide:

- future conversion;
- future payment success;
- intervention outcome;
- attribution result;
- any information that would not be known at the diagnosis moment.

---

## 8. Evidence Provenance

Every AI-review case must have:

```text
evidence_version
evidence_hash
routing_mode
routing_reason
```

The evidence hash must be deterministic.

The same canonical observable evidence must produce the same hash.

The evidence artifact must retain enough information for a reviewer to reconstruct what the model saw.

---

## 9. Gemini Prompt v3

Use a new prompt version:

```text
REVIVE_GEMINI_DIAGNOSIS_PROMPT_V3
```

The prompt must instruct Gemini:

1. You are the REVIVE diagnosis-intelligence component.
2. You receive observable customer evidence only.
3. You must not infer hidden simulator attributes.
4. You must not invent missing evidence.
5. You must return exactly one diagnosis from the bounded vocabulary.
6. You must explain the diagnosis using observable evidence.
7. You must distinguish facts from uncertainty.
8. You must not claim execution, authorization, payment mutation, or intervention completion.
9. You must treat the result as a diagnosis proposal only.
10. Deterministic REVIVE policy remains authoritative.

The prompt should explicitly state that the model is being called because the case was routed to:

```text
AI_REVIEW
```

and should include the deterministic `routing_reason`.

---

## 10. Output Contract

The structured Gemini response must contain:

```text
diagnosis
confidence
actionability
rationale
evidence_used
uncertainty_reasons
```

All values remain bounded by the existing canonical enums/schema.

Confidence:

```text
0.0 <= confidence <= 1.0
```

The model must not output executable commands.

---

## 11. Diagnosis Vocabulary

Use the repository's canonical diagnosis vocabulary.

Phase D v3 does NOT redefine the production diagnosis enum.

Where a diagnosis has a deterministic observable definition, the evaluation layer may use that definition to assess Gemini.

Where a diagnosis cannot be legitimately distinguished from the available observable evidence, the evaluation layer must not invent a hidden label.

Such cases must be explicitly marked:

```text
NOT_SCOREABLE
```

with a reason.

---

## 12. Deterministic vs AI Diagnosis Relationship

Phase D v3 is not intended to prove that Gemini is better than REVIVE's deterministic diagnosis engine across a large dataset.

The intended demonstration is:

```text
Known deterministic case
    → deterministic path

Ambiguous observable case
    → AI_REVIEW
    → Gemini diagnosis
    → deterministic policy gate
```

A useful demonstration should therefore preferably use a case where:

- observable evidence contains multiple meaningful signals;
- no single deterministic shortcut dominates;
- the routing reason is explainable;
- Gemini produces a coherent structured diagnosis;
- deterministic policy still controls whether action can occur.

Do not artificially select an ambiguous-looking customer solely because Gemini gets the answer right.

Selection must be based on observable evidence and documented routing criteria.

---

## 13. AI Review Demonstration

The primary Phase D v3 live demonstration should use **one real Gemini customer case**.

The case must be synthetic/controlled or otherwise safe for non-production demonstration.

The demonstration should show:

```text
CUSTOMER
   ↓
OBSERVABLE EVIDENCE
   ↓
DETERMINISTIC ROUTER
   ↓
AI_REVIEW
   ↓
REAL GEMINI REQUEST
   ↓
STRUCTURED DIAGNOSIS
   ↓
CONFIDENCE
   ↓
EVIDENCE USED
   ↓
DETERMINISTIC POLICY
   ↓
AUTHORIZED / BLOCKED
   ↓
AUDIT
```

The UI must clearly display:

```text
REAL GEMINI
```

when a real request succeeds.

It must never show a fallback diagnosis as a real Gemini result.

---

## 14. Optional Secondary Real Cases

A single real case is sufficient for the primary Phase D demonstration.

The implementation may support additional real cases, but this is optional.

If additional calls are used:

- they must be explicitly counted;
- they must remain separate from the primary demonstration;
- provider failures remain visible;
- no statistical quality claim should be made unless a properly designed benchmark is separately established.

The implementation must not require 100 or 10,000 real Gemini calls.

---

## 15. Historical Benchmark Infrastructure

Existing Phase D v2 benchmarking infrastructure may remain for:

- offline regression;
- provider testing;
- evaluation research;
- future controlled benchmarking.

It must not be presented as the primary Phase D v3 product proof.

Do not delete it solely because the v3 focus is selective AI review.

Do not silently reinterpret historical 100-customer results as v3 results.

---

## 16. Provider Reliability

Use the existing official Google Gemini SDK integration.

Support:

```text
GEMINI_API_KEY
GEMINI_MODEL
```

Maintain:

- request timeout;
- bounded retries;
- controlled pacing;
- explicit provider error classification;
- no secrets in logs.

Transient failures such as:

```text
429
500
503
504 / DEADLINE_EXCEEDED
transport timeout
```

may use bounded retries as already implemented.

Non-transient errors such as:

```text
401
403
404 / model not found
schema rejection
```

must not be retried unless explicitly classified as transient by provider semantics.

Do not make claims about guaranteed completion.

---

## 17. Fallback

If Gemini cannot be used:

```text
MODEL_UNAVAILABLE
```

or:

```text
MODEL_ERROR
```

must be recorded honestly.

Fallback may invoke the existing deterministic diagnosis path, but it must be labeled:

```text
FALLBACK_USED
```

Fallback output is not a Gemini response.

The UI must distinguish:

```text
REAL_GEMINI
MODEL_ERROR
MODEL_UNAVAILABLE
SCHEMA_REJECTED
FALLBACK_USED
```

---

## 18. Governance

Every real Gemini response must be checked for:

```text
execution_bypass_attempt
unsupported_action_claim
policy_guard_violation
```

The model must have no direct execution capability.

The implementation must prove that a Gemini diagnosis object cannot be submitted directly to execution as if it were an authorized intervention decision.

Any action must pass through:

```text
InterventionEngine
→ policy
→ ExecutionEngine
→ guards
```

using the existing deterministic path.

---

## 19. AI Review Evidence Artifact

The current Phase D artifact may be replaced by a v3-shaped artifact:

```text
docs/evidence/phase_d_gemini_evaluation.json
```

or another clearly versioned Phase D evidence artifact if repository conventions require it.

The artifact must identify:

```text
phase_version = "3.0.0"
run_id
timestamp
model
prompt_version
evidence_version
```

For the primary demonstration, persist:

```text
customer_id
routing_mode
routing_reason
evidence_hash
observable_evidence
gemini_status
gemini_diagnosis
confidence
rationale
evidence_used
uncertainty_reasons
policy_result
execution_authority_result
governance_result
latency
token_usage
error_information
```

No secrets.

No hidden simulator truth.

No production PII.

---

## 20. Artifact Truthfulness

The artifact must clearly distinguish:

### Real model evidence

```text
REAL_GEMINI
```

### Provider failures

```text
MODEL_ERROR
MODEL_UNAVAILABLE
```

### Validation failure

```text
SCHEMA_REJECTED
```

### Deterministic fallback

```text
FALLBACK_USED
```

Do not create synthetic model responses when credentials are absent.

Do not fabricate latency/token/cost data.

---

## 21. Cost and Token Accounting

If the provider returns usage metadata, store it.

If pricing information is not configured:

```text
estimated_cost = null
cost_data_status = COST_UNAVAILABLE
```

Do not fabricate currency costs.

Because Phase D v3 is selective, token/cost reporting should be scoped to the actual real Gemini calls performed.

---

## 22. Command-Line Demonstration

Provide a simple repository command for the primary live demonstration, following repository conventions.

Preferred interface:

```powershell
py -m app.evaluation.phase_d_gemini
```

The v3 command should:

1. construct the selected controlled customer case;
2. build observable evidence;
3. run deterministic AI-review routing;
4. invoke real Gemini only if routed to AI review;
5. validate the structured response;
6. record governance results;
7. pass the diagnosis proposal to deterministic policy for evaluation;
8. write the Phase D v3 evidence artifact;
9. print a concise truthful summary.

The command must NOT perform production mutations.

---

## 23. Demonstration Case Selection

The implementation may use a deterministic selector rather than random selection.

The selection criteria should prefer:

- meaningful multi-signal evidence;
- observable ambiguity;
- no hidden-label dependency;
- a clear reason why deterministic logic alone is insufficient;
- enough evidence for Gemini to produce a grounded diagnosis.

The selector itself must be explainable.

Example output:

```text
Selected Case:
    cus_XXXXXX

Routing:
    AI_REVIEW

Reason:
    Conflicting observable engagement signals with no
    higher-precedence deterministic friction state.
```

Do not choose a case merely because a particular Gemini output is expected.

---

## 24. Dashboard Requirements

Phase C should be extended only as necessary.

Add/retain a clear Phase D view showing:

### AI REVIEW CASE

```text
CUSTOMER
ROUTING MODE
ROUTING REASON
```

### OBSERVABLE EVIDENCE

Show the facts Gemini actually received.

### GEMINI RESPONSE

Show:

```text
MODEL
STATUS
DIAGNOSIS
CONFIDENCE
RATIONALE
EVIDENCE USED
UNCERTAINTY
```

### GOVERNANCE

Show:

```text
EXECUTION AUTHORITY: NONE
BYPASS ATTEMPT: NO
UNSUPPORTED ACTION CLAIM: NO
POLICY VIOLATION: NO
```

### DETERMINISTIC POLICY

Show:

```text
POLICY RESULT
ELIGIBILITY
SELECTED ACTION
```

If no action is authorized, show the governed stop.

The dashboard must never imply that Gemini itself authorized or executed the action.

---

## 25. No Misleading Quality Claims

Phase D v3 must NOT display a fake or statistically meaningless:

```text
Gemini accuracy = X%
```

for the one-case demonstration.

Do not infer model quality from a single correct example.

The primary Phase D v3 claim is:

> **A real Gemini model can be selectively invoked inside REVIVE's diagnosis boundary using observable evidence, produce a structured diagnosis, and remain fully constrained by deterministic policy and execution guards.**

Quality benchmarking is a separate concern and may remain future work or an offline research path.

---

## 26. Testing Requirements

Tests remain important even though the live demonstration is small.

### 26.1 Routing tests

Test:

- deterministic case → `DETERMINISTIC`;
- ambiguous case → `AI_REVIEW`;
- routing is deterministic;
- routing never reads hidden truth.

### 26.2 Evidence tests

Test:

- evidence contains only observable fields;
- aggregate fields are correctly derived;
- no post-outcome information enters the prompt;
- no hidden simulator labels enter the prompt or artifact;
- evidence hashing is deterministic.

### 26.3 Provider tests

Test:

- missing API key;
- successful provider response;
- timeout;
- 429;
- 503;
- 504 / DEADLINE_EXCEEDED;
- bounded retries;
- no retry for non-transient errors;
- effective timeout wiring.

### 26.4 Output tests

Test:

- valid diagnosis;
- malformed JSON;
- unknown diagnosis;
- invalid confidence;
- missing required field;
- unsupported execution claim;
- unsupported action claim.

### 26.5 Governance tests

Test:

- Gemini output cannot directly execute;
- every proposed action passes deterministic policy;
- bypass attempt detected;
- unsupported action detected;
- policy guard violation detected.

### 26.6 Artifact tests

Test:

- real model response persisted correctly;
- failure states remain distinct;
- no secrets;
- no hidden truth;
- evidence hash matches;
- routing metadata persisted;
- policy result persisted;
- all real Gemini calls are represented.

### 26.7 Regression

Run:

```powershell
py -m pytest
```

Frontend if changed:

```powershell
cd frontend
npm run build
npm run lint
```

And:

```powershell
git diff --check
```

Frozen boundary:

```powershell
git diff --name-only -- app/risk app/diagnosis app/ai app/intervention app/execution app/outcome app/integrations/razorpay REVIVE_BUILD_CONSTITUTION.md
```

Must return no files.

---

## 27. Manual Validation

After implementation, manually verify exactly one primary real-Gemini demonstration.

Confirm:

1. API key is configured.
2. Configured model is recorded.
3. Case is routed to `AI_REVIEW`.
4. Observable evidence shown to Gemini is visible.
5. No hidden labels are present.
6. A real Gemini request occurs.
7. Response is structured and schema-valid.
8. Diagnosis/confidence/evidence are displayed.
9. Gemini has no execution authority.
10. Deterministic policy receives/validates the proposal.
11. No production payment mutation occurs.
12. Final evidence artifact records the demonstration truthfully.

If the real provider fails, show the honest failure state and do not manufacture a success.

---

## 28. Acceptance Criteria

Phase D v3 is complete when:

- [ ] Selective AI Review Router exists and is deterministic.
- [ ] Router uses only observable evidence.
- [ ] Real Gemini provider integration remains functional.
- [ ] Gemini is invoked only for the selected AI-review case(s).
- [ ] Prompt version is `REVIVE_GEMINI_DIAGNOSIS_PROMPT_V3`.
- [ ] Evidence version is updated and recorded.
- [ ] No hidden simulator labels reach Gemini.
- [ ] No post-outcome information reaches Gemini.
- [ ] Structured Gemini response validation is enforced.
- [ ] Governance containment is proven.
- [ ] Deterministic policy remains authoritative.
- [ ] No direct Gemini execution authority exists.
- [ ] Provider failure states are explicit.
- [ ] Fallback states are explicit.
- [ ] Truthful v3 evidence artifact is generated.
- [ ] No statistically meaningless Gemini accuracy claim is presented.
- [ ] Phase A evidence remains untouched.
- [ ] Phase B evidence remains untouched.
- [ ] Frozen production engines remain untouched.
- [ ] Focused tests pass.
- [ ] Full regression suite passes.
- [ ] Frontend build/lint pass if changed.
- [ ] Manual one-case real-Gemini demonstration passes.
- [ ] `git diff --check` is clean.
- [ ] No commit/push occurs during implementation.

---

## 29. Implementation Discipline

Antigravity must:

1. Read this specification completely.
2. Inspect the current repository before changing anything.
3. Preserve useful Phase D v2 provider infrastructure where possible.
4. Avoid deleting functionality merely because v3 is selective.
5. Keep v3 routing/evaluation logic outside frozen engines.
6. Prefer the smallest coherent implementation.
7. Do not tune a demonstration case to produce a preferred Gemini answer.
8. Do not alter labels after observing Gemini output.
9. Do not fabricate model responses, costs, metrics, or provenance.
10. Do not run large Gemini benchmarks.
11. Do not perform production mutations.
12. Do not commit.
13. Do not push.
14. Stop and report if implementation requires touching a frozen path.
15. Stop and report if the selected demonstration case cannot be justified from observable evidence.

---

## 30. Explicit Non-Goals

Phase D v3 does not attempt to:

- prove Gemini superiority over deterministic diagnosis;
- benchmark Gemini on 100 customers;
- benchmark Gemini on 10,000 customers;
- calculate a judge-facing statistical AI accuracy score from one or a few demonstrations;
- give Gemini execution authority;
- replace deterministic risk scoring;
- replace deterministic intervention policy;
- replace execution guards;
- modify Razorpay integration;
- rewrite Phase A proof;
- rewrite Phase B economics;
- expose hidden simulator truth;
- manufacture a favorable AI result.

---

## 31. Definition of Done

The strongest judge-facing claim should be:

> **REVIVE selectively invokes a real Gemini model when observable customer evidence is ambiguous, uses Gemini only for structured diagnosis intelligence, and preserves deterministic authorization, guarded execution, payment verification, and attribution as the financial control plane.**

The demonstrated flow is:

```text
CONTROLLED CUSTOMER CASE
        ↓
OBSERVABLE EVIDENCE
        ↓
DETERMINISTIC AI-REVIEW ROUTING
        ↓
REAL GEMINI
        ↓
STRUCTURED DIAGNOSIS
        ↓
CONFIDENCE + EVIDENCE
        ↓
DETERMINISTIC POLICY
        ↓
GUARD
        ↓
EXECUTE / GOVERNED STOP
        ↓
AUDITABLE RESULT
```

The proof is architectural and behavioral, not a fabricated benchmark number.

---

## 32. Final Phase Boundary

At the end of Phase D v3, REVIVE should be able to demonstrate:

```text
Known deterministic case
        ↓
Deterministic path

Ambiguous observable case
        ↓
AI_REVIEW
        ↓
REAL GEMINI
        ↓
Structured diagnosis
        ↓
Deterministic authorization
        ↓
Bounded execution / governed stop
        ↓
Audit evidence
```

This establishes the intended role of Gemini in REVIVE:

> **Gemini adds intelligence at the diagnosis boundary without becoming the financial control plane.**
