from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from daily_sales_etl.database import SalesRepository


class RecordingCursor:
    def __init__(self, fail_on_second: bool = False):
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.fail_on_second = fail_on_second
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        if self.fail_on_second and len(self.calls) == 2:
            raise RuntimeError("insert failed")
        self.rowcount = 1


class RecordingConnection:
    def __init__(self, cursor):
        self.recording_cursor = cursor
        self.exited_with = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exited_with = exc_type
        return False

    def cursor(self):
        return self.recording_cursor


def sales_frame():
    return pd.DataFrame(
        [
            ["TX-1", date(2026, 1, 15), "C-1", "P-1", 1, Decimal("2.50"), "USD"],
            ["TX-2", date(2026, 1, 15), "C-2", "P-2", 2, Decimal("3.50"), "USD"],
        ],
        columns=("transaction_id", "sale_date", "customer_id", "product_id", "quantity", "unit_price", "currency"),
    )


def test_load_uses_parameterized_sql_and_reports_inserted_count():
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    repository = SalesRepository("unused", connection_factory=lambda: connection)

    assert repository.load_sales(sales_frame(), "sales.csv") == 2
    assert len(cursor.calls) == 2
    assert all("%s" in statement for statement, _ in cursor.calls)
    assert all("ON CONFLICT (transaction_id) DO NOTHING" in statement for statement, _ in cursor.calls)
    assert cursor.calls[0][1][0] == "TX-1"
    assert connection.exited_with is None


def test_load_failure_leaves_connection_context_to_roll_back_transaction():
    cursor = RecordingCursor(fail_on_second=True)
    connection = RecordingConnection(cursor)
    repository = SalesRepository("unused", connection_factory=lambda: connection)

    with pytest.raises(RuntimeError, match="insert failed"):
        repository.load_sales(sales_frame(), "sales.csv")

    assert connection.exited_with is RuntimeError

