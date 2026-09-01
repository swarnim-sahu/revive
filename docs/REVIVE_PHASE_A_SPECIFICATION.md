# REVIVE — PHASE A SPECIFICATION
## Real Razorpay Webhook → Outcome Integration

**Status:** SPECIFICATION FOR IMPLEMENTATION  
**Phase:** A  
**Target:** Razorpay AI Buildathon — Track 03: AI Revenue Recovery

## 1. Objective

Implement the narrow integration boundary that allows a Razorpay webhook event to enter REVIVE and flow through the existing execution/outcome/attribution pipeline.

Target closed loop:

Razorpay `payment_link.paid`
→ webhook receipt
→ HMAC verification
→ event-id deduplication
→ `reference_id` correlation
→ existing `BaseEvent(PAYMENT_SUCCEEDED)`
→ existing `OutcomeEngine`
→ existing `AttributionEngine`
→ existing revenue accounting
→ immutable audit trail.

This phase must not redesign existing risk, diagnosis, AI, intervention, execution, outcome, evaluation, or Razorpay dispatch logic.

## 2. Architectural Rules

### MUST NOT
- Rewrite RiskScorer, DiagnosisEngine, AIService, InterventionEngine, ExecutionEngine, OutcomeEngine, AttributionEngine, or RevenueCalculator.
- Duplicate recovery or revenue-calculation logic in the webhook route.
- Introduce a second outcome/revenue calculation path.
- Expose secrets through logs, responses, audit records, or exceptions.
- Use simulator ground-truth fields as webhook/runtime evidence.

### MUST
- Reuse existing domain models and engines.
- Use existing `BaseEvent` and `EventType`.
- Preserve deterministic correlation and idempotency.
- Keep the implementation boundary small and auditable.

## 3. Authoritative Identity Chain

Use the existing chain:

`InterventionDecision`
→ `InterventionPayload.payload_id`
→ Razorpay Payment Link `reference_id`
→ `ExecutionAuditRecord`
→ `OutcomeRecord`.

The webhook must correlate Razorpay `reference_id` to the existing REVIVE `payload_id` and recover the associated execution/decision/customer identity. Do not invent a parallel identity system.

## 4. Event Scope

### Mandatory primary event
`payment_link.paid`

Expected path:

`payment_link.paid`
→ `PAYMENT_SUCCEEDED`
→ `RECOVERED`
→ `DIRECTLY_OBSERVED`
→ attributable revenue
→ net recovered revenue.

### Graceful secondary handling
Optionally handle:
- `payment.captured`
- `payment.failed`
- `payment_link.expired`
- `payment_link.cancelled`

Unsupported event types must be safely acknowledged and audited as ignored.

## 5. Webhook API

Create:

`POST /webhooks/razorpay`

Required headers:
- `X-Razorpay-Signature`
- `X-Razorpay-Event-Id`

The raw HTTP body must be obtained before relying on parsed JSON for signature verification.

Response requirements:

| Scenario | HTTP | Behavior |
|---|---:|---|
| Valid supported event | 200 | Process |
| Invalid/missing signature | 401 | Reject before state mutation |
| Malformed JSON | 400 | No execution/outcome mutation |
| Duplicate event ID | 200 | Do not process twice |
| Unsupported event | 200 | Audit as ignored |
| Unmatched `reference_id` | 404 | No outcome mutation |

Exact safe response JSON may be implementation-defined.

## 6. Signature Verification

Verify HMAC-SHA256 over the exact raw request body bytes using:

`RAZORPAY_WEBHOOK_SECRET`

Use Python standard-library `hmac` and `hashlib`, and `hmac.compare_digest`.

Requirements:
- raw bytes are the signed message;
- fail closed if secret/signature is missing or invalid;
- never log or expose the secret.

## 7. Secret Configuration

Extend `RazorpayConfig` minimally with:

`webhook_secret: Optional[str] = None`

Load it from:

`RAZORPAY_WEBHOOK_SECRET`

Preserve existing `key_id` / `key_secret` behavior and secret-redaction conventions.

## 8. Event Translation

Do not create a new event class.

For `payment_link.paid`, create the existing:

`BaseEvent(event_type=EventType.PAYMENT_SUCCEEDED, ...)`

Include, as applicable:
- event ID;
- schema version;
- merchant ID;
- correlated customer ID;
- UTC timestamp;
- `source="razorpay_webhook"`;
- `payment_id`;
- `payment_link_id`;
- `amount`;
- `currency`;
- `reference_id`;
- payment method when available.

Do not include simulator-only fields such as `ground_truth`, `true_root_cause`, `natural_conversion`, `recoverable`, `maximum_recoverable_revenue`, or `conversion_after_intervention`.

## 9. Outcome Integration

The webhook layer must invoke the existing:

`OutcomeEngine.measure_outcome(...)`

with:
- correlated `ExecutionAuditRecord`;
- associated `InterventionDecision`;
- existing customer event history plus the webhook `BaseEvent`;
- applicable `Plan`;
- configured observation window.

The webhook layer must not independently decide recovery, attribution, or revenue.

The existing outcome pipeline remains authoritative:

`PAYMENT_SUCCEEDED`
→ `RECOVERED`
→ `DIRECTLY_OBSERVED`
→ existing revenue accounting.

