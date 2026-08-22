\# REVIVE



\## Synthetic Customer Journey \& Evaluation Data Specification



\*\*Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery\*\*



\*\*Version:\*\* 1.0

\*\*Status:\*\* Implementation specification

\*\*Parent specification:\*\* `REVIVE\_BUILD\_CONSTITUTION.md`



\---



\# 1. Purpose



This document defines the synthetic business environment in which REVIVE will operate.



The purpose is to generate a realistic, reproducible, controlled dataset of subscription customer journeys that allows REVIVE to:



\* detect revenue at risk;

\* diagnose why revenue is at risk;

\* select recovery actions;

\* evaluate whether interventions are appropriate;

\* measure incremental revenue;

\* test safety behaviour;

\* evaluate failure handling.



The dataset must support both:



1\. \*\*observable information available to REVIVE\*\*, and

2\. \*\*hidden ground truth available only to the evaluation system\*\*.



REVIVE must never receive hidden ground-truth fields during inference.



\---



\# 2. Dataset Scale



The initial dataset target is:



\*\*20,000 customer journeys\*\*



The generator must support configurable dataset sizes.



Example:



```bash

python scripts/generate\_dataset.py --customers 20000 --seed 42

```



The same seed and configuration must produce a reproducible dataset.



\---



\# 3. Synthetic Merchant



REVIVE will operate on one fictional subscription SaaS merchant.



\## Merchant



\*\*Name:\*\* CodeCraft Pro



\*\*Merchant ID:\*\* `merch\_codecraft`



\*\*Currency:\*\* `INR`



\*\*Timezone:\*\* `Asia/Kolkata`



CodeCraft Pro is fictional and exists only as the controlled environment for experimentation.



No claims about actual Razorpay merchant behaviour should be inferred from this synthetic merchant.



\---



\# 4. Subscription Plans



The merchant has three monthly subscription plans.



| Plan     | ID         | Monthly Price |

| -------- | ---------- | ------------: |

| Starter  | `starter`  |          ₹999 |

| Pro      | `pro`      |        ₹4,999 |

| Business | `business` |        ₹9,999 |



All prices are synthetic.



Money must be represented using `Decimal`.



\---



\# 5. Plan Distribution



Across 20,000 generated customers:



| Plan     | Percentage | Target Customers |

| -------- | ---------: | ---------------: |

| Starter  |        50% |           10,000 |

| Pro      |        35% |            7,000 |

| Business |        15% |            3,000 |



The generator must ensure the final distribution is either exactly equal to these counts or document any intentional sampling variation.



For the initial implementation, use exact counts.



\---



\# 6. Customer Journey Segments



The generator will create eight behavioural segments.



These are \*\*generation categories\*\*, not information visible to REVIVE.



| Segment            | Percentage | Target Customers |

| ------------------ | ---------: | ---------------: |

| Healthy Converter  |        20% |            4,000 |

| Low Intent         |        20% |            4,000 |

| Checkout Abandoner |        15% |            3,000 |

| Payment Friction   |        12% |            2,400 |

| Trial Expiring     |        10% |            2,000 |

| High-Value At Risk |         8% |            1,600 |

| Ambiguous          |        10% |            2,000 |

| Already Converted  |         5% |            1,000 |

| \*\*Total\*\*          |   \*\*100%\*\* |       \*\*20,000\*\* |



The segment assignment must be stored in the hidden ground-truth dataset.



It must NOT appear in observable customer/event records.



\---



\# 7. General Journey Rules



Every customer must have:



1\. a unique customer ID;

2\. a merchant ID;

3\. a plan;

4\. a trial;

5\. a trial start timestamp;

6\. a trial end timestamp;

7\. at least one customer lifecycle event;

8\. a hidden ground-truth record.



Events must occur in logically valid chronological order.



Impossible journeys must not be generated.



For example:



\* subscription creation cannot occur before customer creation;

\* payment cannot reference an unknown customer;

\* checkout completion cannot occur before checkout starts;

\* trial expiration cannot occur before trial starts.



\---



\# 8. Trial Configuration



Initial trial duration:



\*\*14 days\*\*



The generator may introduce small timing variation around user activity, but the baseline trial duration remains 14 days.



Every customer begins with:



```text

trial\_started

```



A customer who reaches the end of the trial without conversion must receive:



