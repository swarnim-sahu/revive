\# REVIVE



\## AI Trial-to-Paid Revenue Recovery Agent



\*\*Razorpay AI Buildathon 2026 — Track 03: AI Revenue Recovery\*\*



\*\*Version:\*\* 1.0

\*\*Status:\*\* Build-locked foundation

\*\*Primary objective:\*\* Build a working, measurable, bounded AI revenue-recovery system that demonstrates real engineering judgment.



\---



\# 1. Problem



Merchants do not lose subscription revenue only when a payment fails.



Revenue can disappear earlier in the customer journey:



\* a high-intent trial user abandons checkout;

\* a payment method develops friction;

\* a trial approaches expiration while the user is still highly engaged;

\* a customer stops engaging after demonstrating strong buying intent;

\* repeated recovery attempts are made without understanding the underlying cause.



Traditional analytics can identify users who are likely to churn, but identifying risk alone does not recover revenue.



\### The problem Revive solves



> \*\*How can a merchant identify future subscription revenue that is genuinely recoverable, understand why it is at risk, choose the smallest effective intervention, execute that intervention safely, and prove the incremental revenue recovered?\*\*



\---



\# 2. Product Definition



\## Revive



Revive is a bounded AI revenue-recovery agent for subscription merchants.



It:



1\. detects trial users whose future revenue is at risk;

2\. estimates how much revenue is realistically recoverable;

3\. gathers evidence explaining the risk;

4\. diagnoses the likely cause;

5\. evaluates possible recovery actions;

6\. selects the minimum effective intervention;

7\. passes the decision through deterministic policy controls;

8\. executes an approved test-mode recovery workflow;

9\. handles failures safely;

10\. measures incremental revenue recovered against a control group;

11\. records a complete audit trail.



\### Core promise



> \*\*Revive does not merely predict lost revenue. It closes the loop from revenue risk to bounded recovery and measurement.\*\*



\---



\# 3. Target User



\### Primary user



A subscription merchant using Razorpay payment infrastructure.



\### Merchant problem



The merchant wants to increase legitimate subscription revenue without:



\* unnecessarily discounting customers;

\* repeatedly contacting customers;

\* blindly retrying failed actions;

\* increasing operational workload;

\* allowing an AI model to perform uncontrolled financial actions.



\### Revive's job



Revive acts as an AI recovery operator for the merchant, not as an unrestricted autonomous financial agent.



\---



\# 4. Core Loop



The entire product is built around:



\# DETECT → DIAGNOSE → DECIDE → GUARD → RECOVER → MEASURE



\### DETECT



Identify customers whose future subscription revenue is at risk.



\### DIAGNOSE



Determine why the revenue is at risk using behavioural, checkout, payment, and subscription evidence.



\### DECIDE



Select the intervention with the highest expected incremental value subject to merchant constraints.



\### GUARD



Validate the recommendation against deterministic policy, limits, consent, retry, and stopping rules.



\### RECOVER



Execute the approved action through Razorpay test-mode workflows or controlled simulation where an appropriate test-mode action is unavailable.



\### MEASURE



Determine whether the intervention actually produced incremental revenue and compare it against a control group.



\---



\# 5. Revenue Model



Revive distinguishes between three different concepts.



\## Revenue at Risk



The expected future subscription revenue that may be lost if a customer does not convert.



A simplified formulation:



`Revenue at Risk = Subscription Value × Probability of Non-Conversion`



\---



\## Recoverable Revenue



The portion of revenue at risk that Revive estimates can realistically influence through an allowed intervention.



This prevents the system from treating every potentially lost rupee as recoverable.



\---



\## Incremental Revenue Recovered



The additional revenue attributable to Revive relative to what would have happened without the intervention.



This is the primary business metric.



\### Critical principle



> \*\*Predicted revenue is not recovered revenue.\*\*



Revive may predict ₹10 lakh at risk, but it cannot claim ₹10 lakh recovered unless the evaluation demonstrates that outcome.



\---



\# 6. Primary Success Metric



\## Incremental Revenue Recovered



Revive will use a treatment/control evaluation.



