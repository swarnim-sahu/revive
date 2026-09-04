# REVIVE PHASE D SPECIFICATION

**Version:** 1.0.0
**Phase:** D — Real Gemini Evaluation & AI Evidence
**Status:** SPECIFICATION FOR IMPLEMENTATION
**Parent:** `REVIVE_BUILD_CONSTITUTION.md`
**Dependencies:** Phase A Razorpay Test Mode proof + Phase B controlled evaluation + Phase C Command Center

---

## 1. Phase D Objective

Phase D establishes a **real, reproducible Gemini-backed evaluation path** for REVIVE's diagnosis layer and turns that evaluation into auditable evidence.

The purpose is **not** to replace the deterministic REVIVE decision system with an unconstrained LLM.

The purpose is to answer, with evidence:

> When REVIVE is given the same observable customer evidence, can Gemini produce a useful, structured, policy-compatible diagnosis that improves or validates the diagnosis stage without taking authority away from the governed intervention system?

Phase D must therefore preserve the existing separation:

```text
Observable customer evidence
        ↓
Risk detection
        ↓
Gemini diagnosis evaluation
        ↓
Structured diagnosis
        ↓
Existing governed intervention policy
        ↓
Existing execution guards
        ↓
Existing outcome + attribution
```

Gemini may **diagnose/evaluate**. It must not independently authorize money movement, intervention execution, retries, discounts, refunds, or policy overrides.

---

## 2. Non-Negotiable Constraints

### 2.1 Frozen engines remain frozen

Unless explicitly approved in a later phase, do not modify:

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

**Important:** Phase D is an evaluation/integration phase. The existence of Gemini work does not automatically authorize edits to the frozen `app/ai/*` implementation.

If an existing AI boundary cannot support the required evaluation cleanly, build an adapter/evaluation boundary around it rather than rewriting the frozen engine.

### 2.2 No production credentials

Do not use production Razorpay credentials, production customer data, production payment data, or real customer PII.

Gemini evaluation must use synthetic/redacted benchmark evidence only.

### 2.3 No autonomous execution

Gemini output must never directly trigger:

- payment links
- retries
- discounts
- refunds
- credits
- subscription changes
- customer communications
- Razorpay mutations
- policy overrides

All execution remains behind the existing governed intervention and execution layers.

### 2.4 No fabricated AI evidence

Do not:

- label deterministic output as Gemini output;
- invent model responses;
- invent Gemini latency/token/cost measurements;
- claim Gemini was used when it was unavailable;
- silently substitute deterministic fallback while presenting the result as real Gemini.

If Gemini is unavailable, the system must expose an explicit unavailable/fallback state.

### 2.5 Reproducibility

A Gemini evaluation record must identify, where available:

- model identifier;
- evaluation run identifier;
- timestamp;
- input evidence version/hash;
- prompt/template version;
- output schema version;
- model response or normalized response;
- latency;
- token usage if supplied by the provider;
- error state if the call failed;
- fallback state if fallback was used.

Secrets must never be persisted.

---

## 3. What Phase D Must Prove

Phase D should produce evidence for five questions.

### A. Can Gemini produce structured diagnoses?

Given a fixed evidence record, Gemini should return a constrained diagnosis object rather than free-form prose.

### B. Is the output schema-valid?

Malformed, incomplete, contradictory, or otherwise unusable model output must be rejected rather than silently accepted.

### C. Is the diagnosis useful?

Gemini diagnoses must be evaluated against the benchmark's available ground-truth/expected diagnosis labels and reported with appropriate metrics.

### D. Is Gemini safe to use inside REVIVE?

The evaluation must prove that Gemini cannot bypass eligibility, intervention policy, execution guards, or attribution.

### E. Is Gemini operationally observable?

The evaluation must expose enough metadata to distinguish:

```text
REAL GEMINI RESULT
MODEL UNAVAILABLE
MODEL ERROR
SCHEMA REJECTED
DETERMINISTIC FALLBACK
```

---

## 4. Phase D Architecture

The preferred architecture is:

