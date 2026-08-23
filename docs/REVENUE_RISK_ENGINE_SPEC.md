# REVIVE

## Revenue Risk Engine Specification

**Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery**

**Version:** 1.1  
**Phase:** 3 — Revenue Risk Engine  
**Status:** Implementation specification  
**Parent specification:** `REVIVE\\\_BUILD\\\_CONSTITUTION.md`

\---

## 1\. Purpose

The Revenue Risk Engine is the first decision-support component of REVIVE.

Its purpose is to answer:

> Which customers are currently at meaningful risk of failing to convert, and how much revenue is exposed if they do not convert?

The engine must operate only on information that would genuinely be available to REVIVE at the decision snapshot.

It must NOT use hidden synthetic ground truth as an inference feature.

The engine must produce:

1. a probability of natural conversion failure;
2. a risk score;
3. revenue at risk;
4. a risk tier;
5. a deterministic explanation of observable signals contributing to the score.

The engine must rank customers so later REVIVE components can prioritize them for diagnosis and recovery decisions.

\---

## 2\. Phase Boundary

Phase 3 implements ONLY:

```text
Observable events
        ↓
Feature construction
        ↓
Risk prediction
        ↓
Revenue-at-risk calculation
        ↓
Risk ranking
        ↓
Evaluation
```

Do NOT implement in this phase:

* root-cause diagnosis;
* recovery action selection;
* intervention execution;
* policy engine;
* Razorpay API;
* LLM;
* agent orchestration;
* treatment/control experiment;
* dashboard;
* frontend;
* database;
* production deployment.

Those belong to later phases.

\---

## 3\. Core Risk Definition

For Phase 3:

```text
risk\\\_score = P(customer does NOT naturally convert)
```

Therefore:

```text
0.00 = essentially no predicted conversion risk
1.00 = extremely high predicted conversion risk
```

The risk score is a probability estimate, not a guaranteed outcome.

\---

## 4\. Prediction Target

The supervised prediction target is:

```text
conversion\\\_failure
```

defined as:

```text
conversion\\\_failure = NOT natural\\\_conversion
```

The `natural\\\_conversion` field exists only in hidden ground truth.

It may be used for:

* training label construction;
* offline evaluation.

It MUST NOT be used as an input feature.

\---

## 5\. Strict Data Separation

The following fields are forbidden as model features:

```text
generation\\\_segment
natural\\\_conversion
conversion\\\_after\\\_intervention
recoverable
maximum\\\_recoverable\\\_revenue
true\\\_root\\\_cause
```

The model must not read `ground\\\_truth.jsonl` during inference.

Ground truth may only be loaded by the training/evaluation pipeline and must never be exposed through the runtime feature-building interface.

\---

## 6\. Observable Input

The risk engine receives observable customer journey data:

```text
data/generated/observable/customers.jsonl
data/generated/observable/plans.jsonl
data/generated/observable/events.jsonl
```

The feature builder must reconstruct customer-level features from these observable records.

It must not depend on the synthetic generation segment.

\---

## 7\. Fixed Prediction Snapshot

The model must make a prediction from a customer's observable state **before the final conversion/expiration outcome is known**.

To prevent outcome leakage and make customers comparable, Phase 3 uses a fixed decision rule:

> \\\*\\\*Prediction timestamp = trial start + 72 hours, capped at the trial end timestamp.\\\*\\\*

If the trial ends before 72 hours, use the trial end timestamp.

If a customer has already converted before the snapshot, that customer is excluded from the at-risk inference population and may be retained only for offline training/evaluation as an already-observed positive outcome.

The feature builder must include only events with timestamps at or before the prediction timestamp.

Events after the prediction timestamp must never enter the feature vector.

This fixed snapshot is mandatory for the initial Phase 3 implementation.

\---

## 8\. Snapshot Validity

For each customer, the feature builder must verify:

```text
trial\\\_started <= prediction\\\_timestamp <= trial\\\_end
```

where applicable.

If a valid prediction snapshot cannot be constructed, return:

```text
status = "INSUFFICIENT\\\_DATA"
```

rather than inventing a timestamp.

The prediction timestamp must be stored with each scored customer.

\---