Example:



\* Control group: receives normal merchant experience.

\* Treatment group: eligible customers receive Revive interventions.

\* Conversion and revenue outcomes are compared.



The system will estimate:



`Incremental Revenue = Treatment Revenue - Expected Treatment Revenue Without Intervention`



The exact statistical methodology will be documented with the implementation.



\### Secondary metrics



\#### Business



\* Revenue at Risk

\* Recoverable Revenue

\* Gross Revenue Recovered

\* Incremental Revenue Recovered

\* Net Revenue Recovered

\* Recovery Rate

\* Intervention Cost

\* Revenue Recovered per Intervention



\#### Model



\* Risk precision

\* Risk recall

\* Calibration

\* Diagnosis accuracy

\* Action-selection accuracy



\#### Agent



\* Correct intervention rate

\* No-action correctness

\* Policy violation rate

\* Failed-action recovery rate

\* Duplicate-intervention rate



\#### Safety



\* Unbounded action rate

\* Unauthorized action rate

\* Excessive retry rate

\* Audit coverage

\* Escalation correctness



\---



\# 7. Hero Scenario



The primary demo scenario will be a high-intent trial user approaching conversion.



\### Customer



`CUS\_10482`



\### Plan



Pro — ₹4,999/month



\### Trial remaining



8 hours



\### Evidence



\* 19 product sessions

\* 7 projects created

\* pricing page viewed 4 times

\* checkout initiated

\* payment method added

\* checkout abandoned



Revive detects:



\### Revenue Risk



\*\*HIGH\*\*



\### Revenue at Risk



\*\*₹4,999\*\*



\### Diagnosis



\*\*High-intent checkout abandonment\*\*



The system evaluates possible interventions:



| Action          |                     Expected Recovery | Cost | Decision |

| --------------- | ------------------------------------: | ---: | -------- |

| No action       |                                   Low |   ₹0 | No       |

| Trial reminder  |                              Moderate |  Low | No       |

| Resume checkout |                                  High |  Low | \*\*Yes\*\*  |

| Discount        | Higher gross recovery but margin cost | High | No       |



The agent recommends:



> \*\*Resume checkout\*\*



because it is expected to recover meaningful revenue without unnecessarily giving away merchant margin.



The recommendation passes through the policy engine.



If approved, the recovery action executes.



The final result is recorded as either:



\* successful recovery;

\* unsuccessful recovery;

\* fallback action;

\* human escalation.



\---



\# 8. Intervention Catalogue



Revive will initially support a small, bounded set of actions.



\## A0 — No Intervention



Used when intervention is unnecessary, unsafe, uneconomical, or unsupported by evidence.



This is a valid AI decision.



\---



\## A1 — Trial Reminder



A contextual reminder based on trial status and customer activity.



\---



\## A2 — Resume Checkout



Provide or initiate a bounded checkout-recovery workflow for users who demonstrated strong checkout intent.



\---



\## A3 — Payment Recovery Prompt



Guide the customer toward an allowed alternative payment path when payment friction is the diagnosed cause.



\---



\## A4 — Value Reminder



Communicate the product value or features the customer actually used.



\---



\## A5 — Bounded Incentive



A controlled incentive available only when merchant policy allows it.



The AI cannot invent:



\* discount percentages;

\* eligibility rules;

\* expiry rules;

\* monetary limits.



Those come from deterministic merchant configuration.



\---



\## A6 — Human Escalation



Used when:



\* confidence is low;

\* customer value is unusually high;

\* automated recovery repeatedly fails;

\* policy prevents automated intervention;

\* the case requires human judgment.



\---



\# 9. Minimum Effective Intervention Principle



Revive will not optimize for the most aggressive intervention.



It will optimize for:



> \*\*Maximum expected incremental revenue subject to cost, policy, customer, and safety constraints.\*\*



Example:



A ₹4,999 subscription might technically have a higher expected conversion rate with a large discount.



Revive should still choose a low-cost checkout recovery if that action provides sufficient expected incremental revenue.



\### Product philosophy



> \*\*Recover revenue without unnecessarily sacrificing margin or customer trust.\*\*



