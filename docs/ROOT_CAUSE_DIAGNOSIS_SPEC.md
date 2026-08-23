# REVIVE â€” Root-Cause Diagnosis Specification

**Razorpay AI Buildathon 2026 â€” Track 03: AI Revenue Recovery**

**\*\*Version:\*\* 1.0**

**\*\*Phase:\*\* 4 â€” Root-Cause Diagnosis**

**\*\*Status:\*\* Implementation specification**

**\*\*Parent:\*\* `REVIVE\\\_BUILD\\\_CONSTITUTION.md`**

**Depends on:** Phase 1 Event/Data Model, Phase 2 Synthetic Journey Generator, Phase 3 Revenue Risk Engine

\---

## 1\. Purpose

Phase 4 answers:

> \\\*\\\*Why is this customer's future subscription revenue at risk?\\\*\\\*

Phase 3 identifies customers with elevated conversion-failure risk. Phase 4 transforms that risk signal into an evidence-grounded diagnosis using only observable customer-journey information available at the Phase 3 prediction snapshot.

The diagnosis must provide:

1. a primary root-cause category;
2. supporting observable evidence;
3. a confidence score;
4. competing candidate causes where appropriate;
5. an explicit uncertainty state when evidence is insufficient or conflicting.

Phase 4 must not choose or execute a recovery action.

\---

## 2\. Phase Boundary

```text
Risk-scored customer
        â†“
Observable evidence extraction
        â†“
Candidate cause generation
        â†“
Evidence scoring
        â†“
Primary diagnosis
        â†“
Confidence / uncertainty
        â†“
Diagnostic explanation
```

Do NOT implement in this phase:

* recovery action selection;
* intervention execution;
* policy authorization;
* Razorpay API calls;
* discounts;
* payment retries;
* customer messaging;
* treatment/control assignment;
* recovery measurement;
* frontend/dashboard;
* unrestricted LLM agent.

\---

## 3\. Input Contract

The diagnosis engine receives Phase 3 outputs:

```text
customer\\\_id
prediction\\\_timestamp
risk\\\_score
risk\\\_tier
plan\\\_id
plan\\\_price
revenue\\\_at\\\_risk
```

and observable journey data:

```text
customers.jsonl
plans.jsonl
events.jsonl
```

The diagnosis engine must not require:

```text
ground\\\_truth.jsonl
```

for inference.

\---

## 4\. Strict Ground-Truth Separation

The following fields are forbidden during inference:

```text
generation\\\_segment
natural\\\_conversion
conversion\\\_after\\\_intervention
recoverable
maximum\\\_recoverable\\\_revenue
true\\\_root\\\_cause
```

Ground truth may be loaded only by an offline evaluation harness.

Add a test proving diagnosis can run when `ground\\\_truth.jsonl` is absent.

\---

## 5\. Temporal Boundary

Diagnosis must use the same prediction snapshot as Phase 3:

```text
prediction\\\_timestamp =
    trial\\\_start + 72 hours,
    capped at trial\\\_end
```

Only events satisfying:

```text
event.timestamp <= prediction\\\_timestamp
```

may influence diagnosis.

No future event may influence diagnosis, including future:

```text
checkout\\\_completed
payment\\\_succeeded
subscription\\\_created
trial\\\_expired
```

\---

## 6\. Diagnostic Eligibility

Only customers eligible for Phase 3 risk scoring enter normal diagnosis.

If observable state proves that a customer has already converted, return:

```text
diagnosis = ALREADY\\\_CONVERTED
actionability = NONE
```

If insufficient evidence exists:

```text
diagnosis = INSUFFICIENT\\\_EVIDENCE
```

A diagnosis never authorizes an intervention.

\---

## 7\. Diagnostic Taxonomy

Implement this deliberately small taxonomy:

```text
NO\\\_MEANINGFUL\\\_RISK
LOW\\\_INTENT
CHECKOUT\\\_ABANDONMENT
PAYMENT\\\_FRICTION
TRIAL\\\_EXPIRATION
ENGAGEMENT\\\_DECLINE
MIXED\\\_SIGNALS
INSUFFICIENT\\\_EVIDENCE
ALREADY\\\_CONVERTED
```

These categories are grounded in the existing observable journey and the Phase 2 synthetic scenarios.

`ALREADY\\\_CONVERTED` is terminal and is not a recovery opportunity.

\---

## 8\. Diagnosis Is Not Ground Truth