## 10. Pre-Existing Conversion Protection

Existing temporal protection remains authoritative.

If conversion evidence exists at or before intervention:
- outcome = `ALREADY_CONVERTED`;
- attribution = `UNATTRIBUTED`;
- attributable revenue = ₹0.00.

Do not bypass or weaken this rule.

## 11. Three Idempotency Boundaries

### Webhook delivery
Key: `X-Razorpay-Event-Id`

Duplicate delivery:
- HTTP 200;
- no second processing;
- audit as `DUPLICATE_IGNORED`.

### Execution
Existing ExecutionEngine idempotency remains authoritative. Never create a second payment link from a webhook.

### Outcome
Existing OutcomeEngine outcome identity remains authoritative. Revenue must not be double-counted.

## 12. Webhook Audit Store

Use a small in-memory append-only webhook audit store consistent with REVIVE's existing architecture.

Safe fields may include:
- Razorpay event ID;
- event type;
- processing status;
- timestamp;
- reference ID;
- correlated execution ID;
- safe reason/error code.

Never persist:
- webhook secret;
- API credentials;
- authorization headers;
- secret-bearing configuration.

No external database is required.

## 13. Edge Cases

- Invalid signature → 401, no business mutation.
- Malformed JSON → 400, no business mutation.
- Duplicate event ID → 200, no duplicate outcome/revenue.
- Unsupported event → 200, audit ignored.
- Unmatched reference ID → 404, no mutation.
- Pre-execution conversion → existing `ALREADY_CONVERTED` behavior.
- Post-window event → existing temporal machinery must prevent direct recovery attribution.

## 14. Required Files

### Add
- `app/integrations/razorpay/webhook.py`
- `app/api/webhooks.py`
- `tests/test_razorpay_webhook.py`

### Modify minimally
- `app/integrations/razorpay/config.py`
- `app/integrations/razorpay/__init__.py`
- `app/api/main.py`

### Frozen / must remain untouched
- `app/risk/*`
- `app/diagnosis/*`
- `app/intervention/*`
- `app/ai/*`
- `app/execution/engine.py`
- `app/execution/state_machine.py`
- `app/execution/payloads.py`
- `app/outcome/engine.py`
- `app/outcome/observer.py`
- `app/outcome/resolver.py`
- `app/outcome/attribution.py`
- `app/outcome/revenue.py`
- `app/evaluation/batch.py`
- `REVIVE_BUILD_CONSTITUTION.md`
- frontend/dashboard code.

## 15. Required Tests

At minimum:
1. Valid HMAC signature accepted.
2. Invalid signature → 401.
3. Missing signature → 401.
4. Missing/invalid secret fails closed.
5. `payment_link.paid` correlates through `reference_id`.
6. It produces `PAYMENT_SUCCEEDED`.
7. Full path reaches `RECOVERED`.
8. Attribution becomes `DIRECTLY_OBSERVED`.
9. Existing revenue logic records attributable/net revenue.
10. Duplicate event ID is idempotent.
11. Duplicate webhook cannot double-count revenue.
12. Unmatched reference is safe.
13. Malformed JSON is safe.
14. Unsupported event is acknowledged/ignored.
15. Pre-existing conversion remains `ALREADY_CONVERTED` with ₹0 attributable.
16. Secret never appears in logs/responses/string representations.
17. Webhook events contain no forbidden simulator ground-truth fields.
18. Full regression suite remains passing.

## 16. Verification

Before completion run:

`py -m pytest`

`py -m pytest tests/test_razorpay_webhook.py -v`

`git diff --check`

Also verify the API:
- `/health`;
- valid signed webhook;
- invalid signature;
- duplicate event;
- unmatched reference.

Do not commit until implementation review and tests are complete.

## 17. Definition of Done

Phase A is complete only when:
- a Razorpay-shaped `payment_link.paid` webhook is receivable;
- raw-body HMAC verification works;
- event deduplication works;
- `reference_id` deterministically correlates to existing execution;
- webhook data becomes an existing `BaseEvent`;
- existing OutcomeEngine resolves recovery;
- existing AttributionEngine attributes recovery;
- existing revenue accounting records it;
- duplicate delivery cannot double-count revenue;
- invalid/malformed/unmatched events fail safely;
- pre-existing conversion protection remains intact;
- no secrets or simulator ground truth leak;
- frozen engines remain untouched;
- full tests pass;
- `git diff --check` passes;
- implementation is ready for Razorpay Test Mode proof.

## 18. Out of Scope

Phase A does not include:
- dashboard redesign;
- live dashboard outcome streaming;
- production database;
- production deployment;
- webhook retry infrastructure;
- merchant multi-tenancy;
- every Razorpay event;
- new AI logic;
- new recovery policy logic.

Its sole purpose is to close:

**Razorpay payment completion → verified webhook → existing REVIVE outcome/attribution/revenue pipeline.**

## 19. Implementation Gate

Before changing code, inspect the repository and verify that this specification matches the actual implementation.

If an assumption is inconsistent:
1. STOP.
2. Report the exact discrepancy.
3. Do not silently redesign.
4. Do not modify frozen files to force compatibility.

Only proceed when the implementation satisfies this specification without violating frozen boundaries.

---

**PHASE A SPECIFICATION — END**