```text
Benchmark Evidence
       │
       ▼
Gemini Evaluation Adapter
       │
       ├── Prompt Builder
       │
       ├── Gemini Client
       │
       ├── Structured Output Validator
       │
       └── Evaluation Recorder
       │
       ▼
Normalized Diagnosis Result
       │
       ▼
Existing Diagnosis / Intervention Boundary
       │
       ▼
Existing Policy + Guard + Execution
```

The Gemini adapter should be isolated from the core execution path.

A recommended conceptual interface is:

```text
GeminiDiagnosisEvaluator
    evaluate(evidence) -> GeminiDiagnosisResult
```

The exact implementation should follow the repository's existing architecture rather than introducing unnecessary abstractions.

---

## 5. Evidence Contract

Gemini must receive only observable evidence that the existing REVIVE system is permitted to use.

Examples may include:

- customer lifecycle state;
- plan;
- trial status;
- time until trial expiry;
- payment failure observations;
- payment history;
- engagement/activity observations;
- prior conversion state;
- revenue-at-risk estimate;
- relevant event history;
- bounded derived features already present in the evaluation dataset.

Do not expose hidden benchmark labels to the model.

For example, if the benchmark knows the expected diagnosis internally, that label must remain outside the Gemini prompt.

### Evidence versioning

Every evaluation record should make it possible to determine exactly which evidence representation was supplied.

Preferred:

```text
evidence_version
evidence_hash
```

The hash must be deterministic for the same canonical evidence payload.

---

## 6. Prompt Contract

The prompt must explicitly constrain Gemini to diagnosis rather than execution.

The model should be instructed to:

1. use only supplied evidence;
2. identify the most likely revenue-recovery diagnosis;
3. return only the required structured output;
4. state uncertainty through the defined confidence field;
5. avoid inventing facts;
6. avoid recommending actions outside the allowed diagnosis contract;
7. never claim that an action was executed.

The prompt itself must be versioned.

Example conceptual version:

```text
REVIVE_GEMINI_DIAGNOSIS_PROMPT_V1
```

Do not hard-code an undocumented prompt whose contents cannot be traced later.

---

## 7. Structured Output Contract

The model response must normalize into a bounded object containing, at minimum:

```text
diagnosis
confidence
rationale
evidence_used
```

Where repository-compatible fields already exist, reuse them rather than creating duplicate representations.

The allowed diagnosis vocabulary must be explicitly bounded by the REVIVE diagnosis contract.

The evaluator must reject:

- unknown diagnosis labels;
- missing required fields;
- invalid confidence values;
- unsupported action/execution claims;
- malformed JSON/structured output;
- evidence claims not grounded in the supplied evidence, where such validation is feasible.

A rejected model response is an evaluation outcome, not a successful diagnosis.

---

## 8. Gemini Provider Boundary

The provider client must be isolated behind a small boundary.

The implementation should make it possible to:

- configure the Gemini model;
- configure the API credential through environment variables;
- set reasonable request timeouts;
- distinguish authentication/configuration failures from model failures;
- capture provider metadata when available;
- avoid logging secrets or full sensitive request payloads.

Do not hard-code API keys.

Recommended environment-variable pattern:

```text
GEMINI_API_KEY
GEMINI_MODEL
```

If the existing repository already defines a different configuration convention, follow the existing convention rather than creating a conflicting one.

---

## 9. Failure Semantics

Phase D must explicitly distinguish at least:

```text
AVAILABLE
MODEL_ERROR
MODEL_UNAVAILABLE
SCHEMA_REJECTED
FALLBACK_USED
```

Fallback, if retained, must be explicit.

A safe conceptual flow is:

```text
Gemini call succeeds
    ↓
validate response
    ↓
valid → REAL GEMINI RESULT
invalid → SCHEMA REJECTED

Gemini call fails/unavailable
    ↓
MODEL ERROR / MODEL UNAVAILABLE
    ↓
optional deterministic fallback
    ↓
FALLBACK USED
```

The UI and evaluation artifacts must never collapse these states into a generic "AI success."

---

## 10. Evaluation Dataset

Phase D should use a deterministic synthetic evaluation set derived from the repository's existing benchmark evidence.

The evaluation must:

- use a fixed seed;
- use a fixed evidence representation;
- keep benchmark labels outside the model input;
- record the number of attempted model evaluations;
- record successful structured responses;
- record rejected responses;
- record unavailable/error responses;
- record fallback usage separately.