```text

trial\_expiring

trial\_expired

```



where appropriate.



\---



\# 9. Segment A — Healthy Converter



\## Purpose



Represents users who genuinely find value in the product and are likely to convert naturally.



\## Observable behaviour



Sessions:



\*\*8–25\*\*



Feature uses:



\*\*10–50\*\*



Pricing views:



\*\*1–5\*\*



Checkout:



Usually initiated.



Payment method:



Usually added before conversion.



Checkout abandonment:



Possible but relatively uncommon.



\## Ground truth



These customers have a high probability of converting without REVIVE intervention.



Target natural conversion probability:



\*\*0.85–0.95\*\*



For initial implementation, use a deterministic distribution within this range based on the seeded random generator.



\## Important property



A healthy converter should often demonstrate that:



> \*\*A successful payment after an intervention does not automatically mean the intervention caused incremental revenue.\*\*



These customers are important for preventing false recovery claims.



\---



\# 10. Segment B — Low Intent



\## Purpose



Represents users who are unlikely to become paying customers.



\## Observable behaviour



Sessions:



\*\*0–4\*\*



Feature uses:



\*\*0–5\*\*



Pricing views:



\*\*0–1\*\*



Checkout:



Usually not started.



Payment method:



Usually absent.



Product engagement:



Low.



\## Ground truth



Natural conversion probability:



\*\*0.02–0.10\*\*



Interventions should generally have low incremental value.



\## Expected REVIVE behaviour



Usually:



\*\*NO INTERVENTION\*\*



This segment tests whether REVIVE avoids wasting interventions on low-value opportunities.



\---



\# 11. Segment C — Checkout Abandoner



\## Purpose



Represents high-intent users who reached the checkout funnel but failed to complete it.



\## Observable behaviour



Sessions:



\*\*8–30\*\*



Feature uses:



\*\*15–60\*\*



Pricing views:



\*\*2–6\*\*



Checkout started:



\*\*Yes\*\*



Payment method added:



Frequently yes.



Checkout abandoned:



\*\*Yes\*\*



Trial status:



Usually active or approaching expiration.



\## Ground truth



Split this segment into three hidden subgroups.



\### C1 — Naturally convertible



Would convert without intervention.



Target:



\*\*25%\*\*



\### C2 — Recoverable



Would not convert naturally but would convert after an appropriate checkout recovery intervention.



Target:



\*\*50%\*\*



\### C3 — Not recoverable



Would not convert even after appropriate intervention.



Target:



\*\*25%\*\*



These proportions are hidden from REVIVE.



\---



\# 12. Segment D — Payment Friction



\## Purpose



Represents high-intent users whose conversion is blocked by payment friction.



\## Observable behaviour



Sessions:



\*\*8–30\*\*



Feature uses:



\*\*15–60\*\*



Pricing views:



\*\*2–6\*\*



Checkout started:



\*\*Yes\*\*



Payment attempted:



\*\*Yes\*\*



Payment failed:



\*\*Yes\*\*



\## Synthetic payment failure reasons



Use:



```text

bank\_declined

insufficient\_funds

payment\_method\_error

temporary\_processing\_failure

```



These are synthetic categories for experimentation.



Do not claim that these probabilities represent real Razorpay failure distributions.



\## Hidden subgroups



\### D1 — Recoverable payment friction



\*\*50%\*\*



\### D2 — Naturally convertible



\*\*20%\*\*



\### D3 — Not recoverable



\*\*30%\*\*



REVIVE must infer payment friction from observable evidence rather than receiving the hidden subgroup.



\---



\# 13. Segment E — Trial Expiring



\## Purpose



Represents engaged users who are approaching trial expiration without converting.



\## Observable behaviour



Sessions:



\*\*6–25\*\*



Feature uses:



\*\*10–50\*\*



Pricing views:



\*\*1–5\*\*



Trial remaining at detection:



\*\*1–24 hours\*\*



Checkout:



May or may not have started.



\## Ground truth



Create variation:



\* some would naturally convert;

\* some are recoverable through a timely reminder;

\* some remain unlikely to convert.



The hidden evaluator must distinguish these cases.



\---



\# 14. Segment F — High-Value At Risk



\## Purpose



Tests whether REVIVE properly prioritizes high-value revenue without automatically using aggressive interventions.



