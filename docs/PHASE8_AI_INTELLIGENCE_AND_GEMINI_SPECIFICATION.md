# REVIVE — Phase 8 AI Intelligence & Gemini Specification

**Version:** 1.0.0
**Phase:** 8 — AI Intelligence & Gemini Integration
**Status:** Architecture Specification — Implementation Not Started
**Depends On:** Phases 1–7
**Primary AI:** Google Gemini via the official Gemini API/SDK
**Environment:** Development / Test Mode only during Phase 8

---

## 1. Purpose

Phase 8 introduces a controlled AI intelligence layer into REVIVE.

The purpose is **not** to replace the deterministic REVIVE decision system with an LLM.

The purpose is to use Gemini where language-model reasoning provides measurable value over deterministic rules, while keeping safety-critical decisions deterministic, bounded, auditable, and reproducible.

> **Gemini proposes intelligence; deterministic REVIVE components validate and govern it.**

---

## 2. Phase 8 Objective

Phase 8 must answer:

> Can an AI intelligence layer improve REVIVE's interpretation and explanation of customer evidence without compromising safety, determinism, attribution integrity, or intervention policy?

The phase has two goals:

1. Integrate Gemini behind a strict internal abstraction.
2. Evaluate whether Gemini materially improves evidence synthesis, diagnosis support, and explanations compared with the deterministic baseline.

---

## 3. What Gemini Is Allowed To Do

Gemini may assist with:

- synthesizing observable customer evidence;
- interpreting heterogeneous or semi-structured evidence;
- producing structured diagnosis candidates;
- identifying supporting evidence from supplied observable context;
- generating human-readable explanations;
- resolving linguistic ambiguity in evidence;
- producing bounded confidence and uncertainty annotations;
- explaining why a deterministic diagnosis may be uncertain or insufficiently grounded.

Gemini output is always a **proposal or interpretation**, never an authorization.

---

## 4. What Gemini Must NOT Do

Gemini must not:

- directly execute an intervention;
- directly call the Razorpay API;
- select an unconstrained monetary incentive;
- bypass Phase 5 eligibility or safety rules;
- override a deterministic policy rejection;
- access hidden simulator ground truth;
- access `ground_truth.jsonl`;
- use `true_root_cause`, `natural_conversion`, or `recoverable`;
- invent customer events, payment outcomes, or evidence;
- directly modify risk scores or revenue-at-risk;
- determine final attribution, recovered revenue, or ROI;
- make final safety decisions.

Mandatory chain:

```text
Gemini
  ↓
Structured AI Output
  ↓
Schema Validation
  ↓
Evidence / Grounding Validation
  ↓
Deterministic Diagnosis / Policy
  ↓
Phase 5 Decision Engine
  ↓
Phase 6 Execution
```

---

## 5. Architectural Position

Phase 8 sits primarily around the evidence and diagnosis layer:

```text
Observable Customer Events
          │
          ▼
   Evidence Extraction
          │
     ┌────┴────┐
     ▼         ▼
Deterministic Gemini
  Baseline Intelligence
     │         │
     │         ▼
     │   Structured Candidate
     │         │
     └────┬────┘
          ▼
 AI / Evidence Validator
          │
          ▼
 Canonical CustomerDiagnosis
          │
          ▼
 Phase 5 Decision Engine
          │
          ▼
 Phase 6 Execution
          │
          ▼
 Phase 7 Outcome Engine
```

Gemini must not become a parallel execution or policy engine.

---

## 6. AI Integration Boundary

Use an internal abstraction rather than direct Gemini SDK calls throughout the codebase.

Recommended conceptual layout:

```text
app/ai/
    __init__.py
    config.py
    client.py
    schemas.py
    prompts.py
    grounding.py
    validator.py
    service.py
    evaluation.py
```

The exact layout may vary if the same boundary is preserved.

Business logic must depend on the internal AI interface, not directly on the Gemini SDK.

This enables deterministic test doubles, model replacement, offline testing, failure isolation, and API-key isolation.

---

## 7. Model/API Contract

Gemini must be accessed through the official Google Gemini API/SDK.

The model identifier must be configurable and never scattered through application code.

Configuration must support at minimum:

- model identifier;
- API key reference;
- request timeout;
- maximum output size;
- temperature;
- retry limit;
- test-mode flag;
- structured-output requirement.

Secrets must come from environment/configuration and never be committed.

Example variable:

```text
GEMINI_API_KEY
```

The secret must never appear in source code, tests, documentation, logs, or evaluation output.

---

## 8. Structured Output Contract

Gemini must return structured output validated against a strict application schema.

Conceptually:

```text
AIAnalysis
├── diagnosis_candidate
├── confidence
├── actionability
├── supporting_evidence[]
├── uncertainty_reasons[]
├── explanation
└── model_metadata
```

