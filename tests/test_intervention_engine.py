"""
Unit and Integration Test Suite for Revive Phase 5 Intervention Decision Engine.
Tests eligibility gates, safety contraindications (S1-S5), deterministic EV scoring,
tie-breaking, human review escalation, ground-truth isolation, and decision schema validation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import pytest

from app.models.entities import Customer, Plan
from app.models.enums import EventType
from app.models.events import BaseEvent
from app.risk.scoring import ScoredCustomer
from app.diagnosis.schemas import Actionability, ConfidenceTier, CustomerDiagnosis, DiagnosisCategory, EvidenceCategory, EvidenceItem
from app.intervention.config import DEFAULT_INTERVENTION_CONFIG, InterventionConfig
from app.intervention.engine import InterventionEngine
from app.intervention.evaluation import InterventionEvaluator
from app.intervention.schemas import InterventionAction, InterventionDecision


@pytest.fixture
def sample_plan():
    return Plan(
        plan_id="pro",
        name="Pro Plan",
        price=Decimal("4999.00"),
        currency="INR",
        billing_interval="month",
    )


@pytest.fixture
def sample_customer():
    start = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    return Customer(
        customer_id="cus_int_001",
        merchant_id="merch_codecraft",
        created_at=start,
        plan_id="pro",
    )


@pytest.fixture
def base_scored_customer(sample_customer):
    pred_ts = (sample_customer.created_at + timedelta(hours=72)).isoformat()
    return ScoredCustomer(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=pred_ts,
        risk_score=0.75,
        risk_tier="HIGH",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=Decimal("3749.25"),
    )


# --- 16 SPECIFICATION TESTS ---

def test_1_low_risk_no_action(sample_customer, sample_plan):
    """Test 1: Customers with risk_score < 0.30 output NO_ACTION."""
    engine = InterventionEngine()
    low_risk_sc = ScoredCustomer(
        customer_id=sample_customer.customer_id,
        prediction_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=0.15,
        risk_tier="LOW",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=Decimal("0.00"),
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=0.15,
        risk_tier="LOW",
        diagnosis=DiagnosisCategory.NO_MEANINGFUL_RISK,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Low risk customer",
    )

    decision = engine.decide_intervention(low_risk_sc, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.NO_ACTION
    assert decision.eligibility_status == "INELIGIBLE"


def test_2_already_converted_no_action(sample_customer, sample_plan, base_scored_customer):
    """Test 2: Customers with ALREADY_CONVERTED diagnosis output NO_ACTION."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.ALREADY_CONVERTED,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Customer already converted",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.NO_ACTION
    assert decision.eligibility_status == "INELIGIBLE"


def test_3_insufficient_evidence_no_action(sample_customer, sample_plan, base_scored_customer):
    """Test 3: Customers with INSUFFICIENT_EVIDENCE output NO_ACTION."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.INSUFFICIENT_EVIDENCE,
        confidence=0.0,
        confidence_tier=ConfidenceTier.LOW,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="No diagnostic evidence available",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.NO_ACTION
    assert decision.eligibility_status == "INELIGIBLE"


def test_4_payment_recovery_selection(sample_customer, sample_plan, base_scored_customer):
    """Test 4: PAYMENT_FRICTION with payment failure evidence selects PAYMENT_RECOVERY."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Recorded 1 payment failure before snapshot (reason: bank_declined)",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.90,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment failed",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.PAYMENT_RECOVERY
    assert decision.eligibility_status == "ELIGIBLE"
    assert decision.expected_value > Decimal("0.00")


def test_5_checkout_assistance_selection(sample_customer, sample_plan, base_scored_customer):
    """Test 5: CHECKOUT_ABANDONMENT with checkout started evidence selects CHECKOUT_ASSISTANCE."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_STARTED,
        strength=1.0,
        description="Checkout started without completion",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.85,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout abandoned",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.CHECKOUT_ASSISTANCE
    assert decision.eligibility_status == "ELIGIBLE"


def test_6_product_guidance_selection(sample_customer, sample_plan, base_scored_customer):
    """Test 6: LOW_INTENT with low usage evidence selects PRODUCT_GUIDANCE."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,
        strength=1.0,
        description="Recorded 1 session during trial",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.LOW_INTENT,
        confidence=0.75,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Low product activity",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.PRODUCT_GUIDANCE
    assert decision.eligibility_status == "ELIGIBLE"


