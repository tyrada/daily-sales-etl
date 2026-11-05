"""PostgreSQL access with parameterized statements and explicit transactions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import psycopg

ConnectionFactory = Callable[[], Any]


class SalesRepository:
    """Persist sales and audit events using short, independent transactions."""

    def __init__(self, database_url: str, connection_factory: ConnectionFactory | None = None):
        self._connect = connection_factory or (lambda: psycopg.connect(database_url))

    def start_run(self, run_id: UUID, source_file: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO etl_runs (run_id, source_file, status)
                    VALUES (%s, %s, 'RUNNING')
                    """,
                    (run_id, source_file),
                )

    def load_sales(self, frame: pd.DataFrame, source_file: str) -> int:
        """Load all rows atomically and return the number newly inserted."""
        records = [
            (
                row.transaction_id,
                row.sale_date,
                row.customer_id,
                row.product_id,
                row.quantity,
                row.unit_price,
                row.currency,
                source_file,
            )
            for row in frame.itertuples(index=False)
        ]
        if not records:
            return 0

        with self._connect() as connection:
            with connection.cursor() as cursor:
                inserted = 0
                for record in records:
                    cursor.execute(
                        """
                        INSERT INTO sales (
                            transaction_id, sale_date, customer_id, product_id,
                            quantity, unit_price, currency, source_file
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (transaction_id) DO NOTHING
                        """,
                        record,
                    )
                    inserted += cursor.rowcount
                return inserted

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        duration_seconds: float,
        input_count: int,
        loaded_count: int,
        rejected_count: int,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE etl_runs
                    SET status = %s,
                        finished_at = CURRENT_TIMESTAMP,
                        duration_seconds = %s,
                        input_count = %s,
                        loaded_count = %s,
                        rejected_count = %s,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        duration_seconds,
                        input_count,
                        loaded_count,
                        rejected_count,
                        error_message,
                        run_id,
                    ),
                )


def apply_schema(database_url: str, schema_path: Path) -> None:
    """Apply the idempotent schema file in one transaction."""
    statements = [statement.strip() for statement in schema_path.read_text(encoding="utf-8").split(";") if statement.strip()]
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