## 9\. Required Features

The initial risk model must use observable features from these groups.

### Engagement

```text
session\\\_count
feature\\\_use\\\_count
product\\\_activity\\\_count
active\\\_days
```

### Recency

```text
hours\\\_since\\\_last\\\_activity
hours\\\_since\\\_last\\\_session
hours\\\_since\\\_last\\\_feature\\\_use
```

### Commercial intent

```text
pricing\\\_view\\\_count
checkout\\\_started
checkout\\\_completed
payment\\\_method\\\_added
```

### Payment behaviour

```text
payment\\\_attempt\\\_count
payment\\\_success\\\_count
payment\\\_failure\\\_count
has\\\_payment\\\_failure
```

### Trial state

```text
trial\\\_age\\\_hours
hours\\\_until\\\_trial\\\_expiry
trial\\\_expiring\\\_soon
```

### Revenue exposure

```text
plan\\\_id
plan\\\_price
```

All features must be computed using events available at or before the prediction timestamp.

\---

## 10\. Derived Features

The feature builder may additionally create:

```text
feature\\\_use\\\_per\\\_session
pricing\\\_views\\\_per\\\_session
payment\\\_failures\\\_per\\\_attempt
pricing\\\_view\\\_recency\\\_hours
checkout\\\_start\\\_recency\\\_hours
activity\\\_recency\\\_hours
```

All ratios must safely handle zero denominators.

No NaN or infinite values may reach the model.

\---

## 11\. Trial Expiry Feature

Define:

```text
trial\\\_expiring\\\_soon =
    hours\\\_until\\\_trial\\\_expiry <= 24
```

when the customer has not already expired.

This must be calculated from observable timestamps at the prediction snapshot.

\---

## 12\. Payment Features

The model may use the synthetic payment-failure categories:

```text
bank\\\_declined
insufficient\\\_funds
payment\\\_method\\\_error
temporary\\\_processing\\\_failure
```

These are synthetic categories defined by Phase 2.

They must not be interpreted as real Razorpay payment-failure statistics.

\---

## 13\. Feature Registry

Create an explicit feature registry.

Every model feature must document:

```text
name
source
type
description
allowed\\\_at\\\_inference
```

Example:

```text
session\\\_count
source: observable events
type: integer
description: number of sessions before prediction timestamp
allowed\\\_at\\\_inference: true
```

Every feature entering the model must exist in this registry.

\---

## 14\. Leakage Prevention

The following are prohibited.

### Hidden-label leakage

Never use:

```text
generation\\\_segment
natural\\\_conversion
conversion\\\_after\\\_intervention
recoverable
maximum\\\_recoverable\\\_revenue
true\\\_root\\\_cause
```

### Future-event leakage

Never use events occurring after the prediction timestamp.

### Outcome leakage

Do not use a final outcome as a predictive feature if it occurs after the prediction timestamp.

For example, a `subscription\\\_created` event occurring after the snapshot must not be used to predict conversion.

If an event occurs before the fixed snapshot, it may be used only because it was genuinely observable at that time.

\---

## 15\. Training Dataset Construction

For each customer:

1. load observable events;
2. establish the fixed prediction timestamp;
3. keep only events at or before the timestamp;
4. construct the feature vector;
5. obtain the hidden `natural\\\_conversion` label separately;
6. derive:

```text
conversion\\\_failure = NOT natural\\\_conversion
```

The target must never be included in the feature vector.

Customers who converted before the snapshot must not be used as live at-risk inference candidates.

They may remain in the offline labelled dataset where their observable pre-snapshot features are used to train/evaluate the classifier.

\---

## 16\. Data Split

Use a deterministic customer-level split:

```text
70% training
15% validation
15% test
```

The split must be performed by customer ID.

No customer may appear in more than one split.

Use a fixed random seed:

```text
42
```

The split must occur before model training and evaluation.

Do not use hidden generation segments as model features or production stratification variables.

\---

## 17\. Baseline Model

Start with an interpretable probabilistic baseline:

```text
Logistic Regression
```

Use it as the primary baseline because it provides:

* probability estimates;
* interpretable coefficients;
* reproducibility;
* fast training;
* a strong reference point.