def test_7_human_review_escalation(sample_customer, sample_plan, base_scored_customer):
    """Test 7: High revenue at risk (>= Rs 2500) combined with MIXED_SIGNALS escalates to HUMAN_REVIEW."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.MIXED_SIGNALS,
        confidence=0.40,
        confidence_tier=ConfidenceTier.LOW,
        actionability=Actionability.REQUIRES_REVIEW,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Multiple competing causes",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.HUMAN_REVIEW
    assert decision.eligibility_status == "ESCALATED"


def test_8_high_value_alone_does_not_trigger_human_review(sample_customer, sample_plan, base_scored_customer):
    """Test 8: High revenue at risk alone does NOT trigger HUMAN_REVIEW when diagnosis is unambiguous."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Payment failed before snapshot",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.90,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,  # Unambiguous candidate
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment failed",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.PAYMENT_RECOVERY
    assert decision.eligibility_status == "ELIGIBLE"


def test_9_rule_s1_no_double_conversion(sample_customer, sample_plan, base_scored_customer):
    """Test 9: Rule S1 prevents active interventions for ALREADY_CONVERTED customers."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.ALREADY_CONVERTED,
        confidence=1.0,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.NONE,
        candidate_causes=[],
        supporting_evidence=[],
        explanation="Already converted",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.NO_ACTION


def test_10_rule_s2_payment_evidence_requirement(sample_customer, sample_plan, base_scored_customer):
    """Test 10: Rule S2 blocks PAYMENT_RECOVERY if payment evidence is missing."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[],  # Empty evidence!
        explanation="Payment friction without evidence",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    pay_rec_candidate = next(c for c in decision.candidate_scores if c.action == InterventionAction.PAYMENT_RECOVERY)
    assert pay_rec_candidate.is_eligible is False
    assert "Rule S2 Violation" in pay_rec_candidate.disqualification_reason


def test_11_rule_s3_checkout_evidence_requirement(sample_customer, sample_plan, base_scored_customer):
    """Test 11: Rule S3 blocks CHECKOUT_ASSISTANCE if checkout evidence is missing."""
    engine = InterventionEngine()
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[],  # Empty evidence!
        explanation="Checkout abandonment without evidence",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    chk_cand = next(c for c in decision.candidate_scores if c.action == InterventionAction.CHECKOUT_ASSISTANCE)
    assert chk_cand.is_eligible is False
    assert "Rule S3 Violation" in chk_cand.disqualification_reason


def test_12_rule_s4_trial_extension_timing(sample_customer, sample_plan, base_scored_customer):
    """Test 12: Rule S4 blocks TRIAL_EXTENSION if hours until trial expiry > 48h."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.TRIAL_EXPIRY_PROXIMITY,
        strength=1.0,
        description="Trial expiry proximity",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.TRIAL_EXPIRATION,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Trial expiring",
    )

    feat = {"hours_until_trial_expiry": 200.0}  # > 48h remaining!
    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, feat)

    ext_cand = next(c for c in decision.candidate_scores if c.action == InterventionAction.TRIAL_EXTENSION)
    assert ext_cand.is_eligible is False
    assert "Rule S4 Violation" in ext_cand.disqualification_reason


def test_13_rule_s5_positive_ev_requirement(sample_customer, sample_plan):
    """Test 13: Rule S5 disqualifies active interventions with non-positive Expected Value (EV <= 0.0)."""
    engine = InterventionEngine()
    low_val_sc = ScoredCustomer(
        customer_id=sample_customer.customer_id,
        prediction_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=0.40,
        risk_tier="MEDIUM",
        plan_id="pro",
        plan_price=Decimal("4999.00"),
        revenue_at_risk=Decimal("1.00"),  # EV will be negative due to costs
    )
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Payment failed",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp="2026-08-04T10:00:00+00:00",
        risk_score=0.40,
        risk_tier="MEDIUM",
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.50,
        confidence_tier=ConfidenceTier.MEDIUM,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment failed",
    )

    decision = engine.decide_intervention(low_val_sc, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.NO_ACTION


def test_14_deterministic_tie_breaking(sample_customer, sample_plan, base_scored_customer):
    """Test 14: Equal EV tie-breaking selects lower direct cost / alphabetical action."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,
        strength=1.0,
        description="Recorded low session activity",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.LOW_INTENT,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Low activity",
    )

    d1 = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    d2 = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})

    assert d1.selected_action == d2.selected_action
    assert d1.expected_value == d2.expected_value