The engine produces an inferred diagnosis.

The hidden:

```text
true\\\_root\\\_cause
```

exists only for offline evaluation.

Never infer a diagnosis from:

```text
generation\\\_segment
```

For example:

```text
PAYMENT\\\_FRICTION
```

means observable payment evidence is strongest. It does not mean the customer was generated in the `payment\\\_friction` segment.

\---

## 9\. Evidence Philosophy

Every diagnosis must be explainable using observable evidence.

Risk identifies:

```text
WHO is at risk
```

Diagnosis identifies:

```text
WHY the customer appears at risk
```

A high risk score alone is never sufficient evidence for a root cause.

Specific evidence should outrank generic risk signals.

\---

## 10\. Evidence Object

Represent supporting signals as structured objects:

```json
{
  "evidence\\\_type": "PAYMENT\\\_FAILURE",
  "strength": 1.0,
  "source\\\_event": "payment\\\_failed",
  "description": "Payment attempt failed before the prediction snapshot."
}
```

Required fields:

```text
evidence\\\_type
strength
source\\\_event
description
```

Include `observed\\\_at` when useful.

\---

## 11\. Evidence Categories

Initial categories:

```text
PAYMENT\\\_ATTEMPT
PAYMENT\\\_FAILURE
PAYMENT\\\_SUCCESS
CHECKOUT\\\_STARTED
CHECKOUT\\\_COMPLETED
CHECKOUT\\\_ABANDONED
PAYMENT\\\_METHOD\\\_ADDED
PRICING\\\_VIEW
SESSION\\\_ACTIVITY
FEATURE\\\_USAGE
PRODUCT\\\_ACTIVITY
RECENCY\\\_DECLINE
TRIAL\\\_EXPIRY\\\_PROXIMITY
CONVERSION\\\_STATE
```

Use only event types and fields actually supported by the existing Phase 2 schema.

Do not invent data.

\---

## 12\. Payment Friction

Strong evidence:

```text
payment\\\_attempted == true
AND
payment\\\_failed == true
```

Additional evidence:

```text
payment\\\_method\\\_added == true
checkout\\\_started == true
pricing\\\_view\\\_count > 0
```

Supported synthetic failure reasons may include:

```text
bank\\\_declined
insufficient\\\_funds
payment\\\_method\\\_error
temporary\\\_processing\\\_failure
```

These are synthetic categories and must not be presented as real Razorpay statistics.

\---

## 13\. Checkout Abandonment

Strong evidence:

```text
checkout\\\_started == true
AND
checkout\\\_completed == false
AND
payment\\\_succeeded == false
```

Additional supporting evidence:

```text
payment\\\_method\\\_added == true
pricing\\\_view\\\_count > 0
meaningful session activity
meaningful feature usage
```

A high-intent abandoned checkout should be distinguished from a customer who barely engaged.

\---

## 14\. Trial Expiration

Strong evidence:

```text
hours\\\_until\\\_trial\\\_expiry <= 24
```

Additional evidence:

```text
trial\\\_expiring\\\_soon == true
checkout\\\_not\\\_completed
payment\\\_not\\\_succeeded
```

Trial expiry should not automatically dominate when there is substantially stronger evidence of payment friction or checkout abandonment.

\---

## 15\. Low Intent

Evidence may include:

```text
low session count
low feature-use count
low product-activity count
few or no pricing views
no checkout start
no payment attempt
```

Low intent should be diagnosed only when commercial-intent signals are also weak.

A customer with strong engagement and a failed payment should not be classified as low intent simply because they have not converted.

\---

## 16\. Engagement Decline

Engagement decline is different from consistently low engagement.

Use:

```text
recent activity recency
```

together with evidence that the customer previously showed meaningful activity.

Example:

```text
high historical activity
+
large recent inactivity gap
```

may support:

```text
ENGAGEMENT\\\_DECLINE
```

A customer who was always inactive is better classified as:

```text
LOW\\\_INTENT
```

\---

## 17\. Mixed Signals

Use:

```text
MIXED\\\_SIGNALS
```

when multiple causes have substantial evidence and no single cause clearly dominates.

Example:

```text
checkout\\\_started
payment\\\_method\\\_added
payment\\\_failed
trial\\\_expiring\\\_soon
```

Possible candidates:

```text
PAYMENT\\\_FRICTION
CHECKOUT\\\_ABANDONMENT
TRIAL\\\_EXPIRATION
```

