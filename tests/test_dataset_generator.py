"""
Unit and integration tests for Revive synthetic customer journey generator.
"""

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import pytest

from app.simulation.config import ALL_PLANS
from app.simulation.generator import DatasetGenerator
from app.simulation.ground_truth import GroundTruthRecord


def test_generation_customer_count():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=100, seed=42, output_dir=tmp_dir)
        stats = gen.generate()

        assert stats["Customers"] == 100
        assert stats["Events"] > 100
        assert stats["Trials"] == 100

        # Check observable customer file line count
        customers_file = Path(tmp_dir) / "observable" / "customers.jsonl"
        with open(customers_file, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 100


def test_reproducibility():
    with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
        gen1 = DatasetGenerator(customers_count=200, seed=123, output_dir=dir1)
        gen1.generate()

        gen2 = DatasetGenerator(customers_count=200, seed=123, output_dir=dir2)
        gen2.generate()

        # Compare output files
        for filename in ["observable/customers.jsonl", "observable/events.jsonl", "ground_truth/ground_truth.jsonl"]:
            f1 = (Path(dir1) / filename).read_text(encoding="utf-8")
            f2 = (Path(dir2) / filename).read_text(encoding="utf-8")
            assert f1 == f2, f"File content mismatch for {filename}"


def test_segment_and_plan_distribution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=1000, seed=42, output_dir=tmp_dir)
        stats = gen.generate()

        seg_counts = stats["Segment counts"]
        assert seg_counts["healthy_converter"] == 200
        assert seg_counts["low_intent"] == 200
        assert seg_counts["checkout_abandoner"] == 150
        assert seg_counts["payment_friction"] == 120
        assert seg_counts["trial_expiring"] == 100
        assert seg_counts["high_value_at_risk"] == 80
        assert seg_counts["ambiguous"] == 100
        assert seg_counts["already_converted"] == 50

        plan_counts = stats["Plan counts"]
        assert plan_counts["starter"] == 500
        assert plan_counts["pro"] == 350
        assert plan_counts["business"] == 150