def test_15_cooldown_enforcement(sample_customer, sample_plan, base_scored_customer):
    """Test 15: Active intervention cooldown period forces NO_ACTION."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Payment failed",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.90,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment failed",
    )

    history = [{"action": "PAYMENT_RECOVERY", "hours_since_last_intervention": 24.0}]  # Cooldown active (< 72h)!
    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {}, intervention_history=history)

    assert decision.selected_action == InterventionAction.NO_ACTION
    assert decision.eligibility_status == "COOLDOWN"


def test_16_ground_truth_isolation_and_schema_serialization(sample_customer, sample_plan, base_scored_customer):
    """Test 16: Verifies zero forbidden ground truth fields are required and InterventionDecision serializes to JSON cleanly."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.PAYMENT_FAILURE,
        strength=1.0,
        description="Payment failed",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.90,
        confidence_tier=ConfidenceTier.VERY_HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment failed",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})

    json_str = decision.model_dump_json()
    assert isinstance(json_str, str)

    reloaded = InterventionDecision.model_validate_json(json_str)
    assert reloaded.customer_id == decision.customer_id
    assert reloaded.selected_action == decision.selected_action
    assert reloaded.policy_version == "v1.0.0"
    assert reloaded.assumption_version == "v1.0.0"


# --- TARGETED REGRESSION TESTS FOR FIXES 1 - 4 ---

