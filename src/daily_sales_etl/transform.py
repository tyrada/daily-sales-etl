"""CSV schema validation and deterministic row cleaning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = (
    "transaction_id",
    "transaction_date",
    "customer_id",
    "product_id",
    "quantity",
    "unit_price",
    "currency",
)


class InputError(Exception):
    """Raised when an input file cannot be parsed or lacks its required schema."""

    def __init__(self, message: str, input_count: int = 0):
        super().__init__(message)
        self.input_count = input_count


@dataclass(frozen=True)
class TransformResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame
    input_count: int


def read_sales_csv(path: Path) -> pd.DataFrame:
    """Read every field as text so cleaning rules, not inference, control types."""
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise InputError(f"could not read CSV: {exc}") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise InputError(f"missing required columns: {', '.join(missing)}", input_count=len(frame))
    return frame


def _clean_text(value: object) -> str:
    return str(value).strip()


def transform_sales(frame: pd.DataFrame) -> TransformResult:
    """Clean valid records and quarantine invalid or duplicate input rows."""
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise InputError(f"missing required columns: {', '.join(missing)}")

    valid_rows: list[dict[str, object]] = []
    rejected_rows: list[dict[str, object]] = []
    seen_transaction_ids: set[str] = set()

    for source_row_number, (_, source_row) in enumerate(frame.iterrows(), start=2):
        raw = {column: _clean_text(source_row[column]) for column in REQUIRED_COLUMNS}
        reasons: list[str] = []

        transaction_id = raw["transaction_id"]
        if not transaction_id:
            reasons.append("missing transaction_id")
        elif transaction_id in seen_transaction_ids:
            reasons.append("duplicate transaction_id")
        else:
            seen_transaction_ids.add(transaction_id)

        try:
            sale_date = datetime.strptime(raw["transaction_date"], "%Y-%m-%d").date()
        except ValueError:
            sale_date = None
            reasons.append("transaction_date must be YYYY-MM-DD")

        customer_id = raw["customer_id"]
        product_id = raw["product_id"]
        if not customer_id:
            reasons.append("missing customer_id")
        if not product_id:
            reasons.append("missing product_id")

        try:
            quantity_decimal = Decimal(raw["quantity"])
            if quantity_decimal != quantity_decimal.to_integral_value() or quantity_decimal <= 0:
                raise InvalidOperation
            quantity = int(quantity_decimal)
        except (InvalidOperation, ValueError):
            quantity = None
            reasons.append("quantity must be a positive integer")

        try:
            unit_price = Decimal(raw["unit_price"])
            if not unit_price.is_finite() or unit_price <= 0:
                raise InvalidOperation
            unit_price = unit_price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            unit_price = None
            reasons.append("unit_price must be a positive number")

        currency = raw["currency"].upper()
        if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
            reasons.append("currency must be a three-letter code")

        if reasons:
            rejected_rows.append(
                {**raw, "source_row_number": source_row_number, "rejection_reason": "; ".join(reasons)}
            )
        else:
            valid_rows.append(
                {
                    "transaction_id": transaction_id,
                    "sale_date": sale_date,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "currency": currency,
                }
            )

    return TransformResult(
        valid=pd.DataFrame(valid_rows, columns=("transaction_id", "sale_date", "customer_id", "product_id", "quantity", "unit_price", "currency")),
        rejected=pd.DataFrame(rejected_rows, columns=(*REQUIRED_COLUMNS, "source_row_number", "rejection_reason")),
        input_count=len(frame),
    )

