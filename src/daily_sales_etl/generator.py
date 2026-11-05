"""Reproducible synthetic daily sales data generator."""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date
from pathlib import Path

PRODUCT_PRICES = {
    "P-100": "12.50",
    "P-200": "25.00",
    "P-300": "7.75",
    "P-400": "49.99",
}


def generate_sales(output: Path, sales_date: date, rows: int, seed: int) -> None:
    """Generate the same output for the same date, row count, and seed."""
    rng = random.Random(seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("transaction_id", "transaction_date", "customer_id", "product_id", "quantity", "unit_price", "currency"),
        )
        writer.writeheader()
        for position in range(1, rows + 1):
            product_id = rng.choice(sorted(PRODUCT_PRICES))
            writer.writerow(
                {
                    "transaction_id": f"TX-{sales_date:%Y%m%d}-{position:06d}",
                    "transaction_date": sales_date.isoformat(),
                    "customer_id": f"C-{rng.randint(1, 50):04d}",
                    "product_id": product_id,
                    "quantity": rng.randint(1, 5),
                    "unit_price": PRODUCT_PRICES[product_id],
                    "currency": "USD",
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic daily sales CSV data")
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="sales date in YYYY-MM-DD format")
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.rows < 0:
        raise SystemExit("--rows must be non-negative")
    output = args.output or Path("data/incoming") / f"sales_{args.date:%Y%m%d}.csv"
    generate_sales(output, args.date, args.rows, args.seed)
    print(f"generated {args.rows} rows at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

