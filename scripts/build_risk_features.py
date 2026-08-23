"""
CLI script to build snapshot risk features from observable datasets for Revive.

Usage:
    python scripts/build_risk_features.py --output data/processed/risk_features.json
"""

import argparse
import json
from pathlib import Path
import sys

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.risk.features import FeatureDatasetBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build snapshot risk features from Revive observable events.")
    parser.add_argument("--customers-file", type=str, default="data/generated/observable/customers.jsonl")
    parser.add_argument("--plans-file", type=str, default="data/generated/observable/plans.jsonl")
    parser.add_argument("--events-file", type=str, default="data/generated/observable/events.jsonl")
    parser.add_argument("--ground-truth-file", type=str, default="data/generated/ground_truth/ground_truth.jsonl")
    parser.add_argument("--output", type=str, default="data/processed/risk_features.json")
    parser.add_argument("--snapshot-hours", type=float, default=72.0)

    args = parser.parse_args()

    print(f"Building risk features from observable data (snapshot={args.snapshot_hours}h)...")
    builder = FeatureDatasetBuilder(snapshot_hours=args.snapshot_hours)

    features, labels = builder.load_and_build(
        customers_file=args.customers_file,
        plans_file=args.plans_file,
        events_file=args.events_file,
        ground_truth_file=args.ground_truth_file,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "snapshot_hours": args.snapshot_hours,
        "count": len(features),
        "features": features,
        "labels": labels,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Extracted features for {len(features)} customers.")
    print(f"Saved feature dataset to: {out_path.resolve()}\n")


if __name__ == "__main__":
    main()