Most customers in this segment should be assigned the:



\*\*Business — ₹9,999/month\*\*



plan.



\## Observable behaviour



Sessions:



\*\*10–30\*\*



Feature uses:



\*\*20–70\*\*



Pricing views:



\*\*2–6\*\*



Trial remaining:



\*\*1–48 hours\*\*



Checkout:



May be started or abandoned.



Payment:



May contain friction.



\## Ground truth



This segment should contain a mixture of:



\* naturally convertible;

\* recoverable;

\* non-recoverable customers.



The higher subscription value should affect revenue exposure and prioritization, but should NOT automatically force an intervention.



\---



\# 15. Segment G — Ambiguous



\## Purpose



Represents conflicting evidence.



These users are deliberately difficult to classify.



Examples:



\* high sessions but low feature usage;

\* pricing views but no checkout;

\* high product usage but little recent activity;

\* checkout started long ago but no recent activity;

\* trial nearly expired with mixed signals.



\## Ground truth



Use mixed outcomes.



No single simple rule should perfectly classify this segment.



\## Expected REVIVE behaviour



Low-confidence cases should generally result in:



\* no automated action; or

\* human escalation.



This segment is important for testing whether REVIVE understands uncertainty.



\---



\# 16. Segment H — Already Converted



\## Purpose



Safety and negative-control population.



These customers have already converted.



They must have:



```text

subscription\_created

```



and a valid subscription.



\## Expected REVIVE behaviour



\*\*NO RECOVERY INTERVENTION\*\*



Once a customer has converted, the recovery opportunity should terminate.



This is a mandatory safety condition.



\---



\# 17. Behaviour Generation



Behaviour must not be deterministic based purely on segment.



Do NOT generate:



```text

if sessions > 15:

&#x20;   checkout\_abandoner

```



Instead:



\* generate segment first;

\* sample behaviour from that segment's distributions;

\* allow overlap between segments.



The goal is to prevent REVIVE from succeeding through trivial hard-coded rules.



\---



\# 18. Observable Features



The generated observable data should allow future phases to derive features such as:



\### Engagement



\* session count;

\* feature-use count;

\* recent activity;

\* activity frequency.



\### Commercial intent



\* pricing views;

\* checkout starts;

\* checkout completion;

\* payment-method addition.



\### Payment health



\* payment attempts;

\* payment successes;

\* payment failures;

\* failure reasons;

\* previous payment history.



\### Trial state



\* trial age;

\* hours remaining;

\* trial expiration.



\### Revenue exposure



\* subscription plan;

\* subscription price.



\---



\# 19. Hidden Ground Truth



For every customer, generate a separate hidden ground-truth record.



Minimum fields:



```text

customer\_id

generation\_segment

natural\_conversion

conversion\_after\_intervention

recoverable

maximum\_recoverable\_revenue

true\_root\_cause

```



\## Definitions



\### natural\_conversion



Whether the customer would convert without REVIVE.



\### conversion\_after\_intervention



Whether the customer would convert after the appropriate successful intervention.



\### recoverable



Whether an appropriate intervention can produce an incremental conversion.



\### maximum\_recoverable\_revenue



The subscription revenue attributable to a successful recoverable conversion.



\### true\_root\_cause



The underlying cause used to construct the scenario.



Possible values:



```text

none

low\_intent

checkout\_abandonment

payment\_friction

trial\_expiration

mixed\_signals

already\_converted

```



\---



\# 20. Ground Truth Must Remain Hidden



The following fields must NEVER be included in observable event payloads:



```text

generation\_segment

natural\_conversion

conversion\_after\_intervention

recoverable

maximum\_recoverable\_revenue

true\_root\_cause

```



They belong exclusively to the evaluation dataset.



REVIVE must make decisions without accessing them.



\---



\# 21. Event Generation



Generate observable events using the Phase 1 `BaseEvent` model.



Initial event types include:



```text

customer\_created

trial\_started

trial\_expiring

trial\_expired



session\_started

feature\_used

pricing\_viewed

product\_activity



checkout\_started

checkout\_abandoned

checkout\_completed



payment\_method\_added

payment\_attempted

payment\_succeeded

payment\_failed



subscription\_created

subscription\_cancelled

subscription\_renewed

```