Do not use an LLM for numerical risk prediction.

Do not introduce a complex model merely for the sake of calling the system AI.

\---

## 18\. Optional Model Comparison

If practical, compare the logistic-regression baseline against one tree-based model such as:

```text
Random Forest
```

or:

```text
Gradient Boosting
```

The comparison is optional if dependency or implementation complexity would materially distract from the core system.

The final model must be selected using validation performance, not model complexity.

\---

## 19\. Model Selection

Select the final model using validation data.

Primary selection metric:

```text
ROC-AUC
```

Secondary considerations:

```text
PR-AUC
Brier Score
Calibration
Top-K recall
```

Do not select a model solely because it has the highest accuracy.

\---

## 20\. Required Evaluation Metrics

The final test-set evaluation must report:

```text
ROC-AUC
PR-AUC
Brier Score
Precision
Recall
F1
```

Also report:

```text
confusion matrix
```

at the selected operating threshold.

Accuracy may be reported, but it must not be the primary model-selection metric.

\---

## 21\. Probability Calibration

Because `risk\\\_score` represents a probability, evaluate calibration.

Report:

```text
Brier Score
```

and a calibration curve or equivalent calibration analysis.

If calibration is poor, an appropriate calibration method may be applied using validation data only.

Do not fit calibration parameters using the test set.

\---

## 22\. Risk Score

The final model output must be:

```text
risk\\\_score
```

where:

```text
0 <= risk\\\_score <= 1
```

Higher means greater predicted probability of natural conversion failure.

\---

## 23\. Risk Tiers

Use these initial deterministic thresholds:

```text
LOW:
risk\\\_score < 0.30

MEDIUM:
0.30 <= risk\\\_score < 0.60

HIGH:
0.60 <= risk\\\_score < 0.80

CRITICAL:
risk\\\_score >= 0.80
```

These are initial operating thresholds.

They must be evaluated against the validation set.

If evidence strongly supports different thresholds, the final thresholds may be adjusted and documented.

Thresholds must not be chosen by looking at the test set.

\---

## 24\. Revenue at Risk

For Phase 3:

```text
revenue\\\_at\\\_risk =
    plan\\\_price × risk\\\_score
```

Example:

```text
plan\\\_price = ₹4,999
risk\\\_score = 0.80

revenue\\\_at\\\_risk = ₹3,999.20
```

This is expected revenue exposure.

It is NOT guaranteed recoverable revenue.

\---

## 25\. Recoverability Separation

Do NOT use:

```text
recoverable
```

to calculate the risk score.

Do NOT use:

```text
recoverable
```

as an inference feature.

Recoverability belongs to later decision and evaluation stages.

Phase 3 answers:

> How likely is the customer to fail to convert?

Later phases answer:

> Can this customer be recovered, and what should we do?

\---

## 26\. Customer Risk Output

For every eligible scored customer, produce:

```json
{
  "customer\\\_id": "cus\\\_12345",
  "prediction\\\_timestamp": "2026-08-01T12:00:00+05:30",
  "risk\\\_score": 0.82,
  "risk\\\_tier": "CRITICAL",
  "plan\\\_id": "pro",
  "plan\\\_price": "4999.00",
  "revenue\\\_at\\\_risk": "4099.18"
}
```

Do not include hidden ground-truth fields.

Customers that cannot be safely scored must return an explicit status such as:

```text
INSUFFICIENT\\\_DATA
```

rather than a fabricated risk score.

\---

## 27\. Risk Explanation

The engine must provide a deterministic explanation using observable features.

Example:

```text
High risk because:
- trial expires within 24 hours;
- recent activity is low;
- checkout has not completed;
- a previous payment attempt failed.
```

Do NOT produce explanations such as:

```text
Customer belongs to checkout\\\_abandoner segment.
```

because the segment is hidden.

The explanation must describe observable evidence available at the prediction snapshot.

\---

## 28\. Explanation Method

Do NOT use an LLM for Phase 3 explanations.

Use deterministic feature-based explanations.

Examples:

