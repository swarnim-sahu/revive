# REVIVE Phase 6 — Execution & Workflow Specification

**Version:** 1.0.0
**Phase:** 6 — Intervention Workflow Execution, Failure Handling & Delivery
**Status:** Architecture Specification
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Package Path:** `app/execution/`

---

## 1. Purpose

Phase 6 is the execution layer of REVIVE.

Phase 5 answers:

> **What bounded intervention should REVIVE take?**

Phase 6 answers:

> **Can REVIVE safely and deterministically execute that already-selected intervention?**

Phase 6 must not reconsider the Phase 5 decision. It operationalizes the decision while enforcing execution-time safety, idempotency, bounded retries, failure handling, fallback, escalation, and auditability.

Phase 7 will subsequently measure customer outcomes and revenue recovery.

---

## 2. End-to-End Architecture

```text
Customer / Observable Events
            │
            ▼
     Phase 3 — Risk Engine
            │
            ▼
   Phase 4 — Diagnosis Engine
            │
            ▼
 Phase 5 — Intervention Decision
            │
            │ InterventionDecision
            ▼
┌───────────────────────────────────────────┐
│                 PHASE 6                   │
│                                           │
│  Execution Authorization                  │
│          ↓                                │
│  Idempotency Guard                        │
│          ↓                                │
│  Payload Construction                     │
│          ↓                                │
│  Deterministic Dispatch                   │
│          ↓                                │
│  Success / Failure Classification         │
│          ↓                                │
│  Retry / Fallback / Escalation            │
│          ↓                                │
│  Execution Audit + Observable Event       │
└──────────────────────┬────────────────────┘
                       │
                       ▼
                 Phase 7
            Outcome Measurement
```

---

## 3. Phase Boundaries

### Phase 5 owns

- risk-informed intervention eligibility
- diagnosis-informed action selection
- candidate action evaluation
- expected value calculation
- policy constraints for selecting an action
- final `InterventionDecision`

### Phase 6 owns

- accepting a Phase 5 decision for execution
- execution authorization
- idempotency
- payload construction
- deterministic test-mode dispatch
- delivery/failure classification
- bounded retry handling
- fallback
- human escalation
- execution audit records
- execution events

### Phase 6 must not own

- risk prediction
- risk rescoring
- root-cause diagnosis
- intervention/action selection
- expected-value calculation
- conversion prediction
- causal attribution
- incremental revenue calculation
- control-group analysis
- model retraining
- changing the original Phase 5 decision

### Phase 7 owns

- post-intervention customer outcomes
- conversion/recovery measurement
- revenue attribution
- incremental recovery analysis
- long-term effectiveness measurement

---

## 4. Core Design Principles

1. **Decision immutability:** Phase 6 executes the Phase 5 decision; it does not re-decide.
2. **Determinism:** identical decision + identical execution state must produce the same result.
3. **Bounded execution:** retries and execution attempts have hard limits.
4. **Idempotency:** the same decision must never cause duplicate execution.
5. **Safety first:** invalid, ineligible, unsafe, or malformed decisions are blocked.
6. **Test-mode isolation:** Phase 6 performs no real financial or customer-facing mutation.
7. **Temporal isolation:** post-intervention information cannot retroactively influence the original decision.
8. **Auditability:** every execution attempt and terminal outcome must be traceable.
9. **Ground-truth isolation:** hidden simulator fields are never required for runtime execution.
10. **Phase separation:** Phase 6 records execution facts; Phase 7 evaluates outcomes.

---

## 5. Input Contract

The primary Phase 6 input is the immutable Phase 5:

```text
InterventionDecision
```

Relevant fields include:

- `customer_id`
- `decision_timestamp`
- `policy_version`
- `assumption_version`
- `risk_score`
- `risk_tier`
- `revenue_at_risk`
- `diagnosis`
- `diagnosis_confidence`
- `diagnosis_actionability`
- `eligibility_status`
- `selected_action`
- `expected_value`
- `candidate_scores`
- `decision_reason`
- `rejection_reasons`
- `supporting_evidence`

Phase 6 may validate these fields for execution safety.

Phase 6 must not modify their semantic meaning.

---

## 6. Execution Lifecycle

The conceptual lifecycle is:

```text
RECEIVED
   │
   ▼
AUTHORIZED
   │
   ▼
IDEMPOTENCY_CHECKED
   │
   ▼
PAYLOAD_BUILT
   │
   ▼
DISPATCHING
   │
   ├──────────────► SUCCESS
   │
   ▼
FAILURE_CLASSIFIED
   │
   ├── RETRYABLE ──► RETRY
   │                   │
   │                   ├──► SUCCESS
   │                   └──► RETRY_EXHAUSTED
   │
   └── NON_RETRYABLE
             │
             ▼
       FALLBACK / ESCALATE
```

