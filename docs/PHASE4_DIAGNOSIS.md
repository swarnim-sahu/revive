# REVIVE — Phase 4 Root-Cause Diagnosis Engine Documentation

## Core Purpose & Contract

REVIVE Phase 4 transforms Phase 3 risk predictions into evidence-grounded root-cause diagnoses using **ONLY** observable customer-journey evidence available at the prediction timestamp $T_{\text{prediction}} = 72\text{ hours}$.

### Explicit Operational Contract

> **REVIVE does not claim to know an eventual root cause before observable evidence exists.**

The Phase 4 engine answers:
> **"What currently observable evidence explains this customer's elevated revenue risk?"**

It does **NOT** answer:
> **"What event will definitely happen later in the trial?"**

Future event occurrences (such as payment failure, checkout abandonment, or subscription creation occurring between Day 5 and Day 14) are evaluated separately in offline benchmarks under **Future Outcome Alignment**.

---

## Evaluation Architecture

Offline evaluation (`app/diagnosis/evaluation.py`, `scripts/evaluate_diagnosis.py`) strictly separates evaluation into distinct questions:

### A. SNAPSHOT DIAGNOSIS QUALITY
Assesses whether the 72-hour snapshot diagnosis is defensible, evidence-grounded, and consistent with observable event streams available $\le T_{\text{prediction}}$:
- **Evidence Consistency Rate:** $100.0\%$
- **Evidence-Grounded Diagnosis Rate:** $100.0\%$
- **Coverage:** Percentage of eligible at-risk customers receiving an actionable candidate diagnosis.
- **Uncertainty Rate:** Percentage of customers cleanly assigned `INSUFFICIENT_EVIDENCE` (Safe Uncertainty) when no diagnostic evidence exists at 72h.

### B. OBSERVABILITY ANALYSIS
Classifies each customer's eventual ground-truth category at $T_{\text{prediction}}$ into:
- **`OBSERVABLE`:** Key decisive evidence items were present $\le 72\text{h}$.
- **`PARTIALLY_OBSERVABLE`:** Low engagement or partial evidence items present $\le 72\text{h}$.
- **`NOT_YET_OBSERVABLE`:** Decisive defining events occur after 72h.

### C. FUTURE OUTCOME ALIGNMENT
Measures whether an actionable candidate diagnosis at $T_{\text{prediction}} = 72\text{h}$ (`actionability == CANDIDATE`) corresponds to the eventual 14-day ground-truth outcome:
- Evaluated **ONLY** on actionable candidate diagnoses ($N=3,321$).
- `INSUFFICIENT_EVIDENCE` is treated as a safe non-actionable state and is not penalized as an alignment error.

### D. TEMPORAL SAFETY & LEAKAGE VERIFICATION
- **Future Information Leakage Rate:** $0.0\%$. Events $> T_{\text{prediction}}$ cannot alter diagnosis, confidence, actionability, or candidate scores.

### E. REFERENCE-ONLY NAIVE FUTURE-LABEL ACCURACY
- Compares a 72-hour snapshot diagnosis directly against 14-day eventual ground-truth labels.
- Retained for research reference only; **must not be interpreted as causal snapshot diagnosis accuracy**.