If evidence scores are close, do not fabricate certainty.

Return the competing causes.

\---

## 18\. Insufficient Evidence

Return:

```text
INSUFFICIENT\\\_EVIDENCE
```

when:

* too few observable events exist;
* no candidate has sufficient support;
* signals conflict without a clear winner;
* required timestamps are missing;
* customer state cannot be safely reconstructed.

Uncertainty is a valid output.

\---

## 19\. Evidence Scoring

Use an explicit deterministic evidence-scoring system.

Initial configuration:

```text
strong evidence      = 1.00
moderate evidence    = 0.60
weak evidence        = 0.25
contradictory signal = negative contribution
```

Centralize these weights in configuration.

Do not scatter magic numbers throughout the implementation.

\---

## 20\. Candidate Scores

For each candidate cause:

```text
candidate\\\_score =
    supporting evidence
    -
    contradictory evidence
```

Normalize candidate scores into a comparable range.

Every scoring rule must be documented.

\---

## 21\. Primary Diagnosis

Select the highest-scoring candidate only when it has sufficient evidence.

Return:

```text
primary\\\_diagnosis
confidence
supporting\\\_evidence
```

If the top candidates are within the configured ambiguity margin:

```text
primary\\\_diagnosis = MIXED\\\_SIGNALS
```

Do not force a winner when the evidence does not justify one.

\---

## 22\. Confidence

Confidence means:

> How strongly the observable evidence supports the selected diagnosis relative to competing explanations.

It is NOT automatically:

```text
P(true\\\_root\\\_cause)
```

unless a separately calibrated probabilistic model is introduced.

The initial implementation uses evidence-based confidence.

\---

## 23\. Confidence Tiers

Initial tiers:

```text
LOW:
confidence < 0.50

MEDIUM:
0.50 <= confidence < 0.75

HIGH:
0.75 <= confidence < 0.90

VERY\\\_HIGH:
confidence >= 0.90
```

These are diagnosis-confidence tiers, not risk tiers.

\---

## 24\. Risk and Diagnosis Stay Separate

For example:

```text
risk\\\_score = 0.89
diagnosis\\\_confidence = 0.61
```

is valid.

A customer can be highly likely to fail conversion while the reason remains uncertain.

Never copy the risk score into diagnosis confidence.

\---

## 25\. Diagnostic Output

Produce a structured result such as:

```json
{
  "customer\\\_id": "cus\\\_005369",
  "prediction\\\_timestamp": "2026-08-06T19:00:21+00:00",
  "risk\\\_score": 0.7314,
  "risk\\\_tier": "HIGH",
  "diagnosis": "CHECKOUT\\\_ABANDONMENT",
  "confidence": 0.86,
  "confidence\\\_tier": "HIGH",
  "actionability": "CANDIDATE",
  "candidate\\\_causes": \\\[
    {
      "cause": "CHECKOUT\\\_ABANDONMENT",
      "score": 0.86
    },
    {
      "cause": "TRIAL\\\_EXPIRATION",
      "score": 0.48
    }
  ],
  "supporting\\\_evidence": \\\[]
}
```

Do not include hidden ground truth.

\---

## 26\. Actionability State

Use:

```text
NONE
CANDIDATE
REQUIRES\\\_REVIEW
```

### NONE

For:

* already converted;
* risk below configured threshold;
* no reliable diagnosis.

### CANDIDATE

When evidence is sufficiently strong for downstream decision-making.

### REQUIRES\_REVIEW

When confidence is low, evidence conflicts, or the case is unusual.

This field does not authorize an intervention.

\---

## 27\. Deterministic Explanation

Every diagnosis must produce a concise explanation.

Example:

```text
Primary diagnosis: PAYMENT\\\_FRICTION

Why:
- checkout was started;
- a payment method was added;
- a payment attempt failed;
- no successful payment occurred before the prediction snapshot.

Confidence: HIGH (0.91)
```

The explanation must be generated from structured evidence.

Never invent facts.

\---

## 28\. LLM Boundary

The core diagnosis must work without an LLM.

This is intentional because the first implementation must be:

* reproducible;
* inspectable;
* auditable;
* deterministic.

An LLM may later summarize structured evidence, but:

```text
AI may summarize evidence.
AI must not invent evidence.
AI must not override event data.
AI must not authorize financial actions.
```

\---

## 29\. Conflict Resolution

Use evidence score as the primary mechanism.