Reject malformed responses, unsupported diagnosis/evidence categories, fabricated event identifiers, invalid confidence values, and unsupported action recommendations.

Free-form model text must never be treated as an authoritative diagnosis.

---

## 9. Evidence Grounding

Every accepted AI-supported claim must be grounded in evidence supplied to the model.

The validator must verify that referenced evidence corresponds to observable input.

Example:

```text
Observed:
payment_failed
error_code = CARD_DECLINED

Valid:
CARD_DECLINED

Invalid:
"Customer's bank permanently blocked the card"
```

Unsupported claims must cause rejection or deterministic fallback.

---

## 10. Deterministic Fallback

Gemini is optional. The core pipeline must remain fully operational without it.

If Gemini:

- times out;
- returns malformed output;
- violates schema;
- produces unsupported evidence;
- exceeds limits;
- is unavailable;
- returns insufficient confidence;

REVIVE must fall back safely to the deterministic Phase 4 diagnosis path.

```text
Gemini unavailable
      ↓
Deterministic diagnosis
      ↓
Phase 5 policy
```

A Gemini outage must never prevent a safe `NO_ACTION`.

---

## 11. Confidence and Uncertainty

AI confidence must not be treated as calibrated probability without evaluation.

The system must distinguish:

- high-confidence interpretation;
- low-confidence interpretation;
- insufficient evidence;
- validation failure;
- AI unavailable.

Low-confidence or ambiguous AI results should prefer deterministic fallback rather than forcing an intervention.

---

## 12. Phase 5 Separation

Phase 5 remains authoritative for intervention selection.

If Gemini proposes an action, Phase 5 independently determines whether it is permitted, eligible, safe, economically justified, consistent with diagnosis, and within configured bounds.

Gemini cannot override a Phase 5 rejection.

---

## 13. Phase 7 Separation

Gemini must not determine:

- whether revenue is recovered;
- whether revenue is attributable;
- attribution percentage;
- intervention cost;
- net recovered revenue;
- ROI.

Phase 7 remains authoritative for outcome measurement and accounting.

---

## 14. Prompt Architecture

Prompts must be versioned and application-controlled.

Prompts must define:

1. role;
2. supplied evidence;
3. allowed diagnosis taxonomy;
4. evidence-grounding rules;
5. uncertainty behavior;
6. structured output schema;
7. prohibited behavior.

Prompts must not include hidden simulator labels.

Prompt versions should be recorded in AI analysis metadata.

---

## 15. Context Minimization

Only information necessary for the AI task should be sent.

Permitted context may include:

- relevant event types;
- event timestamps;
- observable payment status;
- observable error codes;
- customer journey context;
- deterministic evidence categories.

Do not send:

- hidden ground truth;
- unnecessary personal data;
- payment credentials;
- API keys;
- secrets.

---

## 16. Privacy and Security

Gemini is an external service boundary.

The implementation must minimize transmitted data, avoid payment credentials, avoid unnecessary PII, redact credentials/tokens, and log metadata rather than sensitive raw payloads where appropriate.

Phase 8 must remain synthetic/sandboxed.

---

## 17. Test Mode

Default development mode should use a deterministic mock provider:

```text
AI_PROVIDER=mock
```

Gemini may be explicitly enabled:

```text
AI_PROVIDER=gemini
```

Unit tests must not require live Gemini availability.

Live Gemini calls belong only in explicit integration/evaluation tests.

---

## 18. Deterministic Mock Provider

A deterministic mock provider is mandatory.

Given identical input evidence, prompt version, and configuration, the mock must produce identical output.

This allows complete offline testing without network access.

---

## 19. Failure Handling

AI failures must be classified explicitly:

```text
AI_SUCCESS
AI_TIMEOUT
AI_RATE_LIMITED
AI_UNAVAILABLE
AI_SCHEMA_INVALID
AI_GROUNDING_FAILED
AI_LOW_CONFIDENCE
AI_PROVIDER_ERROR
```

Failures must be auditable and must not silently become successful AI diagnoses.

---

## 20. Observability

Each AI analysis should carry sufficient metadata for auditability:

```text
analysis_id
customer_id
context_timestamp
provider
model
prompt_version
schema_version
status
latency_ms
confidence
fallback_used
validation_status
```

Do not store secrets or unrestricted sensitive model responses.

---

## 21. Evaluation Framework

Compare at least:

### Baseline A
Existing deterministic Phase 4 diagnosis.

### Baseline B
Gemini-assisted diagnosis.

### Final System
Gemini proposal + deterministic validation + deterministic policy.

Measure:

- diagnosis agreement;
- evidence grounding accuracy;
- unsupported-claim rate;
- schema validity;
- fallback rate;
- actionable diagnosis precision/recall where measurable;
- explanation usefulness;
- latency;
- failure rate;
- cost per analysis;
- safety-policy compliance.

Live inference must not use hidden ground truth.