```text
hours\\\_until\\\_trial\\\_expiry <= 24
→ "trial expires within 24 hours"

payment\\\_failure\\\_count > 0
→ "previous payment failure"

checkout\\\_started == true AND checkout\\\_completed == false
→ "checkout was started but not completed"

hours\\\_since\\\_last\\\_activity > threshold
→ "recent activity is low"
```

This makes explanations:

* reproducible;
* auditable;
* cheap;
* deterministic.

An LLM may be considered later for diagnosis where it adds genuine value.

\---

## 29\. Batch Ranking

The risk engine must support scoring a batch of eligible customers.

Customers must be rankable by:

```text
revenue\\\_at\\\_risk descending
```

and:

```text
risk\\\_score descending
```

The primary business ranking should use `revenue\\\_at\\\_risk`.

\---

## 30\. Top-K Evaluation

Evaluate ranking quality using:

```text
Recall@1%
Recall@5%
Recall@10%

Precision@1%
Precision@5%
Precision@10%
```

Customers are ranked by `revenue\\\_at\\\_risk`.

Ground truth may be used only during offline evaluation.

\---

## 31\. Revenue-Weighted Ranking Evaluation

Measure how much exposed revenue is represented inside the highest-ranked customers.

Report revenue-at-risk captured in:

```text
Top 1%
Top 5%
Top 10%
```

This is a ranking diagnostic.

It must NOT be described as recovered revenue.

\---

## 32\. Simple Baselines

Compare the risk engine against simple non-ML ranking baselines.

At minimum:

### Baseline A

Rank by:

```text
plan\\\_price
```

### Baseline B

Rank by:

```text
hours\\\_until\\\_trial\\\_expiry
```

### Baseline C

Rank customers where:

```text
checkout\\\_started == true
AND
checkout\\\_completed == false
```

The risk model should demonstrate value beyond trivial rules.

\---

## 33\. No Hidden Segment Shortcut

Do not build rules such as:

```text
if segment == "checkout\\\_abandoner":
    high\\\_risk
```

The segment is hidden and unavailable.

The engine must derive risk from observable behaviour.

\---

## 34\. Feature Importance

For the final model, report feature importance.

For logistic regression:

```text
model coefficients
```

For tree models:

```text
feature importance
```

The feature importance report must be generated from the trained model.

Do not manually invent importance rankings.

\---

## 35\. Model Artifact

Save the final trained model to a local model artifact.

The artifact must include:

* model;
* feature ordering;
* preprocessing;
* model version;
* training seed;
* feature registry version.

The model artifact must be reproducible from source code and training data.

Do not commit large generated training datasets or secrets.

\---

## 36\. Reproducibility

Training must accept:

```text
--seed 42
```

The same training data, feature specification, model configuration, and seed must produce reproducible results within the deterministic guarantees of the selected libraries.

\---

## 37\. Required Scripts

Create:

```text
scripts/build\\\_risk\\\_features.py
scripts/train\\\_risk\\\_model.py
scripts/evaluate\\\_risk\\\_model.py
```

The exact CLI may be adjusted if necessary while preserving the responsibilities.

\---

## 38\. Required Code Structure

Implement approximately:

```text
app/
├── risk/
│   ├── \\\_\\\_init\\\_\\\_.py
│   ├── features.py
│   ├── feature\\\_registry.py
│   ├── model.py
│   ├── scoring.py
│   ├── ranking.py
│   ├── explanations.py
│   └── evaluation.py
│
├── simulation/
│   └── ...
│
scripts/
├── build\\\_risk\\\_features.py
├── train\\\_risk\\\_model.py
└── evaluate\\\_risk\\\_model.py

tests/
├── test\\\_dataset\\\_generator.py
├── test\\\_event\\\_models.py
└── test\\\_risk\\\_engine.py

models/
└── risk/
```

Minor structural changes are acceptable if responsibilities remain separated.

\---

## 39\. Required Tests

Add tests for:

### Feature construction

* correct session count;
* correct feature-use count;
* correct pricing-view count;
* correct checkout state;
* correct payment failure count;
* correct recency;
* correct trial remaining time;
* correct plan price.

### Leakage

Explicitly test that forbidden fields cannot enter the feature vector:

```text
generation\\\_segment
natural\\\_conversion
conversion\\\_after\\\_intervention
recoverable
maximum\\\_recoverable\\\_revenue
true\\\_root\\\_cause
```