Recovery events should not be generated by the initial customer-journey generator unless explicitly representing pre-existing intervention history.



Recovery actions will primarily be generated by later REVIVE execution phases.



\---



\# 22. Event Ordering



Every journey must follow valid chronology.



Minimum ordering:



```text

customer\_created

&#x20;       ↓

trial\_started

&#x20;       ↓

behaviour events

&#x20;       ↓

checkout/payment events

&#x20;       ↓

subscription or trial expiration outcome

```



Possible successful path:



```text

customer\_created

→ trial\_started

→ session\_started

→ feature\_used

→ pricing\_viewed

→ checkout\_started

→ payment\_method\_added

→ payment\_attempted

→ payment\_succeeded

→ checkout\_completed

→ subscription\_created

```



Possible abandonment path:



```text

customer\_created

→ trial\_started

→ session\_started

→ feature\_used

→ pricing\_viewed

→ checkout\_started

→ checkout\_abandoned

→ trial\_expiring

→ trial\_expired

```



Possible payment-friction path:



```text

customer\_created

→ trial\_started

→ session\_started

→ pricing\_viewed

→ checkout\_started

→ payment\_method\_added

→ payment\_attempted

→ payment\_failed

```



\---



\# 23. Payment Rules



Payments must be logically consistent.



A successful payment must have:



\* a valid customer;

\* a valid amount;

\* a payment attempt before success.



A failed payment must have:



\* a payment attempt;

\* a failure reason.



A successful subscription conversion should have an appropriate successful payment path.



Do not generate impossible states such as:



```text

payment\_succeeded

```



without a preceding payment attempt.



\---



\# 24. Subscription Rules



A subscription may only be created after a valid conversion path.



For a monthly plan:



```text

subscription.amount = plan.price

```



Subscription creation represents a successful conversion.



The generator should not create duplicate active subscriptions for the same synthetic journey unless the scenario explicitly requires it.



\---



\# 25. Intervention Opportunity



The generator should identify whether the customer is theoretically eligible for a recovery opportunity.



This is different from saying REVIVE will intervene.



The hidden ground truth may say:



```text

recoverable = true

```



while REVIVE may still choose:



```text

NO\_INTERVENTION

```



if its risk estimate or diagnosis is incorrect.



This distinction is essential for later evaluation.



\---



\# 26. Revenue Truth



For every customer, the evaluator must be able to determine:



\### Baseline outcome



What would happen without REVIVE?



\### Intervention outcome



What would happen if the appropriate intervention succeeds?



\### Incremental outcome



The difference attributable to intervention.



Do not calculate:



```text

successful\_payment = recovered\_revenue

```



without considering the counterfactual baseline.



\---



\# 27. Data Separation



The generated data must be separated into:



```text

data/

├── generated/

│   ├── observable/

│   │   ├── customers.jsonl

│   │   ├── plans.jsonl

│   │   └── events.jsonl

│   │

│   └── ground\_truth/

│       └── ground\_truth.jsonl

```



The observable dataset is the only dataset future REVIVE inference code should consume.



The ground-truth dataset is reserved for evaluation.



\---



\# 28. Reproducibility



The generator must accept:



```text

\--customers

\--seed

```



Example:



```bash

python scripts/generate\_dataset.py --customers 20000 --seed 42

```



The generator must use a controlled seeded random-number generator.



Running the same command twice should produce equivalent datasets.



\---



\# 29. Dataset Validation



After generation, validate:



\### Identity



\* exactly the requested number of customers;

\* unique customer IDs;

\* unique event IDs.



\### Referential integrity



\* every event references an existing customer;

\* every plan reference is valid;

\* every subscription references an existing customer;

\* every payment references an existing customer.



\### Chronology



\* timestamps are timezone-aware;

\* timestamps are logically ordered;

\* impossible lifecycle transitions are rejected.



\### Money



\* no negative prices;

\* no negative payment amounts;

\* no negative subscription amounts.



\### Ground truth



\* every customer has exactly one ground-truth record;

\* ground-truth IDs match observable customer IDs;

\* hidden fields are absent from observable data.



\### Segment distribution



The generated segment counts must match the configured target counts.



\---



\# 30. Dataset Statistics



After generation, print calculated statistics.



At minimum:



```text

Customers

Events

Trials

Subscriptions

Payments

Successful payments

Failed payments

Checkout starts

Checkout abandonments

Natural conversions

Recoverable customers

```



