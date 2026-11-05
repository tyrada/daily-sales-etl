from decimal import Decimal

import pandas as pd
import pytest

from daily_sales_etl.transform import InputError, read_sales_csv, transform_sales


def test_transform_cleans_valid_rows_and_quarantines_invalid_and_duplicate_rows():
    source = pd.DataFrame(
        [
            ["TX-1", "2026-01-15", " C-1 ", "P-1", "2", "10.129", "usd"],
            ["TX-1", "2026-01-15", "C-2", "P-2", "1", "5.00", "USD"],
            ["TX-3", "15/01/2026", "", "P-3", "0", "free", "US"],
        ],
        columns=(
            "transaction_id",
            "transaction_date",
            "customer_id",
            "product_id",
            "quantity",
            "unit_price",
            "currency",
        ),
    )

    result = transform_sales(source)

    assert result.input_count == 3
    assert len(result.valid) == 1
    assert result.valid.iloc[0].to_dict() == {
        "transaction_id": "TX-1",
        "sale_date": pd.Timestamp("2026-01-15").date(),
        "customer_id": "C-1",
        "product_id": "P-1",
        "quantity": 2,
        "unit_price": Decimal("10.13"),
        "currency": "USD",
    }
    assert len(result.rejected) == 2
    assert "duplicate transaction_id" in result.rejected.iloc[0]["rejection_reason"]
    assert "quantity must be a positive integer" in result.rejected.iloc[1]["rejection_reason"]
    assert result.rejected.iloc[1]["source_row_number"] == 4


def test_read_sales_csv_rejects_missing_required_columns(tmp_path):
    input_path = tmp_path / "malformed.csv"
    input_path.write_text("transaction_id,quantity\nTX-1,2\n", encoding="utf-8")

    with pytest.raises(InputError, match="missing required columns"):
        read_sales_csv(input_path)