\---



\# 10. AI Responsibilities



AI/ML may be used for:



\* revenue-risk estimation;

\* conversion-risk estimation;

\* evidence synthesis;

\* root-cause diagnosis;

\* intervention ranking;

\* expected recovery estimation;

\* contextual explanation;

\* constrained message generation.



The AI should answer questions such as:



> "Why is this customer's revenue at risk?"



> "What evidence supports that diagnosis?"



> "Which intervention is expected to be most effective?"



> "Why is no intervention preferable?"



\---



\# 11. Non-AI Responsibilities



Deterministic software must handle:



\* policy enforcement;

\* monetary limits;

\* eligibility;

\* consent;

\* retry limits;

\* stopping rules;

\* action authorization;

\* API execution;

\* idempotency;

\* state transitions;

\* audit logging;

\* experiment assignment;

\* revenue calculation;

\* success/failure classification.



\### Critical architecture principle



> \*\*The LLM recommends. The policy engine authorizes. The payment infrastructure executes.\*\*



The LLM must never have unrestricted direct authority over financial actions.



\---



\# 12. AI Boundary



The system follows:



```text

Customer / Merchant Data

&#x20;       ↓

Risk Model

&#x20;       ↓

Evidence Collection

&#x20;       ↓

AI Diagnosis

&#x20;       ↓

AI Action Recommendation

&#x20;       ↓

Deterministic Policy Engine

&#x20;       ↓

Approved?

&#x20;  ↙          ↘

&#x20;NO            YES

&#x20;↓              ↓

Escalate       Execute

&#x20;                ↓

&#x20;         Razorpay Test Mode

&#x20;                ↓

&#x20;         Result Verification

&#x20;                ↓

&#x20;            Audit Log

```



An AI-generated statement such as:



> "Payment succeeded"



must never be treated as truth without verification from the underlying payment system.



\---



\# 13. Guardrails



Revive must refuse or stop an intervention when:



\* the customer has already converted;

\* the customer has opted out;

\* risk is below the configured threshold;

\* expected incremental revenue is below intervention cost;

\* the action is outside merchant policy;

\* the action exceeds monetary limits;

\* the maximum intervention count is reached;

\* confidence is insufficient;

\* required evidence is unavailable;

\* the underlying API reports failure;

\* the customer enters a terminal state;

\* human review is required.



\---



\# 14. Stopping Rules



Every intervention workflow must have explicit termination conditions.



\### Stop immediately when:



\* conversion occurs;

\* payment succeeds;

\* customer opts out;

\* the revenue opportunity expires;

\* the configured intervention limit is reached.



\### Stop retries when:



\* the retry budget is exhausted;

\* the failure indicates retrying is inappropriate;

\* repeated failures suggest a different root cause;

\* policy prohibits another attempt.



\### Never:



\* retry indefinitely;

\* repeatedly message the same customer;

\* stack multiple incentives;

\* override merchant policy;

\* interpret an API timeout as a successful payment.



\---



\# 15. Failure Handling



Failure is a first-class product requirement.



The demo must intentionally demonstrate at least one failure.



Example:



```text

Recovery Action

&#x20;     ↓

Razorpay Test API

&#x20;     ↓

ACTION FAILED

&#x20;     ↓

Failure classified

&#x20;     ↓

Retry policy checked

&#x20;     ↓

Retry permitted?

&#x20;  ↙           ↘

&#x20;YES            NO

&#x20;↓              ↓

Retry          Fallback

&#x20;                ↓

&#x20;            Escalation

```



The system must show:



\* what failed;

\* why it failed;

\* whether a retry was permitted;

\* what fallback was selected;

\* whether the revenue remains at risk;

\* whether human escalation occurred;

\* complete audit history.



\### Critical rule



> \*\*Never fabricate success.\*\*



\---



\# 16. Audit Trail



Every financial/recovery decision must create an auditable record.



Each event should contain:



\* audit ID;

\* customer ID;

\* merchant ID;

\* revenue at risk;

\* risk score;

\* diagnosis;

\* supporting evidence;