Hidden labels may only be used in offline evaluation where consistent with the existing evaluation methodology.

---

## 22. AI Quality Gates

Phase 8 must not be considered complete merely because Gemini returns valid JSON.

Minimum gates:

1. Structured-output validity ≥ 99% in evaluation.
2. Grounding violations = 0 for accepted production-path outputs.
3. Deterministic fallback operates successfully.
4. No hidden ground-truth fields reach Gemini input.
5. No Gemini output bypasses Phase 5.
6. No live Razorpay endpoint is called.
7. API secrets are absent from repository and logs.
8. Unit tests pass without network access.
9. Integration failures degrade safely.
10. AI-assisted results are auditable.

Exact thresholds may be refined after baseline evaluation.

---

## 23. Cost and Latency Controls

Configuration must include:

- maximum input context;
- maximum output tokens;
- timeout;
- retry limit;
- model selection;
- sampling controls.

Do not automatically make repeated Gemini calls for one decision unless explicitly configured.

Caching may be used for identical requests where appropriate.

---

## 24. No Direct Razorpay Dependency

Phase 8 must not introduce live Razorpay API calls.

Razorpay integration belongs to the subsequent payment-infrastructure phase.

Gemini may interpret synthetic/sandbox payment evidence but must not directly interact with Razorpay.

---

## 25. AI Explanation Layer

Phase 8 should explain:

- why a customer is considered at risk;
- what observable evidence supports the diagnosis;
- what evidence is missing;
- why the diagnosis is uncertain;
- why deterministic policy proceeded or fell back.

Explanations must remain grounded in observable evidence.

---

## 26. AI Does Not Become the Product

REVIVE remains the product.

```text
REVIVE
├── Risk Engine
├── Diagnosis Engine
├── Intervention Engine
├── Execution Engine
├── Outcome Engine
└── AI Intelligence Layer
```

Not:

```text
Gemini
└── REVIVE
```

---

## 27. Required Deliverables

Implementation should produce, at minimum:

```text
app/ai/
tests/test_ai_service.py
tests/test_ai_grounding.py
tests/test_ai_fallback.py
scripts/evaluate_ai.py
scripts/manual_test_phase8.py
```

and any additional files required by the established architecture.

---

## 28. Required Manual Scenarios

At minimum:

### S1 — Valid Gemini diagnosis
Valid structured AI output is accepted.

### S2 — Malformed AI output
Invalid schema falls back safely.

### S3 — Unsupported evidence
Grounding validator rejects fabricated evidence.

### S4 — Low confidence
Low-confidence output falls back or remains non-actionable.

### S5 — Gemini unavailable
Deterministic diagnosis continues normally.

### S6 — Gemini timeout
Safe fallback occurs.

### S7 — Policy boundary
Gemini cannot bypass Phase 5 safety rules.

### S8 — AI cannot execute
Gemini has no direct execution authority.

### S9 — Hidden ground-truth isolation
No simulator truth reaches Gemini.

### S10 — Deterministic mock
Identical inputs produce identical mock outputs.

### S11 — Prompt/schema versioning
Analysis metadata records versions.

### S12 — Sensitive-data protection
Secrets and unnecessary sensitive fields are not transmitted/logged.

---

## 29. Phase 8 Completion Gate

Phase 8 is complete only after:

```text
Architecture specification
        ↓
Gemini abstraction
        ↓
Deterministic mock
        ↓
Structured output validation
        ↓
Grounding validation
        ↓
Safe fallback
        ↓
Phase 4 integration
        ↓
Phase 5 policy protection
        ↓
Evaluation
        ↓
Manual testing
        ↓
Full regression
        ↓
Security / secret scan
        ↓
Git verification
```

All gates must pass before closure.

---

## 30. Definition of Done

Phase 8 is closed only when:

- Gemini integration exists behind an internal provider abstraction;
- deterministic mock mode exists;
- structured output is validated;
- evidence grounding is enforced;
- unsupported claims are rejected;
- deterministic fallback works;
- Phase 5 remains authoritative;
- Phase 6 remains unchanged;
- Phase 7 remains authoritative;
- no hidden simulator truth reaches AI;
- no secrets are committed;
- no live Razorpay integration exists;
- manual tests pass;
- full regression tests pass;
- AI evaluation completes successfully;
- repository is clean;
- implementation is committed;
- remote branch is synchronized.

---

## 31. Architectural Principle

> **AI may increase REVIVE's understanding, but it may never decrease REVIVE's control.**

Gemini is an intelligence amplifier, not an autonomous decision-maker.

---

## 32. Next Phase Boundary

After Phase 8 is closed, the next infrastructure phase may introduce a Razorpay sandbox adapter:

```text
REVIVE Internal Payment Interface
              ↓
      Razorpay Adapter
              ↓
       Razorpay Sandbox
```

The Razorpay provider must remain replaceable and provider-specific contracts must not leak into the REVIVE core.