### Terminal outcomes

- `EXECUTED`
- `FAILED`
- `BLOCKED`
- `ESCALATED`
- `NO_ACTION`

No execution may remain indefinitely in a non-terminal state.

---

## 7. Authorization Guard

Before dispatch, Phase 6 must verify:

1. The decision exists.
2. The selected action is recognized.
3. The decision is not already executed.
4. The decision's eligibility status permits execution.
5. The action is supported by the Phase 6 executor.
6. The execution environment is test/simulation mode.
7. Required payload inputs are present.
8. The decision has not violated an execution-time safety rule.

A failed authorization check results in `BLOCKED`.

Phase 6 must not override a Phase 5 `INELIGIBLE` decision.

---

## 8. Idempotency

Idempotency is mandatory.

A stable execution identity must be derived from the Phase 5 decision, using the existing project identifiers rather than creating an unnecessary parallel identity system.

Conceptually:

```text
decision_id / stable decision identity
        ↓
execution identity
        ↓
already executed?
   ├── YES → return existing execution result
   └── NO  → execute
```

Repeated submission of the same decision must not cause a second customer-facing or financial action.

Idempotency must be deterministic and testable.

---

## 9. Action Execution

Phase 6 must support the existing Phase 5 action taxonomy.

| Action | Execution Behavior |
|---|---|
| `NO_ACTION` | No dispatch. Terminal `NO_ACTION`. |
| `PRODUCT_GUIDANCE` | Build deterministic guidance payload and simulate dispatch. |
| `REMINDER` | Build deterministic reminder payload and simulate dispatch. |
| `CHECKOUT_ASSISTANCE` | Build deterministic checkout assistance payload and simulate dispatch. |
| `PAYMENT_RECOVERY` | Execute only if Phase 5 selected it and execution guards permit it; no real payment mutation. |
| `TRIAL_EXTENSION` | Execute only in deterministic simulation mode; no real account mutation. |
| `HUMAN_REVIEW` | Do not automate customer-facing execution; create escalation/audit outcome. |

Phase 6 must not invent new intervention actions.

---

## 10. Payload Construction

Payloads must be:

- deterministic
- structured
- auditable
- derived only from permitted Phase 5 decision/context
- free of hidden ground-truth fields
- safe for test-mode dispatch

Payload construction must not call an LLM.

The payload builder must not use future customer outcomes.

---

## 11. Dispatch Model

Phase 6 operates in a deterministic simulation/test environment.

It must not:

- charge a real customer
- create a real subscription
- extend a real trial
- send uncontrolled external communications
- mutate a production payment gateway
- perform irreversible financial operations

A dispatch result must be explicitly classified as success or failure.

The simulation must be reproducible.

---

## 12. Failure Taxonomy

Failures must be explicitly classified.

### Retryable failures

Examples include:

- simulated timeout
- temporary channel unavailability
- transient dispatch failure

### Non-retryable failures

Examples include:

- malformed payload
- unsupported action
- authorization failure
- safety violation
- permanently invalid execution request

Failure classification must be deterministic.

A failure must never be silently converted into success.

---

## 13. Retry Policy

Phase 6 uses a bounded retry model.

Initial proposal:

```text
Maximum total dispatch attempts = 3

Attempt 1 = initial execution
Attempt 2 = retry 1
Attempt 3 = retry 2
```

After the retry budget is exhausted:

```text
RETRY_EXHAUSTED
       ↓
FALLBACK or ESCALATION
```

No unbounded retry loop is permitted.

Retry count must be recorded in the execution audit.

---

## 14. Fallback

Fallback is only permitted when the Phase 5 policy and Phase 6 execution contract allow it.

A failed action must not automatically be replaced with an unrelated intervention.

Fallback must:

- be deterministic
- be bounded
- be auditable
- preserve safety constraints
- not secretly re-run Phase 5 action selection

Fallback execution records are created under a distinct fallback execution identity (`exec_fb_{customer_id}_{decision_timestamp}_att{attempt}`) while referencing the original `decision_id`, preserving the failed primary attempt in audit history.

If no valid fallback exists, the execution terminates as `FAILED` or `ESCALATED`, depending on the failure policy.

---

## 15. Human Escalation

`HUMAN_REVIEW` is an explicit terminal execution path.

Escalation is appropriate when:

- the Phase 5 decision explicitly selected human review
- automated execution is unsafe
- a bounded automated fallback is unavailable
- retry exhaustion requires human handling

Phase 6 must not invent a human decision.