\* recommended action;

\* expected incremental revenue;

\* policy decision;

\* policy reason;

\* executed action;

\* API/result status;

\* recovered revenue;

\* timestamp;

\* model/version information.



Example:



```text

AUDIT #18429



Customer:

CUS\_92831



Revenue at Risk:

₹4,999



Risk:

0.91



Diagnosis:

Checkout abandonment



Evidence:

• 21 sessions

• 6 projects created

• Pricing viewed 5×

• Checkout initiated



Recommendation:

Resume checkout



Expected Incremental Revenue:

₹2,140



Policy:

APPROVED



Execution:

Checkout recovery link generated



Result:

SUCCESS



Recovered Revenue:

₹4,999

```



\---



\# 17. Evaluation Dataset



Revive will operate on a sufficiently large synthetic dataset rather than a handful of manually selected examples.



\### Initial target



\*\*20,000 customer journeys\*\*



Each journey may contain:



\### Customer



\* customer ID

\* plan

\* acquisition source

\* historical value



\### Trial



\* start time

\* end time

\* remaining duration



\### Behaviour



\* sessions

\* feature usage

\* product activity

\* pricing views

\* checkout starts

\* checkout abandonment



\### Payment



\* attempts

\* success/failure

\* failure reason

\* payment method

\* previous payment history



\### Subscription



\* conversion status

\* subscription value

\* cancellation

\* renewal



\### Intervention



\* action

\* timestamp

\* outcome

\* intervention count



\### Ground truth



\* actual conversion

\* actual revenue

\* whether the intervention could have influenced the outcome



\---



\# 18. Scenario Matrix



The dataset must contain multiple classes of situations.



| Scenario                         | Expected System Behaviour |

| -------------------------------- | ------------------------- |

| Healthy trial                    | Do nothing                |

| Low-intent user                  | Do nothing                |

| High-intent checkout abandonment | Resume checkout           |

| Payment friction                 | Payment recovery          |

| Trial ending soon                | Contextual reminder       |

| High-value customer              | Higher-priority recovery  |

| Merchant forbids discounts       | No discount               |

| Already converted                | Stop                      |

| Repeated failed action           | Escalate                  |

| API failure                      | Graceful fallback         |

| Low-confidence diagnosis         | Human review              |

| Expired opportunity              | Stop                      |



The system must be tested against these scenarios automatically.



\---



\# 19. Control Group



The evaluation must include a control group.



\### Treatment



Eligible users receive Revive interventions according to policy.



\### Control



Comparable users receive the normal baseline experience.



\### Objective



Determine whether Revive produces \*\*incremental revenue\*\*, not merely correlation.



The experiment methodology, assignment process, assumptions, and limitations will be documented in the repository.



\---



\# 20. Success Criteria



The project is not considered complete merely because the UI works.



Revive is considered successful only when it demonstrates:



\### Product



\* end-to-end revenue recovery workflow;

\* multiple risk scenarios;

\* explainable decisions;

\* bounded interventions.



\### AI



\* meaningful AI reasoning;

\* measurable risk/diagnosis performance;

\* AI used only where it adds value.



\### Engineering



\* working APIs;

\* deterministic state transitions;

\* reliable execution;

\* tests;

\* failure handling;

\* idempotency where applicable.



\### Safety



\* policy enforcement;

\* stopping rules;

\* retry limits;

\* no unrestricted monetary actions;

\* complete audit trail.



\### Business



\* batch evaluation;

\* treatment/control comparison;

\* measured incremental revenue;

\* intervention cost;

\* net recovery.



\---



\# 21. Razorpay Demo Requirements



The final five-minute demonstration must show:



\## 1. Problem



A merchant has revenue at risk.



\## 2. Detection



Revive identifies the customer.



\## 3. Diagnosis



The system explains why the customer is at risk.



\## 4. Decision



The agent compares possible interventions.



\## 5. Guardrail



The policy engine approves or rejects the action.



\## 6. Execution



The recovery workflow executes.



\## 7. Recovery



Revenue is successfully recovered in the test environment.



\## 8. Measurement



Batch results demonstrate incremental revenue.