### Temporal leakage

Verify that events after the prediction timestamp are excluded.

### Snapshot construction

Verify:

```text
prediction\\\_timestamp = trial\\\_start + 72 hours
```

when the trial is at least 72 hours long, otherwise:

```text
prediction\\\_timestamp = trial\\\_end
```

### Division safety

No NaN or infinity from ratios.

### Model output

Verify:

```text
0 <= risk\\\_score <= 1
```

### Revenue calculation

Verify:

```text
revenue\\\_at\\\_risk = plan\\\_price × risk\\\_score
```

using the project's defined Decimal/rounding policy.

### Risk tiers

Test values below, at, and above every threshold.

### Reproducibility

Same seed and same data produce equivalent feature/model results within defined deterministic guarantees.

\---

## 40\. Model Safety

The risk model must be advisory.

It must NOT directly execute any financial action.

The output is:

```text
risk estimate
```

not:

```text
permission to contact customer
```

and not:

```text
permission to charge customer
```

Later policy and decision layers must determine whether any intervention is allowed.

\---

## 41\. Failure Handling

If a customer has insufficient observable information:

Do NOT invent missing values.

Use a documented missing-value strategy.

If the feature set is fundamentally insufficient to score the customer safely, return:

```text
status = "INSUFFICIENT\\\_DATA"
```

rather than fabricating a confident risk score.

\---

## 42\. Missing Data

Missing values must be handled deterministically.

For count features:

```text
missing count = 0
```

only when absence genuinely means zero.

For categorical values, use an explicit:

```text
unknown
```

category where appropriate.

Do not silently convert unknown states into meaningful positive/negative signals.

\---

## 43\. No Intervention in Phase 3

The risk engine must never:

* send a message;
* retry a payment;
* issue a discount;
* change a subscription;
* call Razorpay;
* contact a customer.

It only produces risk information.

\---

## 44\. Evaluation Philosophy

The model is successful only if it demonstrates measurable predictive value.

A passing implementation must not rely on:

* hard-coded segment labels;
* hidden ground truth as an inference feature;
* test-set threshold tuning;
* outcome leakage;
* post-snapshot events;
* manually invented metrics.

\---

## 45\. Phase 3 Definition of Done

Phase 3 is complete only when:

1. Observable customer events can be transformed into customer-level risk features.
2. Feature construction is reproducible.
3. Hidden ground truth is never used as an inference feature.
4. Temporal leakage is prevented.
5. A baseline probabilistic model is trained.
6. Model selection uses validation data.
7. The final model produces calibrated risk probabilities or documents calibration limitations.
8. Risk tiers are deterministic.
9. Revenue-at-risk is calculated correctly.
10. Customer risk outputs are generated.
11. Batch ranking works.
12. Top-K evaluation works.
13. Revenue-weighted ranking evaluation works.
14. Baseline comparisons are available.
15. Deterministic explanations are generated.
16. Tests cover feature construction and leakage.
17. The model does not execute financial actions.
18. No Razorpay API is used.
19. No LLM is required.
20. Full tests pass.

\---

## 46\. Phase 3 Success Principle

The Revenue Risk Engine should answer:

> "Who is likely to fail to convert, based only on observable behaviour available at the prediction snapshot?"

It must NOT answer:

> "Which synthetic segment is this customer?"

and it must NOT answer:

> "Which customer can definitely be recovered?"

Those are separate problems.

The architecture remains:

```text
OBSERVE
   ↓
RISK
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

Phase 3 implements only:

```text
OBSERVE → RISK
```

\---

## 47\. Final Principle

> \\\*\\\*Risk is a prediction, not a verdict.\\\*\\\*

REVIVE must be able to say:

```text
Customer X
Risk = 0.82
Revenue at Risk = ₹4,099.18
Calibration evidence = available
Reason = observable behavioural signals
```

without claiming:

```text
"This customer will definitely churn."
```

or:

```text
"This customer can definitely be recovered."
```

The distinction between prediction, diagnosis, intervention, and measured outcome must remain explicit throughout the system.

\---

# END OF SPECIFICATION