Only for true ties, use this deterministic tie-break order:

```text
ALREADY\\\_CONVERTED
PAYMENT\\\_FRICTION
CHECKOUT\\\_ABANDONMENT
TRIAL\\\_EXPIRATION
ENGAGEMENT\\\_DECLINE
LOW\\\_INTENT
```

The tie-breaker must never override materially stronger evidence for another diagnosis.

\---

## 30\. Example Cases

### Payment friction

```text
pricing\\\_viewed
checkout\\\_started
payment\\\_method\\\_added
payment\\\_attempted
payment\\\_failed
```

â†’ `PAYMENT\\\_FRICTION`

### Checkout abandonment

```text
session\\\_started
feature\\\_used
pricing\\\_viewed
checkout\\\_started
payment\\\_method\\\_added
checkout\\\_abandoned
```

with no payment failure

â†’ `CHECKOUT\\\_ABANDONMENT`

### Trial expiration

```text
meaningful activity
pricing\\\_viewed
no checkout completion
hours\\\_until\\\_trial\\\_expiry <= 24
```

â†’ `TRIAL\\\_EXPIRATION`

### Low intent

```text
few sessions
few feature uses
little/no pricing activity
no checkout
no payment attempt
```

â†’ `LOW\\\_INTENT`

### Mixed signals

```text
checkout\\\_started
payment\\\_method\\\_added
payment\\\_failed
trial\\\_expiring\\\_soon
```

with close candidate scores

â†’ `MIXED\\\_SIGNALS`

### Already converted

```text
payment\\\_succeeded
checkout\\\_completed
subscription\\\_created
```

â†’ `ALREADY\\\_CONVERTED`

\---

## 31\. Offline Evaluation

The diagnosis engine must be evaluated against hidden ground truth.

The evaluation harness may load:

```text
ground\\\_truth.jsonl
```

and compare:

```text
predicted diagnosis
```

with:

```text
true\\\_root\\\_cause
```

The diagnosis engine itself must never receive the hidden field.

\---

## 32\. Required Metrics

Report:

```text
overall accuracy
macro precision
macro recall
macro F1
confusion matrix
```

Also report per-class:

```text
precision
recall
F1
support
```

At minimum evaluate:

```text
LOW\\\_INTENT
CHECKOUT\\\_ABANDONMENT
PAYMENT\\\_FRICTION
TRIAL\\\_EXPIRATION
MIXED\\\_SIGNALS
```

and report applicable:

```text
ALREADY\\\_CONVERTED
INSUFFICIENT\\\_EVIDENCE
```

Accuracy alone is insufficient.

\---

## 33\. Diagnostic Coverage

Report:

```text
diagnosis\\\_coverage =
confidently diagnosed customers /
eligible customers
```

Also report:

```text
uncertain\\\_rate
requires\\\_review\\\_rate
```

A system that confidently diagnoses every customer is suspicious.

\---

## 34\. Evidence Consistency

For every predicted diagnosis, verify that the supporting evidence actually exists in the observable journey.

For example:

```text
PAYMENT\\\_FRICTION
```

must have observable payment-attempt and payment-failure evidence.

Report:

```text
evidence\\\_consistency\\\_rate
```

A diagnosis without supporting evidence is a diagnostic failure.

\---

## 35\. Leakage Tests

Add tests proving:

1. diagnosis works without `ground\\\_truth.jsonl`;
2. hidden fields cannot enter evidence;
3. generation segments cannot influence candidate scores;
4. `true\\\_root\\\_cause` cannot be read by inference code;
5. future events cannot influence diagnosis.

\---

## 36\. Temporal Leakage Tests

Create journeys where these events happen after the prediction timestamp:

```text
payment\\\_failed
checkout\\\_completed
payment\\\_succeeded
subscription\\\_created
trial\\\_expired
```

Verify that future events do not change the diagnosis.

\---

## 37\. Determinism

For identical observable input and configuration:

```text
diagnosis
confidence
candidate scores
evidence
explanation
```

must be identical.

No randomness is permitted in the core diagnosis engine.

\---

## 38\. Required Code Structure

Implement approximately:

```text
app/
â””â”€â”€ diagnosis/
    â”œâ”€â”€ \\\_\\\_init\\\_\\\_.py
    â”œâ”€â”€ config.py
    â”œâ”€â”€ evidence.py
    â”œâ”€â”€ rules.py
    â”œâ”€â”€ engine.py
    â”œâ”€â”€ schemas.py
    â”œâ”€â”€ explanations.py
    â””â”€â”€ evaluation.py

scripts/
â””â”€â”€ evaluate\\\_diagnosis.py

tests/
â””â”€â”€ test\\\_diagnosis\\\_engine.py
```

