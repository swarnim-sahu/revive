"""
REVIVE — Controlled Razorpay Test Mode Demonstration CLI Runner.

Explicit, user-invoked CLI script to demonstrate Phase 9 Razorpay Test Mode
recovery execution without violating safety boundaries or making automatic calls.

Usage:
    # Dry run (safe baseline, zero network access):
    python scripts/run_razorpay_sandbox_demo.py --dry-run

    # Live controlled demonstration (requires explicit test credentials in environment):
    RAZORPAY_EXECUTION_MODE=sandbox RAZORPAY_KEY_ID=rzp_test_... RAZORPAY_KEY_SECRET=... python scripts/run_razorpay_sandbox_demo.py --execute
"""

import argparse
import json
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.integrations.razorpay.config import RazorpayConfig
from app.integrations.razorpay.demo_runner import run_controlled_sandbox_demonstration


def main() -> int:
    parser = argparse.ArgumentParser(
        description="REVIVE Controlled Razorpay Test Mode Demonstration Runner"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the controlled demonstration using configured environment credentials.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run without external execution (writes/verifies NOT_RUN baseline).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output path for the demonstration evidence artifact.",
    )

    args = parser.parse_args()

    # Default to dry-run unless --execute is explicitly given
    is_dry_run = args.dry_run or (not args.execute)

    print("=" * 68)
    print(" REVIVE — CONTROLLED RAZORPAY TEST MODE DEMONSTRATION")
    print("=" * 68)
    print(f" Mode: {'DRY RUN (UNEXECUTED)' if is_dry_run else 'LIVE TEST MODE EXECUTION'}")
    print(" Architecture Boundary: Phase 5 Policy -> Phase 6 ExecutionEngine -> Razorpay")
    print(" Invariant: Payment Link Created != Payment Recovered")
    print("-" * 68)

    try:
        config = RazorpayConfig.from_env()
        custom_path = Path(args.output) if args.output else None

        result = run_controlled_sandbox_demonstration(
            config=config,
            dry_run=is_dry_run,
            save_artifact=True,
            artifact_path=custom_path,
        )

        print("\nDemonstration Summary:")
        print(f"  - Operation:           {result.get('operation')}")
        print(f"  - Execution Status:    {result.get('execution_status')}")
        print(f"  - Payment Status:      {result.get('payment_status')}")
        print(f"  - Payload ID:          {result.get('payload_id')}")
        print(f"  - Provider Reference:  {result.get('provider_reference') or 'None (Not Created)'}")
        print(f"  - Short URL:           {result.get('short_url') or 'None'}")
        print(f"  - Webhook Status:      {result.get('webhook_status')}")
        print(f"  - Outcome Status:      {result.get('outcome_status')}")
        print(f"  - Attribution Status:  {result.get('attribution_status')}")
        print(f"  - Idempotency Result:  {result.get('idempotency_result')}")

        if result.get("failure_reason"):
            print(f"  - Failure Reason:      {result.get('failure_reason')}")

        print("\nPolicy Context:")
        pol = result.get("policy_decision", {})
        print(f"  - Customer ID:         {pol.get('customer_id')}")
        print(f"  - Selected Action:     {pol.get('selected_action')}")
        print(f"  - Eligibility:         {pol.get('eligibility_status')}")
        print(f"  - Expected Value:      INR {pol.get('expected_value', 0.0):.2f}")
        print(f"  - Revenue at Risk:     INR {pol.get('revenue_at_risk', 0.0):.2f}")



        print("\n" + "-" * 68)
        print(f"Evidence Artifact written to:")
        print(f"  docs/evidence/phase9_razorpay_sandbox_demo.json")
        print("=" * 68)
        return 0

    except Exception as exc:
        print(f"\n[ERROR] Demonstration failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
