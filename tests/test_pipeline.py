from __future__ import annotations

import csv
from pathlib import Path

import pytest

from daily_sales_etl.pipeline import run_pipeline
from daily_sales_etl.transform import InputError

FIELDS = (
    "transaction_id",
    "transaction_date",
    "customer_id",
    "product_id",
    "quantity",
    "unit_price",
    "currency",
)


class MemoryRepository:
    def __init__(self, fail_load: bool = False):
        self.sales: dict[str, tuple[object, ...]] = {}
        self.audits: dict[object, dict[str, object]] = {}
        self.fail_load = fail_load

    def start_run(self, run_id, source_file):
        self.audits[run_id] = {"source_file": source_file, "status": "RUNNING"}

    def load_sales(self, frame, source_file):
        if self.fail_load:
            raise RuntimeError("simulated database failure")
        loaded = 0
        for row in frame.itertuples(index=False):
            if row.transaction_id not in self.sales:
                self.sales[row.transaction_id] = (*row, source_file)
                loaded += 1
        return loaded

    def finish_run(self, run_id, **values):
        self.audits[run_id].update(values)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def valid_rows() -> list[dict[str, str]]:
    return [
        {
            "transaction_id": transaction_id,
            "transaction_date": "2026-01-15",
            "customer_id": "C-1",
            "product_id": "P-1",
            "quantity": "2",
            "unit_price": "10.00",
            "currency": "USD",
        }
        for transaction_id in ("TX-1", "TX-2")
    ]


def test_successful_load_and_repeated_run_are_idempotent(tmp_path):
    source = tmp_path / "sales.csv"
    write_csv(source, valid_rows())
    repository = MemoryRepository()

    first = run_pipeline(source, tmp_path / "quarantine", repository)
    second = run_pipeline(source, tmp_path / "quarantine", repository)

    assert (first.input_count, first.loaded_count, first.rejected_count) == (2, 2, 0)
    assert (second.input_count, second.loaded_count, second.rejected_count) == (2, 0, 0)
    assert len(repository.sales) == 2
    assert repository.audits[first.run_id]["status"] == "SUCCEEDED"
    assert repository.audits[second.run_id]["status"] == "SUCCEEDED"


def test_invalid_rows_are_written_to_quarantine(tmp_path):
    source = tmp_path / "sales.csv"
    rows = valid_rows()
    rows[1]["quantity"] = "not-a-number"
    write_csv(source, rows)

    result = run_pipeline(source, tmp_path / "quarantine", MemoryRepository())

    assert (result.loaded_count, result.rejected_count) == (1, 1)
    assert result.quarantine_path is not None
    assert "quantity must be a positive integer" in result.quarantine_path.read_text(encoding="utf-8")


def test_malformed_input_records_failed_audit(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("transaction_id,quantity\nTX-1,1\n", encoding="utf-8")
    repository = MemoryRepository()

    with pytest.raises(InputError):
        run_pipeline(source, tmp_path / "quarantine", repository)

    audit = next(iter(repository.audits.values()))
    assert audit["status"] == "FAILED"
    assert audit["input_count"] == 1
    assert "missing required columns" in audit["error_message"]


def test_failed_load_records_failed_audit_and_no_sales(tmp_path):
    source = tmp_path / "sales.csv"
    write_csv(source, valid_rows())
    repository = MemoryRepository(fail_load=True)

    with pytest.raises(RuntimeError, match="simulated database failure"):
        run_pipeline(source, tmp_path / "quarantine", repository)

    audit = next(iter(repository.audits.values()))
    assert audit["status"] == "FAILED"
    assert audit["loaded_count"] == 0
    assert not repository.sales

