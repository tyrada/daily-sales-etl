from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from daily_sales_etl.database import SalesRepository, apply_schema
from daily_sales_etl.generator import generate_sales
from daily_sales_etl.pipeline import run_pipeline


@pytest.mark.integration
def test_real_postgres_load_is_idempotent(tmp_path):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not set")

    schema_path = Path(__file__).parents[1] / "sql" / "init.sql"
    apply_schema(database_url, schema_path)
    source = tmp_path / "sales_20260115.csv"
    from datetime import date

    generate_sales(source, date(2026, 1, 15), rows=3, seed=42)
    repository = SalesRepository(database_url)

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sales WHERE transaction_id LIKE %s", ("TX-20260115-%",))

    first = run_pipeline(source, tmp_path / "quarantine", repository)
    second = run_pipeline(source, tmp_path / "quarantine", repository)

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM sales WHERE transaction_id LIKE %s", ("TX-20260115-%",))
            sales_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT loaded_count FROM etl_runs WHERE run_id IN (%s, %s) ORDER BY started_at",
                (first.run_id, second.run_id),
            )
            loaded_counts = [row[0] for row in cursor.fetchall()]

    assert sales_count == 3
    assert loaded_counts == [3, 0]
