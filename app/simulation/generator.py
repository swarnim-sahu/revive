"""
Dataset Generator and Evaluator for Revive synthetic customer journeys.
"""

from decimal import Decimal
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

from app.models.entities import Customer, Payment, Plan, Subscription, Trial
from app.models.events import BaseEvent
from app.simulation.behaviour import sample_behaviour
from app.simulation.config import (
    ALL_PLANS,
    SYNTHETIC_MERCHANT,
    TARGET_PLAN_PERCENTAGES,
    TARGET_SEGMENT_PERCENTAGES,
    calculate_counts,
)
from app.simulation.ground_truth import GroundTruthRecord
from app.simulation.journey import generate_customer_journey
from app.simulation.segments import create_ground_truth


class DatasetGenerator:
    """Orchestrates reproducible generation, validation, and serialization of synthetic datasets."""

    def __init__(
        self,
        customers_count: int = 20000,
        seed: int = 42,
        output_dir: str = "data/generated",
    ) -> None:
        self.customers_count = customers_count
        self.seed = seed
        self.output_dir = Path(output_dir)
        self.rng = random.Random(seed)

    def _allocate_plans_and_segments(self) -> List[Tuple[str, str]]:
        """
        Allocate segment and plan for each customer such that total plan and segment counts
        match target distributions, and high_value_at_risk segment prioritizes business plan.
        """
        seg_counts = calculate_counts(self.customers_count, TARGET_SEGMENT_PERCENTAGES)
        plan_counts = calculate_counts(self.customers_count, TARGET_PLAN_PERCENTAGES)

        # Build list of segments
        segment_pool: List[str] = []
        for seg, count in seg_counts.items():
            segment_pool.extend([seg] * count)

        # Build list of plans
        plan_pool: List[str] = []
        for plan_id, count in plan_counts.items():
            plan_pool.extend([plan_id] * count)

        # Shuffle pools using seeded rng
        self.rng.shuffle(segment_pool)
        self.rng.shuffle(plan_pool)

        # Pair them up, prioritizing business plan for high_value_at_risk
        assignments: List[Tuple[str, str]] = []
        b_indices = [i for i, p in enumerate(plan_pool) if p == "business"]
        b_idx_pos = 0

        # First pass for high_value_at_risk to get business plan where available
        plan_assigned = [False] * len(plan_pool)

        for i, seg in enumerate(segment_pool):
            if seg == "high_value_at_risk" and b_idx_pos < len(b_indices):
                # Assign a business plan
                p_idx = b_indices[b_idx_pos]
                plan_assigned[p_idx] = True
                b_idx_pos += 1
                assignments.append((seg, "business"))
            else:
                assignments.append((seg, ""))  # To be filled in second pass

        # Fill remaining unassigned plan slots
        remaining_plans = [p for i, p in enumerate(plan_pool) if not plan_assigned[i]]
        rem_idx = 0

        final_pairs: List[Tuple[str, str]] = []
        for seg, p in assignments:
            if p != "":
                final_pairs.append((seg, p))
            else:
                final_pairs.append((seg, remaining_plans[rem_idx]))
                rem_idx += 1

        return final_pairs

    def generate(self) -> Dict[str, Any]:
        """
        Generate customers, trials, events, payments, subscriptions, and ground truth.
        Validates output and writes to JSONL files. Returns dataset statistics.
        """
        pairs = self._allocate_plans_and_segments()

        customers: List[Customer] = []
        trials: List[Trial] = []
        events: List[BaseEvent] = []
        payments: List[Payment] = []
        subscriptions: List[Subscription] = []
        ground_truth_records: List[GroundTruthRecord] = []

        merchant_id = SYNTHETIC_MERCHANT.merchant_id

        for idx, (segment, plan_id) in enumerate(pairs, start=1):
            customer_id = f"cus_{idx:06d}"
            plan = ALL_PLANS[plan_id]

            # 1. Ground truth
            gt = create_ground_truth(customer_id, segment, plan, self.rng)
            ground_truth_records.append(gt)

            # 2. Behaviour
            behaviour = sample_behaviour(segment, gt.natural_conversion, self.rng)

            # 3. Journey
            cus, trl, evts, pay, sub = generate_customer_journey(
                customer_id=customer_id,
                merchant_id=merchant_id,
                plan=plan,
                behaviour=behaviour,
                rng=self.rng,
            )

            customers.append(cus)
            trials.append(trl)
            events.extend(evts)
            if pay is not None:
                payments.append(pay)
            if sub is not None:
                subscriptions.append(sub)

        # Validate
        self.validate(customers, events, payments, subscriptions, ground_truth_records)

        # Write data
        self._write_files(customers, events, ground_truth_records)

        # Statistics
        stats = self.calculate_statistics(
            customers, trials, events, payments, subscriptions, ground_truth_records
        )
        return stats

    def validate(
        self,
        customers: List[Customer],
        events: List[BaseEvent],
        payments: List[Payment],
        subscriptions: List[Subscription],
        ground_truth_records: List[GroundTruthRecord],
    ) -> None:
        """Run comprehensive validation checks on the generated dataset."""
        # 1. Identity
        assert len(customers) == self.customers_count, f"Expected {self.customers_count} customers, got {len(customers)}"
        customer_ids = {c.customer_id for c in customers}
        assert len(customer_ids) == self.customers_count, "Duplicate customer IDs found"

        event_ids = {e.event_id for e in events}
        assert len(event_ids) == len(events), "Duplicate event IDs found"

        # 2. Referential integrity
        for e in events:
            assert e.customer_id in customer_ids, f"Event {e.event_id} references unknown customer {e.customer_id}"
            assert e.merchant_id == SYNTHETIC_MERCHANT.merchant_id, "Invalid merchant ID in event"

        for p in payments:
            assert p.customer_id in customer_ids, f"Payment {p.payment_id} references unknown customer {p.customer_id}"
            assert p.amount >= Decimal("0.00"), f"Payment {p.payment_id} has negative amount"

        for s in subscriptions:
            assert s.customer_id in customer_ids, f"Subscription {s.subscription_id} references unknown customer"
            assert s.amount >= Decimal("0.00"), "Subscription has negative amount"

        # 3. Ground truth separation & match
        gt_ids = {gt.customer_id for gt in ground_truth_records}
        assert len(gt_ids) == len(ground_truth_records) == self.customers_count, "Ground truth count or ID mismatch"
        assert gt_ids == customer_ids, "Ground truth IDs do not match customer IDs"

        hidden_fields = {
            "generation_segment",
            "natural_conversion",
            "conversion_after_intervention",
            "recoverable",
            "maximum_recoverable_revenue",
            "true_root_cause",
        }

        for e in events:
            for field in hidden_fields:
                assert field not in e.payload, f"Hidden field '{field}' leaked into event payload!"

        for c in customers:
            c_dict = c.model_dump()
            for field in hidden_fields:
                assert field not in c_dict, f"Hidden field '{field}' leaked into customer record!"

        # 4. Chronology
        for e in events:
            assert e.timestamp.tzinfo is not None, f"Event {e.event_id} timestamp is naive!"

    def _write_files(
        self,
        customers: List[Customer],
        events: List[BaseEvent],
        ground_truth_records: List[GroundTruthRecord],
    ) -> None:
        """Write JSONL files to observable and ground truth directories."""
        obs_dir = self.output_dir / "observable"
        gt_dir = self.output_dir / "ground_truth"

        obs_dir.mkdir(parents=True, exist_ok=True)
        gt_dir.mkdir(parents=True, exist_ok=True)

        # Write plans.jsonl
        with open(obs_dir / "plans.jsonl", "w", encoding="utf-8") as f:
            for plan in ALL_PLANS.values():
                f.write(plan.model_dump_json() + "\n")

        # Write customers.jsonl
        with open(obs_dir / "customers.jsonl", "w", encoding="utf-8") as f:
            for c in customers:
                f.write(c.model_dump_json() + "\n")

        # Write events.jsonl
        with open(obs_dir / "events.jsonl", "w", encoding="utf-8") as f:
            for e in events:
                f.write(e.model_dump_json() + "\n")

        # Write ground_truth.jsonl
        with open(gt_dir / "ground_truth.jsonl", "w", encoding="utf-8") as f:
            for gt in ground_truth_records:
                f.write(gt.model_dump_json() + "\n")

    def calculate_statistics(
        self,
        customers: List[Customer],
        trials: List[Trial],
        events: List[BaseEvent],
        payments: List[Payment],
        subscriptions: List[Subscription],
        ground_truth_records: List[GroundTruthRecord],
    ) -> Dict[str, Any]:
        """Compute summary statistics for the dataset."""
        seg_counts: Dict[str, int] = {}
        for gt in ground_truth_records:
            seg_counts[gt.generation_segment] = seg_counts.get(gt.generation_segment, 0) + 1

        plan_counts: Dict[str, int] = {}
        for c in customers:
            plan_counts[c.plan_id] = plan_counts.get(c.plan_id, 0) + 1

        succ_payments = sum(1 for p in payments if p.status.value == "succeeded")
        fail_payments = sum(1 for p in payments if p.status.value == "failed")
        checkout_starts = sum(1 for e in events if e.event_type.value == "checkout_started")
        checkout_abandonments = sum(1 for e in events if e.event_type.value == "checkout_abandoned")

        natural_conversions = sum(1 for gt in ground_truth_records if gt.natural_conversion)
        recoverable_customers = sum(1 for gt in ground_truth_records if gt.recoverable)

        stats = {
            "Customers": len(customers),
            "Events": len(events),
            "Trials": len(trials),
            "Subscriptions": len(subscriptions),
            "Payments": len(payments),
            "Successful payments": succ_payments,
            "Failed payments": fail_payments,
            "Checkout starts": checkout_starts,
            "Checkout abandonments": checkout_abandonments,
            "Natural conversions": natural_conversions,
            "Recoverable customers": recoverable_customers,
            "Segment counts": seg_counts,
            "Plan counts": plan_counts,
        }
        return stats