\## 9. Failure



One recovery action intentionally fails.



\## 10. Recovery from failure



The system stops/retries/falls back/escalates correctly.



\## 11. Audit



The complete decision trail is visible.



\---



\# 22. What We Will NOT Build



To protect scope, Revive will initially exclude:



\* generic conversational chatbot;

\* unrestricted autonomous agent;

\* arbitrary payment manipulation;

\* large CRM system;

\* complex merchant marketing platform;

\* dozens of intervention types;

\* unnecessary microservices;

\* excessive frontend animation;

\* fake production claims;

\* fabricated business metrics;

\* unnecessary RAG infrastructure;

\* features that cannot be demonstrated in the five-minute pitch.



\### Rule



> \*\*If a feature does not improve revenue recovery, measurement, safety, AI judgment, or demonstrable engineering quality, it is probably out of scope.\*\*



\---



\# 23. Technical Philosophy



Revive should be designed as a small production-like system rather than a hackathon prototype held together by prompts.



\### Prefer



\* deterministic workflows;

\* typed schemas;

\* explicit state machines;

\* testable components;

\* reproducible experiments;

\* observable decisions;

\* small interfaces;

\* clear failure modes.



\### Avoid



\* "magic" agent behaviour;

\* hidden state;

\* unexplained LLM decisions;

\* hardcoded demo-only outcomes;

\* claims unsupported by evaluation.



\---



\# 24. Definition of Done



Revive is ready for Razorpay submission only when a fresh evaluator can:



1\. clone the public repository;

2\. follow the setup instructions;

3\. generate/load the evaluation dataset;

4\. run the application;

5\. inspect a customer at risk;

6\. understand why revenue is at risk;

7\. observe an intervention decision;

8\. see the policy gate;

9\. execute a test-mode recovery;

10\. inspect the audit trail;

11\. reproduce the failure scenario;

12\. observe graceful failure handling;

13\. run the batch evaluation;

14\. see treatment/control results;

15\. understand how incremental revenue was calculated.



\---



\# 25. Final Product Statement



> \*\*Revive is a bounded AI revenue-recovery agent that identifies high-intent trial users whose future subscription revenue is at risk, diagnoses the cause using behavioural and payment evidence, selects the minimum effective intervention, executes it through controlled Razorpay test-mode workflows, and proves incremental revenue recovered against a control group.\*\*



\---



\# 26. North Star



Every major engineering decision must answer:



> \*\*Does this help Revive recover legitimate merchant revenue, prove that it recovered it, or make that recovery safer and more trustworthy?\*\*



If the answer is no, we do not build it merely because it is technically interesting.



\---



\# 27. Build Order After Constitution



With this constitution frozen, implementation proceeds in this order:



\*\*Phase 1 — Event \& Data Model\*\*



↓



\*\*Phase 2 — Synthetic Journey Generator\*\*



↓



\*\*Phase 3 — Revenue Risk Engine\*\*



↓



\*\*Phase 4 — Root-Cause Diagnosis\*\*



↓



\*\*Phase 5 — Recovery Decision Engine\*\*



↓



\*\*Phase 6 — Policy \& Guardrail Engine\*\*



↓



\*\*Phase 7 — Razorpay Test-Mode Execution\*\*



↓



\*\*Phase 8 — Measurement \& Control Group\*\*



↓



\*\*Phase 9 — Audit \& Failure Handling\*\*



↓



\*\*Phase 10 — Command Center UI\*\*



↓



\*\*Phase 11 — Automated Evaluation\*\*



↓



\*\*Phase 12 — Documentation + Architecture\*\*



↓



\*\*Phase 13 — Five-Minute Pitch\*\*



↓



\*\*Phase 14 — Final Submission\*\*



\---



\# FINAL RULE



\## We optimize for evidence, not features.



A smaller system that can convincingly demonstrate:



\*\*₹X incremental revenue recovered + why + how + under what policy + with what failure handling\*\*



is more valuable than a giant AI platform that cannot prove its business impact.



\*\*REVIVE v1.0 is now the foundation for implementation.\*\*