def test_ground_truth_counterfactual_consistency():
    """Verify counterfactual equations across all ground truth records."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        # Load customer plan map
        customer_plans = {}
        with open(Path(tmp_dir) / "observable" / "customers.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                customer_plans[c["customer_id"]] = c["plan_id"]

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                gt = json.loads(line)
                rec = GroundTruthRecord(**gt)

                # Rule 1: recoverable == conversion_after_intervention and not natural_conversion
                expected_recoverable = rec.conversion_after_intervention and (not rec.natural_conversion)
                assert rec.recoverable == expected_recoverable, (
                    f"Recoverable mismatch for customer {rec.customer_id}"
                )

                # Rule 2: max revenue consistency
                plan_price = ALL_PLANS[customer_plans[rec.customer_id]].price
                if not rec.recoverable:
                    assert rec.maximum_recoverable_revenue == Decimal("0.00")
                else:
                    assert rec.maximum_recoverable_revenue == plan_price


def test_ground_truth_separation_and_exact_record_count():
    """Verify observable files leak no hidden fields and ground truth has exactly 1 record per customer."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=300, seed=42, output_dir=tmp_dir)
        gen.generate()

        hidden_fields = {
            "generation_segment",
            "natural_conversion",
            "conversion_after_intervention",
            "recoverable",
            "maximum_recoverable_revenue",
            "true_root_cause",
        }

        # Inspect observable events file
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                payload = data.get("payload", {})
                for field in hidden_fields:
                    assert field not in data, f"Leaked {field} in event top level"
                    assert field not in payload, f"Leaked {field} in event payload"

        # Inspect observable customers file
        customer_ids = set()
        customers_file = Path(tmp_dir) / "observable" / "customers.jsonl"
        with open(customers_file, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                customer_ids.add(data["customer_id"])
                for field in hidden_fields:
                    assert field not in data, f"Leaked {field} in customer record"

        # Verify ground truth record count and matching IDs
        gt_ids = []
        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                gt_ids.append(rec["customer_id"])

        assert len(gt_ids) == len(customer_ids) == 300, "Ground truth record count mismatch"
        assert set(gt_ids) == customer_ids, "Ground truth IDs do not match customer IDs"


def test_event_lifecycle_ordering():
    """Verify strict chronological event ordering and lifecycle constraints for every customer."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        events_by_customer = {}
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                cid = data["customer_id"]
                events_by_customer.setdefault(cid, []).append(data)

        for cid, evts in events_by_customer.items():
            # Check timezone awareness of all timestamps
            for e in evts:
                ts_str = e["timestamp"]
                assert "Z" in ts_str or "+" in ts_str, f"Event {e['event_id']} timestamp not timezone-aware"

            # Index timestamps by event_type
            type_ts = {}
            for e in evts:
                type_ts.setdefault(e["event_type"], []).append(e["timestamp"])

            # 1. customer_created < trial_started
            assert "customer_created" in type_ts
            assert "trial_started" in type_ts
            assert type_ts["customer_created"][0] < type_ts["trial_started"][0]

            # 2. trial_started < trial_expired (if trial_expired exists)
            if "trial_expired" in type_ts:
                assert type_ts["trial_started"][0] < type_ts["trial_expired"][0]

            # 3. If subscription_created exists: payment_succeeded < subscription_created
            if "subscription_created" in type_ts:
                assert "payment_succeeded" in type_ts
                assert type_ts["payment_succeeded"][0] < type_ts["subscription_created"][0]

            # 4. If payment_failed exists: payment_attempted < payment_failed
            if "payment_failed" in type_ts:
                assert "payment_attempted" in type_ts
                assert type_ts["payment_attempted"][0] < type_ts["payment_failed"][0]

            # 5. If checkout_completed exists: checkout_started < checkout_completed
            if "checkout_completed" in type_ts:
                assert "checkout_started" in type_ts
                assert type_ts["checkout_started"][0] < type_ts["checkout_completed"][0]

            # 6. If checkout_abandoned exists: checkout_started < checkout_abandoned
            if "checkout_abandoned" in type_ts:
                assert "checkout_started" in type_ts
                assert type_ts["checkout_started"][0] < type_ts["checkout_abandoned"][0]


def test_payment_friction_counterfactual_case():
    """
    Verify counterfactual scenario where natural_conversion=True but observable journey contains payment_failed.
    This scenario represents high-intent users who would convert naturally (e.g. by retrying later),
    making recoverable=False for intervention evaluation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=1000, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        friction_naturally_convertible_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "payment_friction" and rec["natural_conversion"]:
                    friction_naturally_convertible_ids.add(rec["customer_id"])
                    assert rec["recoverable"] is False

        # Verify these customers have payment_failed in their observable event stream
        failed_count = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in friction_naturally_convertible_ids and evt["event_type"] == "payment_failed":
                    failed_count += 1

        assert failed_count > 0, "Expected payment_failed events for naturally convertible payment friction subgroup"


# --- SEGMENT BEHAVIOUR TESTS ---

def test_healthy_converter_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        healthy_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "healthy_converter":
                    healthy_ids.add(rec["customer_id"])

        # Check conversion rate for healthy converters
        converted = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in healthy_ids and evt["event_type"] == "subscription_created":
                    converted += 1

        conv_rate = converted / len(healthy_ids)
        assert conv_rate >= 0.80, f"Expected high conversion for healthy converters, got {conv_rate}"


def test_low_intent_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        low_intent_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "low_intent":
                    low_intent_ids.add(rec["customer_id"])

        session_counts = {cid: 0 for cid in low_intent_ids}
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in low_intent_ids and evt["event_type"] == "session_started":
                    session_counts[evt["customer_id"]] += 1

        avg_sessions = sum(session_counts.values()) / len(low_intent_ids)
        assert avg_sessions <= 5, f"Expected low sessions for low intent, got average {avg_sessions}"


def test_checkout_abandoner_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        abandoner_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "checkout_abandoner":
                    abandoner_ids.add(rec["customer_id"])

        abandoned_count = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in abandoner_ids and evt["event_type"] == "checkout_abandoned":
                    abandoned_count += 1

        assert abandoned_count == len(abandoner_ids)


def test_payment_friction_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        friction_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "payment_friction":
                    friction_ids.add(rec["customer_id"])

        failed_payments = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in friction_ids and evt["event_type"] == "payment_failed":
                    failed_payments += 1

        assert failed_payments == len(friction_ids)


def test_trial_expiring_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        expiring_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "trial_expiring":
                    expiring_ids.add(rec["customer_id"])

        expiring_events = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in expiring_ids and evt["event_type"] == "trial_expiring":
                    expiring_events += 1

        assert expiring_events > 0


def test_high_value_at_risk_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        hv_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "high_value_at_risk":
                    hv_ids.add(rec["customer_id"])

        # High value segment should predominantly be assigned business plan
        business_plan_count = 0
        customers_file = Path(tmp_dir) / "observable" / "customers.jsonl"
        with open(customers_file, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                if c["customer_id"] in hv_ids and c["plan_id"] == "business":
                    business_plan_count += 1

        assert business_plan_count / len(hv_ids) >= 0.70


def test_ambiguous_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        ambiguous_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "ambiguous":
                    ambiguous_ids.add(rec["customer_id"])

        assert len(ambiguous_ids) > 0


def test_already_converted_segment_properties():
    with tempfile.TemporaryDirectory() as tmp_dir:
        gen = DatasetGenerator(customers_count=500, seed=42, output_dir=tmp_dir)
        gen.generate()

        gt_file = Path(tmp_dir) / "ground_truth" / "ground_truth.jsonl"
        converted_ids = set()
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["generation_segment"] == "already_converted":
                    converted_ids.add(rec["customer_id"])

        sub_events = 0
        events_file = Path(tmp_dir) / "observable" / "events.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                evt = json.loads(line)
                if evt["customer_id"] in converted_ids and evt["event_type"] == "subscription_created":
                    sub_events += 1

        assert sub_events == len(converted_ids)
