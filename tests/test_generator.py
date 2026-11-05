from datetime import date

from daily_sales_etl.generator import generate_sales


def test_generator_is_reproducible(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    generate_sales(first, date(2026, 1, 15), rows=5, seed=42)
    generate_sales(second, date(2026, 1, 15), rows=5, seed=42)

    assert first.read_bytes() == second.read_bytes()
    assert b"TX-20260115-000001" in first.read_bytes()