Do not silently change the Phase B benchmark itself.

If a Phase D-specific sample is required for cost/latency reasons, define it as a **separate evaluation artifact** and clearly distinguish it from the authoritative Phase B benchmark.

---

## 11. Metrics

At minimum report:

### Model output quality

- diagnosis accuracy;
- macro precision;
- macro recall;
- macro F1;
- per-diagnosis support/counts where meaningful.

### Operational reliability

- attempted evaluations;
- successful evaluations;
- schema rejections;
- model errors;
- unavailable evaluations;
- fallback count/rate;
- success rate;
- average latency;
- p95 latency if enough samples exist.

### Governance

- execution bypass attempts observed;
- policy/guard violations;
- unsupported action claims;
- safety compliance.

A safety result must be expressed as an observed evaluation metric, not as a blanket claim that the model is inherently safe.

---

## 12. Cost Accounting

If Gemini/provider usage metadata supplies token counts or billable usage information, record it.

If reliable provider pricing is configured, report estimated evaluation cost.

If cost cannot be determined reliably, report:

```text
COST DATA UNAVAILABLE
```

Do not fabricate a dollar/rupee amount.

The evaluation artifact should distinguish:

```text
provider-reported usage
estimated cost
cost unavailable
```

---

## 13. Evidence Artifact

Phase D must create a committed, machine-readable evidence artifact under:

```text
docs/evidence/
```

Recommended filename:

```text
phase_d_gemini_evaluation.json
```

The artifact should contain enough information to reproduce and audit the evaluation without containing secrets.

At minimum include:

```text
metadata
model
prompt_version
evidence_version
evaluation_counts
quality_metrics
operational_metrics
governance_metrics
cost
failure_summary
reproducibility
```

The artifact must not contain:

- API keys;
- authorization headers;
- secrets;
- unnecessary personal data;
- production customer information.

---

## 14. Command-Line Evaluation

Phase D should provide a deterministic command for running the evaluation.

For example, conceptually:

```powershell
py -m app.evaluation.phase_d_gemini
```

The exact module/command should follow repository conventions.

The command should:

1. load the controlled evaluation evidence;
2. initialize the Gemini adapter;
3. execute the requested evaluation;
4. validate outputs;
5. compute metrics;
6. write the evidence artifact;
7. print a concise summary;
8. clearly report unavailable/error/fallback states.

It must not mutate customer state or invoke production integrations.

---

## 15. API / Presentation Requirements

If Phase C's Command Center is extended for Phase D, the UI must clearly distinguish:

### Real Gemini

```text
GEMINI — REAL EVALUATION
```

### Unavailable

```text
GEMINI — UNAVAILABLE
```

### Error

```text
GEMINI — ERROR
```

### Fallback

```text
GEMINI — FALLBACK USED
```

Never show:

```text
AI SUCCESS
```

when the underlying result is actually deterministic fallback.

Any Phase D dashboard metrics must be sourced from the committed Phase D evidence artifact or the authoritative evaluation result, with no fabricated frontend constants.

---

## 16. Testing Requirements

Add focused automated tests for:

### Provider boundary

- configuration present;
- missing API key;
- provider error;
- timeout/error classification.

### Output validation

- valid diagnosis;
- invalid diagnosis;
- malformed response;
- missing confidence;
- out-of-range confidence;
- unsupported execution/action claim.

### Evidence handling

- deterministic evidence hashing;
- hidden ground-truth labels are not included in model input;
- secrets are not persisted.

### Evaluation

- metrics are calculated correctly;
- unavailable/error/fallback counts reconcile;
- no model result is mislabeled as real Gemini.

### Governance

- Gemini output cannot directly execute an intervention;
- existing guards remain authoritative.

### Regression

Run the full existing suite:

```powershell
py -m pytest
```

And frontend checks where applicable:

```powershell
cd frontend
npm run build
npm run lint
```

---

## 17. Manual Validation Requirements

Automated tests are not sufficient.

After implementation, manually verify:

