"""
CLI script to generate synthetic subscription customer journey datasets for Revive.

Usage:
    python scripts/generate_dataset.py --customers 20000 --seed 42 --output-dir data/generated
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.simulation.generator import DatasetGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic subscription customer journey dataset for REVIVE.")
    parser.add_argument("--customers", type=int, default=20000, help="Target customer count (default: 20000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--output-dir", type=str, default="data/generated", help="Output directory path")

    args = parser.parse_args()

    print(f"Generating REVIVE synthetic dataset ({args.customers} customers, seed={args.seed})...")
    generator = DatasetGenerator(
        customers_count=args.customers,
        seed=args.seed,
        output_dir=args.output_dir,
    )

    stats = generator.generate()

    print("\n" + "=" * 50)
    print("      REVIVE DATASET GENERATION STATISTICS")
    print("=" * 50)
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"\n{key}:")
            for sub_k, sub_v in value.items():
                print(f"  {sub_k}: {sub_v}")
        else:
            print(f"{key}: {value}")
    print("=" * 50)
    print(f"Dataset saved to: {Path(args.output_dir).resolve()}\n")


if __name__ == "__main__":
    main()