It records that human intervention is required.

---

## 16. Execution Audit Record

Every execution request must produce an auditable record.

Minimum conceptual fields:

```text
execution_id
customer_id
decision_id / stable decision identity
action
execution_timestamp
status
attempt_number
payload_reference
failure_reason
fallback_action
escalation_status
execution_policy_version
```

The audit record must describe what Phase 6 actually did.

It must not claim that a customer converted or revenue was recovered.

---

## 17. Execution Events

Phase 6 emits execution lifecycle events mapped directly to the canonical Phase 1 `EventType` values:

- **Dispatch / Delivery Success:** `RECOVERY_ACTION_EXECUTED`
- **Attempt Failure:** `RECOVERY_ACTION_FAILED`
- **Retry Exhaustion / Human Escalation:** `RECOVERY_ESCALATED`
- **Authorization / Cooldown Block:** `POLICY_REJECTED`

Phase 6 uses these canonical Phase 1 event types and does not introduce a duplicate parallel `INTERVENTION_*` event taxonomy. Every execution event is emitted as a canonical `BaseEvent` containing structured payload context (`decision_id`, `customer_id`, `action`, `attempt`, `failure_type`, `failure_reason`, `payload_id`, `target_url`).

---

## 18. Temporal Contract

Phase 6 occurs after the Phase 5 decision snapshot.

Conceptually:

```text
Tprediction
    ↓
Tdecision
    ↓
Tdispatch
    ↓
Tdelivery / Tfailure
    ↓
Tretry / Tescalation
    ↓
Phase 7 outcome measurement
```

### Rule

Information observed after `Tprediction` may describe execution, but must not alter or justify the original Phase 5 decision.

Phase 6 must never use:

- future conversion
- future subscription creation
- future revenue
- hidden simulator outcomes

to determine whether the original intervention should have been selected.

---

## 19. Ground-Truth Isolation

The following simulator-only fields are prohibited during runtime Phase 6 execution:

- `generation_segment`
- `natural_conversion`
- `true_root_cause`
- `conversion_after_intervention`
- `recoverable`
- `maximum_recoverable_revenue`

These may be used only by offline evaluation systems where explicitly required.

---

## 20. AI Boundary

Phase 6 does not require AI.

The intended architecture is:

```text
Phase 3 → ML risk prediction
Phase 4 → deterministic evidence/rule diagnosis
Phase 5 → deterministic intervention policy/EV selection
Phase 6 → deterministic execution
Phase 7 → outcome measurement/evaluation
```

No LLM, reinforcement-learning agent, or generative model is permitted in Phase 6 unless the architecture is explicitly revised and re-approved.

---

## 21. Safety Controls

Phase 6 must enforce:

### S6.1 Idempotency

Prevent duplicate execution.

### S6.2 Authorization

Block invalid or ineligible decisions.

### S6.3 Bounded retries

Prevent uncontrolled execution loops.

### S6.4 Test-mode isolation

Prevent real-world financial/customer mutation.

### S6.5 Action integrity

Execute only the action contained in the accepted Phase 5 decision.

### S6.6 Audit integrity

Record every execution attempt and terminal outcome.

### S6.7 Temporal isolation

Prevent future information from affecting execution justification.

---

## 22. Evaluation Strategy

Phase 6 evaluation must focus on execution correctness, not revenue recovery.

Required evaluation categories:

### Execution correctness

- correct action dispatched
- correct `NO_ACTION` handling
- correct `HUMAN_REVIEW` handling
- correct terminal state

### Safety

- no duplicate execution
- no execution of ineligible decisions
- no live financial mutation
- no forbidden hidden-field access

### Retry correctness

- retryable failures retry
- non-retryable failures do not retry
- retry budget is respected

### Fallback correctness

- valid fallback only
- no accidental re-selection of actions

### Audit completeness

- every execution has an execution record
- failures contain failure information
- retries are counted

### Temporal integrity

- post-decision events do not alter the original decision
- no future-outcome leakage

### Determinism

Repeated identical execution inputs produce identical execution results.

---

## 23. Manual Behavioral Testing

Phase 6 must include real behavioral manual tests.

Minimum scenarios:

### S1 — Successful PRODUCT_GUIDANCE

Expected:
- authorized
- dispatched
- successful terminal result

### S2 — Successful CHECKOUT_ASSISTANCE

Expected:
- correct payload
- successful dispatch
- no unrelated action

### S3 — Retryable failure

Expected:
- first attempt fails
- retry occurs
- retry count is correct

### S4 — Non-retryable failure

Expected:
- no retry
- terminal failure/fallback according to policy

### S5 — Retry exhaustion