1. A real Gemini request is actually made when credentials are configured.
2. The returned model identity is recorded correctly.
3. The output is structured and validated.
4. The model receives no hidden ground-truth diagnosis.
5. A malformed/invalid model response is visibly rejected.
6. Provider unavailability is visibly distinguished from success.
7. Fallback, if used, is visibly marked.
8. Gemini cannot directly execute an intervention.
9. No production Razorpay mutation occurs.
10. The committed evidence artifact contains no secret.
11. Dashboard labels accurately describe whether the result is real Gemini or fallback.
12. Existing Phase A, B, and C evidence remains unchanged.

---

## 18. Acceptance Criteria

Phase D is complete only when all of the following are true:

- [ ] Real Gemini provider boundary implemented.
- [ ] No production credentials/data used.
- [ ] Prompt is versioned.
- [ ] Evidence representation is versioned/hashable.
- [ ] Ground-truth labels are hidden from the model.
- [ ] Structured output validation implemented.
- [ ] Model errors/unavailability are explicit.
- [ ] Fallback is explicit if present.
- [ ] Diagnosis quality metrics are calculated.
- [ ] Operational reliability metrics are calculated.
- [ ] Governance/safety checks are calculated.
- [ ] Cost/usage is recorded when reliably available.
- [ ] Phase D evidence JSON is generated.
- [ ] Evidence contains no secrets.
- [ ] Existing execution authority remains unchanged.
- [ ] Existing frozen engines remain untouched unless explicitly approved.
- [ ] Phase A evidence remains unchanged.
- [ ] Phase B evidence remains unchanged.
- [ ] Phase C presentation remains truthful.
- [ ] Focused Phase D tests pass.
- [ ] Full backend test suite passes.
- [ ] Frontend build/lint pass if frontend changes were made.
- [ ] Manual real-Gemini validation completed.
- [ ] `git diff --check` is clean.

---

## 19. Definition of Done

The phase should be described to judges as:

> **REVIVE now has a real Gemini evaluation path that is structured, measurable, reproducible, and governed. Gemini contributes diagnosis intelligence, while REVIVE's deterministic policy, execution guards, and attribution system remain authoritative.**

The strongest evidence is not merely that an API call succeeded.

The strongest evidence is that:

```text
REAL MODEL
   ↓
STRUCTURED DIAGNOSIS
   ↓
MEASURED QUALITY
   ↓
EXPLICIT FAILURE STATES
   ↓
NO EXECUTION BYPASS
   ↓
AUDITABLE EVIDENCE
```

---

## 20. Implementation Discipline

Antigravity must:

1. Read this specification completely before changing code.
2. Inspect the current repository and existing architecture.
3. Identify exactly which files must change.
4. Preserve all frozen paths unless explicit approval is obtained.
5. Prefer the smallest coherent implementation.
6. Reuse existing contracts and helpers where appropriate.
7. Avoid duplicate domain logic.
8. Never fabricate Gemini responses or evaluation metrics.
9. Run only automated tests/checks during implementation.
10. Produce a concise implementation report listing:
    - files changed;
    - architecture decisions;
    - tests run and results;
    - evidence generated;
    - any unavailable credentials/configuration;
    - any deviations from this specification.
11. Do not commit or push changes.
12. Do not modify unrelated files.
13. Do not delete existing evidence.
14. Do not alter Phase A or Phase B authoritative artifacts.
15. Stop and report if a required change conflicts with a frozen boundary.

---

## 21. Explicit Non-Goals

Phase D does **not**:

- replace deterministic risk scoring;
- replace intervention policy;
- replace execution guards;
- authorize autonomous model-driven payments;
- introduce production customer traffic;
- claim production revenue recovery from Gemini;
- modify the Razorpay integration proof;
- rewrite the Phase B benchmark;
- weaken the Phase C audit/provenance model.

Phase D is an **AI evaluation and evidence phase**, not an uncontrolled autonomous-agent phase.

---

## 22. Final Phase Boundary

At the end of Phase D, REVIVE should be able to demonstrate:

```text
A controlled customer evidence record
        ↓
A real Gemini request
        ↓
A versioned structured diagnosis
        ↓
Measured diagnosis quality
        ↓
Explicit model/fallback/error state
        ↓
Governed REVIVE decision boundary
        ↓
No unauthorized execution
        ↓
Committed reproducible evidence
```

That is the required bridge between REVIVE's deterministic recovery system and credible AI-powered revenue recovery.
