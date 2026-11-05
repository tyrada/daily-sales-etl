"""Orchestration for one auditable daily file run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from daily_sales_etl.database import SalesRepository
from daily_sales_etl.transform import InputError, read_sales_csv, transform_sales

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    run_id: UUID
    input_count: int
    loaded_count: int
    rejected_count: int
    quarantine_path: Path | None


def run_pipeline(input_path: Path, quarantine_dir: Path, repository: SalesRepository) -> RunResult:
    run_id = uuid4()
    started = monotonic()
    input_count = loaded_count = rejected_count = 0
    quarantine_path: Path | None = None

    LOGGER.info("run_started run_id=%s source_file=%s", run_id, input_path.name)
    repository.start_run(run_id, input_path.name)

    try:
        source = read_sales_csv(input_path)
        input_count = len(source)
        result = transform_sales(source)
        rejected_count = len(result.rejected)

        if rejected_count:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            quarantine_path = quarantine_dir / f"{input_path.stem}.{run_id}.rejected.csv"
            result.rejected.to_csv(quarantine_path, index=False)
            LOGGER.warning("records_quarantined run_id=%s count=%d path=%s", run_id, rejected_count, quarantine_path)

        loaded_count = repository.load_sales(result.valid, input_path.name)
        duration = monotonic() - started
        repository.finish_run(
            run_id,
            status="SUCCEEDED",
            duration_seconds=duration,
            input_count=input_count,
            loaded_count=loaded_count,
            rejected_count=rejected_count,
        )
        LOGGER.info(
            "run_succeeded run_id=%s input=%d loaded=%d rejected=%d duration_seconds=%.3f",
            run_id,
            input_count,
            loaded_count,
            rejected_count,
            duration,
        )
        return RunResult(run_id, input_count, loaded_count, rejected_count, quarantine_path)
    except Exception as exc:
        if isinstance(exc, InputError):
            input_count = exc.input_count
        duration = monotonic() - started
        try:
            repository.finish_run(
                run_id,
                status="FAILED",
                duration_seconds=duration,
                input_count=input_count,
                loaded_count=0,
                rejected_count=rejected_count,
                error_message=str(exc)[:2000],
            )
        except Exception:
            LOGGER.exception("audit_update_failed run_id=%s", run_id)
        LOGGER.exception("run_failed run_id=%s duration_seconds=%.3f", run_id, duration)
        raise

