# REVIVE — Razorpay Sandbox Integration Specification

**Status:** Design specification — implementation must not begin until this boundary is reviewed and approved.

**Baseline:** Phases 1–8 are frozen, audited, tested, committed, and pushed. This specification defines the next integration boundary without changing that baseline.

---

## 1. Objective

Introduce a Razorpay sandbox integration behind the existing intervention and execution architecture.

The integration must allow Revive to execute only explicitly approved, bounded recovery actions while preserving Phase 5 policy authority and preventing Gemini or the AI layer from directly initiating payment operations.

---

## 2. Current Baseline

- Phases 1–7 are complete and regression-tested.
- Phase 8 AI/Gemini intelligence is complete and regression-tested.
- Full regression: **157/157 tests passed**.
- Phase 8 manual behavioral tests: **12/12 passed**.
- Real Gemini authenticated path: successfully verified.
- Ground-truth leakage: **0%** in the audited AI runtime.
- Gemini has **no intervention or execution authority**.
- Phase 5 remains authoritative for intervention policy.
- Repository baseline commit: `6912c2e` — `Implemented AI intelligence and Gemini integration`.

---

## 3. Target Architecture

```text
Customer/Event Data
        ↓
Risk Engine
        ↓
Diagnosis
        ↓
Gemini Intelligence
        ↓
Schema/Grounding Validation
        ↓
Phase 5 Intervention Policy
        ↓
Phase 6 ExecutionEngine
        ↓
Razorpay Adapter
        ↓
Razorpay Sandbox
        ↓
Execution Result / Webhook
        ↓
Outcome Engine
```

### Authority boundaries

- **Gemini:** analytical candidate only; no payment or execution authority.
- **Phase 5 InterventionEngine:** authoritative policy decision-maker for eligibility, expected value, safety constraints, and allowed action.
- **Phase 6 ExecutionEngine:** authoritative workflow/execution boundary.
- **Razorpay adapter:** external-provider transport boundary; it must not independently decide whether an intervention is allowed.
- **Phase 7 OutcomeEngine:** records and evaluates outcomes; it must not retroactively authorize execution.

---

## 4. Razorpay Integration Scope

- Identify the exact Razorpay API operation(s) required by the existing Phase 5 action taxonomy before implementation.
- Implement only the minimum operation required by the approved recovery workflow.
- Do not add arbitrary charging or unrelated payment capabilities.
- Do not expose raw Razorpay calls to `AIService` or Gemini.
- Do not allow AI-generated actionability to bypass Phase 5.
- Keep production credentials and production endpoints out of development/test configuration.

---

## 5. Proposed Component Boundary

- `app/integrations/razorpay/` — dedicated provider/adapter package.
- Narrow Razorpay client interface defining only approved operations.
- Razorpay sandbox implementation for controlled external testing.
- Deterministic mock Razorpay provider for offline tests.
- Typed request/response schemas.
- Webhook verification/handling only where required by the selected operation.

---

## 6. Configuration and Secrets

Use environment-based configuration only. Never hardcode credentials.

Expected configuration:

- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`

Secrets must never appear in:

- source code
- tests
- documentation
- logs
- exception messages
- object representations
- audit records
- Git history

`.env` files remain ignored.

---

## 7. Execution Contract

Phase 5 must produce an explicit, bounded execution proposal before Phase 6 can invoke the Razorpay adapter.

The execution contract should contain, as applicable:

- Customer/reference identifier.
- Approved intervention/action type.
- Eligibility decision.
- Safety-policy decision.
- Any bounded amount or parameter required by the action.
- Idempotency key/reference.
- Reason/audit reference.
- Execution expiry/deadline where applicable.

The adapter must reject:

- malformed requests
- requests lacking authorization metadata
- unsupported action types
- requests outside the execution contract

---

## 8. Idempotency and Duplicate Protection

- Every externally mutating request must have an idempotent execution reference.
- Repeated attempts must not unintentionally create duplicate payment actions.
- `ExecutionEngine` state must be checked before dispatch.
- Retries must distinguish safe retryable failures from non-retryable failures.
- Duplicate execution attempts must be explicitly tested.

---

## 9. Failure and Retry Model

At minimum, classify failures into:

1. Configuration failure — credentials/configuration unavailable.
2. Validation failure — execution request violates the contract.
3. Provider authentication/authorization failure.
4. Provider rate limiting.
5. Provider timeout/network failure.
6. Provider business/API rejection.
7. Duplicate/idempotency conflict.
8. Unknown/unclassified provider failure.

**Critical rule:** No failure path may silently treat an unexecuted action as successfully executed.

---

## 10. Webhook Boundary

If the selected Razorpay operation uses asynchronous confirmation:

- Implement a verified webhook boundary.
- Verify webhook authenticity before accepting state changes.
- Persist only validated provider events.
- Handle duplicate webhook delivery idempotently.
- Never allow an unverified webhook to mark an intervention successful.
- Webhook processing updates execution/outcome state; it does not grant policy authority.

---

## 11. Sandbox Safety Requirements

- All development and automated tests use Razorpay sandbox/test credentials and endpoints.
- Tests fail closed if production credentials/endpoints are detected in a sandbox-only test.
- No production payment operation is reachable from normal development/test configuration.
- Sandbox mode is explicit and enforced by configuration.
- No real customer/payment credentials are used in tests.

---

## 12. Testing Strategy

The existing **157-test baseline must remain passing**.

| Test Area | Required Verification |
|---|---|
| Provider initialization | Sandbox configuration loads correctly; missing credentials fail safely. |
| Request schema | Malformed or unauthorized execution requests are rejected. |
| Mock provider | Deterministic offline success/failure behavior. |
| Idempotency | Duplicate requests do not create duplicate execution. |
| Timeout | Timeout never becomes false success. |
| Rate limit | Rate-limited responses are classified correctly. |
| Provider rejection | Business/API rejection is represented accurately. |
| Webhook | Valid, invalid, and duplicate webhook scenarios. |
| Execution isolation | `AIService` cannot directly invoke Razorpay. |
| Policy authority | Phase 5 must approve before execution. |
| Sandbox E2E | Approved intervention reaches sandbox and records the correct result. |
| Secret safety | Credentials never appear in logs, tests, `repr`, or repository. |

---

## 13. End-to-End Scenarios

### E2E-01
Eligible intervention → Phase 5 approval → ExecutionEngine → Razorpay sandbox success → recorded execution success → outcome event.

### E2E-02
Phase 5 rejection → **no Razorpay request**.

### E2E-03
Gemini proposes an action but Phase 5 rejects it → **no Razorpay request**.

### E2E-04
Razorpay sandbox rejects request → execution failure is recorded; no false success.

### E2E-05
Timeout → no false success; retry behavior follows idempotency rules.

### E2E-06
Duplicate execution attempt → safely deduplicated.

### E2E-07
Invalid webhook → rejected.

### E2E-08
Duplicate webhook → idempotently handled.

### E2E-09
Missing sandbox credentials → safe failure without secret leakage.

### E2E-10
Direct AI-to-Razorpay execution attempt → architecturally impossible/unavailable.

---

## 14. Observability and Audit Trail

- Record execution identifiers and provider references without unnecessary sensitive payment data.
- Record decision/execution timestamps and state transitions.
- Record provider status and error categories.
- Never record API keys, authorization headers, PAN, CVV, or other payment credentials.
- Maintain lineage from Phase 5 approval to ExecutionEngine action to provider result.

---

## 15. Data Minimization

- Send only the minimum data required by the selected Razorpay operation.
- Do not send Gemini prompts or AI explanations to Razorpay unless explicitly required.
- Do not expose hidden simulator/ground-truth fields.
- Do not store unnecessary payment credentials or sensitive payment data.

---

## 16. Implementation Order

1. Freeze the existing Phase 1–8 baseline.
2. Define the exact Phase 5 → Phase 6 execution contract.
3. Define the narrow Razorpay adapter interface.
4. Define request/response schemas.
5. Implement deterministic mock Razorpay provider.
6. Add unit and integration tests against the mock.
7. Add sandbox configuration and real Razorpay sandbox provider.
8. Run a small number of controlled sandbox E2E tests.
9. Audit logs, idempotency, failure states, and authority boundaries.
10. Run the complete Phase 1–new integration regression suite.
11. Perform a final read-only architecture/security audit.

---

## 17. Explicit Non-Goals

- No production payment operations.
- No unrestricted charging capability.
- No direct Gemini-to-Razorpay execution.
- No replacement of Phase 5 policy logic.
- No unnecessary changes to the completed Phase 1–8 architecture.
- No storing of raw payment credentials.

---

## 18. Acceptance Criteria

- Existing 157 tests remain passing.
- All newly added Razorpay adapter tests pass.
- Mock provider provides deterministic offline coverage.
- Sandbox E2E test succeeds for the approved operation.
- Phase 5 remains the only intervention policy authority.
- `AIService` has no direct Razorpay dependency.
- `ExecutionEngine` is the only approved external execution boundary.
- Idempotency prevents duplicate execution.
- Provider failures never become false successes.
- Webhook authenticity and idempotency are enforced where applicable.
- No secrets are committed or logged.
- Production endpoints/credentials are unreachable from sandbox test configuration.
- Final audit reports no critical or high-severity integration issues.

---

## 19. Approval Gate

> **This document is a specification, not authorization to implement.**

Before coding begins, confirm:

1. The exact Razorpay operation.
2. The Phase 5 → Phase 6 execution contract.
3. Sandbox configuration.
4. Idempotency strategy.
5. Webhook requirements, if applicable.

Any implementation must preserve the audited Phase 1–8 baseline.