Expected:
- maximum attempts respected
- no infinite loop
- fallback/escalation occurs

### S6 — Fallback

Expected:
- only an allowed deterministic fallback occurs

### S7 — Human escalation

Expected:
- no automated customer-facing execution
- escalation recorded

### S8 — Duplicate execution

Expected:
- second identical decision does not dispatch again

### S9 — INELIGIBLE decision

Expected:
- execution blocked

### S10 — NO_ACTION

Expected:
- no dispatch
- terminal `NO_ACTION`

### S11 — Determinism

Expected:
- repeated identical execution produces identical results

### S12 — Test-mode isolation

Expected:
- no real external/financial mutation occurs

---

## 24. Proposed Implementation Structure

The implementation should use the minimum necessary components.

Proposed:

```text
app/execution/
    __init__.py
    config.py
    schemas.py
    payloads.py
    state_machine.py
    engine.py
    audit.py
    evaluation.py

scripts/
    evaluate_execution.py
    manual_test_phase6.py

tests/
    test_execution_engine.py

docs/
    PHASE6_EXECUTION_AND_WORKFLOW_SPECIFICATION.md
```

These are implementation targets, not permission to expand scope unnecessarily.

---

## 25. Implementation Order

Phase 6 should be implemented in controlled stages:

### Phase 6A — Contracts

- execution schemas
- execution states
- configuration/versioning
- event compatibility

### Phase 6B — Payload & State Machine

- payload builders
- failure classification
- retry state machine
- fallback/escalation logic

### Phase 6C — Execution Engine

- authorization
- idempotency
- dispatch simulation
- audit records
- event emission

### Phase 6D — Evaluation

- execution evaluation
- safety metrics
- retry metrics
- audit completeness
- leakage checks

### Phase 6E — Automated Tests

Unit and integration tests for all execution paths.

### Phase 6F — Manual Behavioral Validation

Run the twelve scenarios defined above.

### Phase 6G — Closure

Only after:

- tests pass
- evaluation passes
- manual behavioral tests pass
- leakage/safety checks pass
- Git inspection is clean

may Phase 6 be committed and closed.

---

## 26. Acceptance Criteria

Phase 6 is acceptable only if all are true:

- [ ] Phase 5 `InterventionDecision` remains the source of the selected action.
- [ ] Phase 6 never re-selects an intervention.
- [ ] `NO_ACTION` never causes a dispatch.
- [ ] `INELIGIBLE` decisions cannot execute.
- [ ] Duplicate decisions cannot cause duplicate execution.
- [ ] Retryable failures retry.
- [ ] Non-retryable failures do not retry.
- [ ] Retry attempts are bounded.
- [ ] Fallback is deterministic and authorized.
- [ ] Human review does not trigger automatic customer-facing execution.
- [ ] Execution records are auditable.
- [ ] Execution events are temporally isolated.
- [ ] No hidden ground-truth field is required at runtime.
- [ ] No real financial/customer mutation occurs.
- [ ] Identical inputs produce deterministic results.
- [ ] Phase 7 outcome measurement is not implemented inside Phase 6.
- [ ] Existing Phase 1–5 contracts remain intact unless an explicitly approved compatibility extension is required.

---

## 27. Completion Criteria

Phase 6 may be marked **CLOSED** only after:

1. Specification is frozen.
2. Implementation is complete.
3. Automated tests pass.
4. Execution evaluation passes.
5. Leakage verification passes.
6. Manual behavioral tests pass.
7. Safety scenarios pass.
8. Determinism is verified.
9. Git diff is clean.
10. A dedicated Phase 6 commit is created.
11. The commit is pushed to `origin/main`.
12. Working tree is clean.
13. Phase 7 boundary remains intact.

---

## 28. Explicit Non-Goals

Phase 6 does not:

- predict conversion
- diagnose root cause
- select interventions
- calculate recovery EV
- claim recovered revenue
- perform causal attribution
- retrain models
- optimize future intervention policies
- perform real financial transactions
- send uncontrolled production communications
- use an LLM to make execution decisions

---

## 29. Architecture Summary

REVIVE is intentionally separated into:

```text
PHASE 3
"What revenue is at risk?"
        ↓
PHASE 4
"Why is it at risk?"
        ↓
PHASE 5
"What bounded action should we choose?"
        ↓
PHASE 6
"Can we safely execute that action?"
        ↓
PHASE 7
"Did the action actually recover revenue?"
```

This separation prevents decision logic, execution logic, and outcome measurement from becoming one coupled system.

---

**Phase 6 specification status: ARCHITECTURE DRAFT — READY FOR IMPLEMENTATION REVIEW**