Also print segment counts.



Do NOT hardcode statistics.



All values must be calculated from the generated dataset.



\---



\# 31. Testing Requirements



The Phase 2 implementation must include tests for:



\### Generation



\* requested number of customers is generated;

\* customer IDs are unique;

\* event IDs are unique.



\### Reproducibility



\* same seed produces equivalent results.



\### Distribution



\* segment counts match target configuration.



\### Validity



\* no invalid references;

\* no negative monetary values;

\* valid timestamps;

\* valid event ordering.



\### Ground truth



\* every customer has hidden ground truth;

\* hidden fields are not present in observable records.



\### Segment behaviour



At least one representative validation test should exist for each segment.



The tests should verify broad behavioural properties rather than asserting exact random values.



\---



\# 32. No AI in Phase 2



The synthetic data generator must not use:



\* LLMs;

\* embeddings;

\* external AI APIs;

\* machine-learning models.



The generator must be deterministic, explainable, and reproducible.



\---



\# 33. No Razorpay API in Phase 2



Do not call Razorpay APIs during dataset generation.



Razorpay integration belongs to the later execution phase.



The synthetic environment should be completely runnable offline.



\---



\# 34. No Database in Phase 2



Use generated JSONL files for this phase.



Do not introduce:



\* PostgreSQL;

\* MongoDB;

\* Redis;

\* SQLAlchemy.



Persistence architecture will be decided later.



\---



\# 35. Required Implementation Structure



Antigravity should implement approximately:



```text

app/

├── models/

│   ├── enums.py

│   ├── events.py

│   └── entities.py

│

└── simulation/

&#x20;   ├── \_\_init\_\_.py

&#x20;   ├── config.py

&#x20;   ├── segments.py

&#x20;   ├── behaviour.py

&#x20;   ├── journey.py

&#x20;   ├── ground\_truth.py

&#x20;   └── generator.py



scripts/

└── generate\_dataset.py



tests/

├── test\_event\_models.py

└── test\_dataset\_generator.py



data/

├── generated/

│   ├── observable/

│   └── ground\_truth/

└── schemas/

```



The exact module decomposition may be adjusted if necessary, but the responsibilities must remain separated.



\---



\# 36. Phase 2 Definition of Done



Phase 2 is complete only when:



1\. A configurable synthetic merchant exists.

2\. Three plans exist.

3\. 20,000 customers can be generated.

4\. Eight behavioural segments exist.

5\. Behaviour varies within segments.

6\. Valid event streams are generated.

7\. Ground truth is generated separately.

8\. REVIVE cannot access hidden ground truth through observable data.

9\. Dataset generation is reproducible.

10\. Dataset validation runs automatically.

11\. Tests pass.

12\. Dataset statistics are calculated.

13\. The generator runs without AI.

14\. The generator runs without Razorpay APIs.

15\. The generator runs without a database.



\---



\# 37. Phase 2 Success Principle



The synthetic world must be difficult enough that a trivial rule cannot solve REVIVE.



A system should not be able to succeed simply by saying:



```text

if checkout\_abandoned:

&#x20;   recover

```



because:



\* some checkout abandoners convert naturally;

\* some are recoverable;

\* some are not recoverable;

\* some have conflicting signals;

\* some have payment friction;

\* some should receive no intervention.



The future risk, diagnosis, and decision systems must therefore solve a genuine inference problem.



\---



\# 38. Final Phase 2 Principle



> \*\*The generator creates the world. REVIVE observes the world. The evaluator knows the truth.\*\*



The three must remain separate.



```text

&#x20;               SYNTHETIC WORLD

&#x20;                     │

&#x20;            ┌────────┴────────┐

&#x20;            ↓                 ↓

&#x20;      OBSERVABLE DATA     HIDDEN TRUTH

&#x20;            │                 │

&#x20;            ↓                 ↓

&#x20;         REVIVE            EVALUATOR

&#x20;            │                 │

&#x20;            └────────┬────────┘

&#x20;                     ↓

&#x20;               MEASURE RESULT

```



The purpose of Phase 2 is not to make REVIVE look successful.



The purpose is to create a controlled environment in which we can honestly determine whether REVIVE actually works.



\---



\# END OF SPECIFICATION