Reuse existing Phase 1 event models and Phase 3 risk schemas.

Do not duplicate existing models unnecessarily.

\---

## 39\. Configuration

Centralize:

```text
diagnosis weights
confidence thresholds
ambiguity margin
risk eligibility threshold
minimum evidence threshold
configuration version
```

Store the configuration version with evaluation results.

\---

## 40\. Phase 2 Compatibility

Do not modify the Phase 2 synthetic generator merely to make diagnosis easier.

The diagnosis engine must work against the existing 20,000-customer dataset.

If an observable field genuinely required by this specification is missing, stop and report the gap before modifying Phase 2.

Never add hidden labels to observable events.

\---

## 41\. Phase 3 Compatibility

Do not modify the Phase 3 risk model merely because diagnosis is being added.

Phase 3 remains the source of:

```text
risk\\\_score
risk\\\_tier
revenue\\\_at\\\_risk
prediction\\\_timestamp
```

Phase 4 consumes those outputs.

\---

## 42\. Required Tests

At minimum test:

### Eligibility

* low-risk customer;
* already-converted customer;
* insufficient-data customer.

### Payment friction

* payment attempted + failed;
* each supported failure reason;
* future payment failure ignored.

### Checkout abandonment

* checkout started + abandoned;
* checkout completed prevents abandonment diagnosis;
* future checkout completion ignored.

### Trial expiration

* <=24 hours;
* >24 hours;
* future trial expiration ignored.

### Low intent

* low activity;
* weak commercial intent.

### Engagement decline

* previously active + recent inactivity;
* consistently inactive prefers low intent.

### Mixed signals

* competing strong causes;
* ambiguity margin.

### Leakage

* no ground truth required;
* hidden fields rejected;
* future events rejected.

### Determinism

* identical input produces identical output.

### Evidence consistency

* every diagnosis has valid observable evidence.

\---

## 43\. Phase 4 Definition of Done

Phase 4 is complete only when:

* observable journeys produce structured evidence;
* the Phase 3 prediction snapshot is reused;
* hidden ground truth is never used during inference;
* future events are excluded;
* the diagnosis taxonomy is implemented;
* candidate causes are scored deterministically;
* a primary diagnosis is selected when justified;
* confidence is calculated separately from risk;
* ambiguity is represented explicitly;
* insufficient evidence is represented explicitly;
* structured supporting evidence is returned;
* deterministic explanations are generated;
* diagnosis works without an LLM;
* diagnosis works without Razorpay API;
* diagnosis works without ground truth;
* offline evaluation works;
* macro precision/recall/F1 are reported;
* confusion matrix is reported;
* evidence consistency is measured;
* leakage tests pass;
* determinism tests pass;
* all Phase 1â€“4 tests pass.

\---

## 44\. Phase 4 Success Principle

The system must be able to say:

```text
Customer:
cus\\\_005369

Risk:
0.7314

Revenue at Risk:
â‚¹7,312.82

Diagnosis:
CHECKOUT\\\_ABANDONMENT

Confidence:
0.86

Evidence:
- checkout started
- payment method added
- checkout not completed
- meaningful product engagement
```

without saying:

```text
Customer belongs to checkout\\\_abandoner segment.
```

The first is evidence-grounded diagnosis.

The second uses hidden simulator information.

\---

## 45\. Final Architecture

```text
                    OBSERVABLE JOURNEY
                           â”‚
                           â–¼
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚ RISK ENGINE â”‚
                    â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜
                           â”‚
              risk\\\_score / revenue\\\_at\\\_risk
                           â”‚
                           â–¼
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                 â”‚ EVIDENCE BUILDER â”‚
                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚
                   observable signals
                          â”‚
                          â–¼
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                 â”‚ DIAGNOSIS ENGINE â”‚
                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚
             â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
             â–¼            â–¼            â–¼
        Diagnosis     Confidence    Evidence
             â”‚
             â–¼
        PHASE 5
      DECISION ENGINE
```

Phase 4 ends at:

```text
DIAGNOSE
```

It does not cross into:

```text
DECIDE
GUARD
RECOVER
MEASURE
```

\---

# END OF SPECIFICATION