def test_s3_checkout_abandoned_only_cannot_authorize_checkout_assistance(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 1: CHECKOUT_ABANDONED evidence alone cannot satisfy Rule S3."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_ABANDONED,  # Abandoned only, NOT started!
        strength=1.0,
        description="Checkout abandoned recorded",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.85,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout abandoned",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    chk_cand = next(c for c in decision.candidate_scores if c.action == InterventionAction.CHECKOUT_ASSISTANCE)

    assert chk_cand.is_eligible is False
    assert "Rule S3 Violation" in chk_cand.disqualification_reason


def test_s3_checkout_started_authorizes_checkout_assistance(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 1 Positive Case: CHECKOUT_STARTED authorizes CHECKOUT_ASSISTANCE."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_STARTED,
        strength=1.0,
        description="Checkout started recorded",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.85,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout started",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    assert decision.selected_action == InterventionAction.CHECKOUT_ASSISTANCE


def test_closed_policy_matrix_rejects_undefined_pair(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 2: Closed policy matrix rejects undefined (diagnosis, action) pair."""
    engine = InterventionEngine()
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_STARTED,
        strength=1.0,
        description="Checkout started recorded",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,  # CHECKOUT_ABANDONMENT + PAYMENT_RECOVERY is undefined!
        confidence=0.85,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout started",
    )

    decision = engine.decide_intervention(base_scored_customer, diag, sample_plan, {})
    pay_rec_cand = next(c for c in decision.candidate_scores if c.action == InterventionAction.PAYMENT_RECOVERY)

    assert pay_rec_cand.is_eligible is False
    assert "No policy mapping" in pay_rec_cand.disqualification_reason


def test_evaluator_detects_s2_violation_in_manual_decision(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 3: InterventionEvaluator detects Rule S2 violation in manual decision."""
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.SESSION_ACTIVITY,  # No payment evidence!
        strength=1.0,
        description="Recorded 1 session",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.PAYMENT_FRICTION,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Payment friction",
    )

    # Manually create malformed decision with PAYMENT_RECOVERY despite missing payment evidence
    manual_decision = InterventionDecision(
        customer_id=sample_customer.customer_id,
        decision_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        revenue_at_risk=base_scored_customer.revenue_at_risk,
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.80,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("100.00"),
        candidate_scores=[],
        decision_reason="Manual",
        supporting_evidence=[ev_item.description],
    )

    is_compliant = InterventionEvaluator.verify_safety_compliance_single(
        manual_decision, diagnosis=diag
    )
    assert is_compliant is False


def test_evaluator_detects_s3_violation_in_manual_decision(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 3: InterventionEvaluator detects Rule S3 violation in manual decision."""
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_ABANDONED,  # Abandoned ONLY, NOT started!
        strength=1.0,
        description="Checkout abandoned",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout abandoned",
    )

    manual_decision = InterventionDecision(
        customer_id=sample_customer.customer_id,
        decision_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        revenue_at_risk=base_scored_customer.revenue_at_risk,
        diagnosis="CHECKOUT_ABANDONMENT",
        diagnosis_confidence=0.80,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.CHECKOUT_ASSISTANCE,
        expected_value=Decimal("100.00"),
        candidate_scores=[],
        decision_reason="Manual",
        supporting_evidence=[ev_item.description],
    )

    is_compliant = InterventionEvaluator.verify_safety_compliance_single(
        manual_decision, diagnosis=diag
    )
    assert is_compliant is False


def test_evaluator_detects_s4_violation_in_manual_decision(sample_customer, sample_plan, base_scored_customer):
    """Targeted Fix 3: InterventionEvaluator detects Rule S4 violation in manual decision (expiry > 48h)."""
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.TRIAL_EXPIRY_PROXIMITY,
        strength=1.0,
        description="Trial expiry proximity",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.TRIAL_EXPIRATION,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Trial expiring",
    )

    manual_decision = InterventionDecision(
        customer_id=sample_customer.customer_id,
        decision_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        revenue_at_risk=base_scored_customer.revenue_at_risk,
        diagnosis="TRIAL_EXPIRATION",
        diagnosis_confidence=0.80,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.TRIAL_EXTENSION,
        expected_value=Decimal("100.00"),
        candidate_scores=[],
        decision_reason="Manual",
        supporting_evidence=[ev_item.description],
    )

    feat = {"hours_until_trial_expiry": 200.0}  # Expiry > 48h!
    is_compliant = InterventionEvaluator.verify_safety_compliance_single(
        manual_decision, diagnosis=diag, feature_record=feat
    )
    assert is_compliant is False


def test_evaluator_uses_structured_evidence_categories(sample_customer, base_scored_customer):
    """Targeted Fix 4: InterventionEvaluator uses structured EvidenceCategory enums."""
    ev_item = EvidenceItem(
        evidence_type=EvidenceCategory.CHECKOUT_STARTED,
        strength=1.0,
        description="User started checkout flow",
    )
    diag = CustomerDiagnosis(
        customer_id=sample_customer.customer_id,
        prediction_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        diagnosis=DiagnosisCategory.CHECKOUT_ABANDONMENT,
        confidence=0.80,
        confidence_tier=ConfidenceTier.HIGH,
        actionability=Actionability.CANDIDATE,
        candidate_causes=[],
        supporting_evidence=[ev_item],
        explanation="Checkout started",
    )

    manual_decision = InterventionDecision(
        customer_id=sample_customer.customer_id,
        decision_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        revenue_at_risk=base_scored_customer.revenue_at_risk,
        diagnosis="CHECKOUT_ABANDONMENT",
        diagnosis_confidence=0.80,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.CHECKOUT_ASSISTANCE,
        expected_value=Decimal("100.00"),
        candidate_scores=[],
        decision_reason="Manual",
        supporting_evidence=[ev_item.description],
    )

    is_consistent = InterventionEvaluator.verify_evidence_action_consistency(
        manual_decision, diagnosis=diag
    )
    assert is_consistent is True


def test_evaluator_rejects_text_only_evidence_without_structured_diagnosis(sample_customer, base_scored_customer):
    """Proves that arbitrary text such as 'payment failed' cannot satisfy PAYMENT_RECOVERY when no structured EvidenceCategory is supplied."""
    manual_decision = InterventionDecision(
        customer_id=sample_customer.customer_id,
        decision_timestamp=base_scored_customer.prediction_timestamp,
        risk_score=base_scored_customer.risk_score,
        risk_tier=base_scored_customer.risk_tier,
        revenue_at_risk=base_scored_customer.revenue_at_risk,
        diagnosis="PAYMENT_FRICTION",
        diagnosis_confidence=0.80,
        diagnosis_actionability="candidate",
        eligibility_status="ELIGIBLE",
        selected_action=InterventionAction.PAYMENT_RECOVERY,
        expected_value=Decimal("100.00"),
        candidate_scores=[],
        decision_reason="Manual",
        supporting_evidence=["payment failed bank declined"],
    )

    is_consistent = InterventionEvaluator.verify_evidence_action_consistency(
        manual_decision, diagnosis=None
    )
    assert is_consistent is False
