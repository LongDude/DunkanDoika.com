from __future__ import annotations

import io
import json
from math import floor
import time
from typing import Callable, TypeVar

from minio.error import S3Error

from app.api.schemas import ForecastJobStatus, ForecastResult, ScenarioParams
from app.core.config import settings
from app.db.session import SessionLocal
from app.live.events import publish_job_event
from app.repositories.datasets import DatasetRepository
from app.repositories.forecast_jobs import ForecastJobRepository
from app.simulator.exporter import export_forecast_csv, export_forecast_xlsx
from app.simulator.forecast import run_forecast
from app.simulator.loader import load_dataset_df
from app.storage.object_storage import storage_client

T = TypeVar("T")


def _retry(op: Callable[[], T], retries: int = 3, base_delay: float = 0.5) -> T:
    for attempt in range(retries):
        try:
            return op()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError("unreachable")


def run_forecast_job(forecast_job_id: str) -> None:
    session = SessionLocal()
    try:
        jobs = ForecastJobRepository(session)
        datasets = DatasetRepository(session)

        existing = jobs.get(forecast_job_id)
        if existing is None:
            return
        if existing.status in {ForecastJobStatus.SUCCEEDED.value, ForecastJobStatus.FAILED.value}:
            return

        params = ScenarioParams.model_validate(existing.params_json)
        total_runs = params.mc_runs
        job_row = jobs.mark_running(forecast_job_id, progress_pct=10, total_runs=total_runs)
        if job_row is not None:
            publish_job_event(
                forecast_job_id,
                {
                    "type": "job_progress",
                    "status": job_row.status,
                    "progress_pct": job_row.progress_pct,
                    "completed_runs": job_row.completed_runs,
                    "total_runs": job_row.total_runs,
                    "partial_result": None,
                    "error_message": None,
                },
            )

        dataset_row = datasets.get(params.dataset_id)
        if dataset_row is None:
            failed = jobs.mark_failed(forecast_job_id, "DATASET_NOT_FOUND: dataset metadata missing")
            if failed is not None:
                publish_job_event(
                    forecast_job_id,
                    {
                        "type": "job_failed",
                        "status": failed.status,
                        "progress_pct": failed.progress_pct,
                        "completed_runs": failed.completed_runs,
                        "total_runs": failed.total_runs,
                        "partial_result": None,
                        "error_message": failed.error_message,
                    },
                )
            return

        try:
            csv_bytes = _retry(
                lambda: storage_client.get_bytes(storage_client.datasets_bucket, dataset_row.object_key)
            )
        except S3Error:
            failed = jobs.mark_failed(forecast_job_id, "DATASET_OBJECT_MISSING: dataset object missing in storage")
            if failed is not None:
                publish_job_event(
                    forecast_job_id,
                    {
                        "type": "job_failed",
                        "status": failed.status,
                        "progress_pct": failed.progress_pct,
                        "completed_runs": failed.completed_runs,
                        "total_runs": failed.total_runs,
                        "partial_result": None,
                        "error_message": failed.error_message,
                    },
                )
            return

        df = load_dataset_df(io.BytesIO(csv_bytes))

        def on_progress(completed_runs: int, all_runs: int, partial_result: ForecastResult) -> None:
            progress = 10 + floor(80 * completed_runs / max(1, all_runs))
            progress = min(progress, 90)
            updated = jobs.update_progress(
                forecast_job_id,
                progress_pct=progress,
                completed_runs=completed_runs,
                total_runs=all_runs,
            )
            if updated is None:
                return
            publish_job_event(
                forecast_job_id,
                {
                    "type": "job_progress",
                    "status": updated.status,
                    "progress_pct": updated.progress_pct,
                    "completed_runs": updated.completed_runs,
                    "total_runs": updated.total_runs,
                    "partial_result": partial_result.model_dump(mode="json"),
                    "error_message": None,
                },
            )

        result = run_forecast(
            df,
            params,
            parallel_enabled=settings.mc_parallel_enabled,
            max_processes=settings.mc_max_processes,
            batch_size=settings.mc_batch_size,
            progress_callback=on_progress,
        )

        result_key = f"results/{forecast_job_id}.json"
        csv_key = f"exports/{forecast_job_id}.csv"
        xlsx_key = f"exports/{forecast_job_id}.xlsx"

        result_bytes = json.dumps(result.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        csv_export = export_forecast_csv(result).encode("utf-8")
        xlsx_export = export_forecast_xlsx(result)

        _retry(lambda: storage_client.put_bytes(storage_client.results_bucket, result_key, result_bytes, "application/json"))
        _retry(lambda: storage_client.put_bytes(storage_client.exports_bucket, csv_key, csv_export, "text/csv"))
        _retry(
            lambda: storage_client.put_bytes(
                storage_client.exports_bucket,
                xlsx_key,
                xlsx_export,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )

        jobs.mark_succeeded(
            forecast_job_id,
            result_object_key=result_key,
            csv_object_key=csv_key,
            xlsx_object_key=xlsx_key,
        )
        done = jobs.get(forecast_job_id)
        if done is not None:
            publish_job_event(
                forecast_job_id,
                {
                    "type": "job_succeeded",
                    "status": done.status,
                    "progress_pct": done.progress_pct,
                    "completed_runs": done.completed_runs,
                    "total_runs": done.total_runs,
                    "partial_result": result.model_dump(mode="json"),
                    "error_message": None,
                },
            )
    except Exception as exc:
        failed = ForecastJobRepository(session).mark_failed(forecast_job_id, f"INTERNAL_ERROR: {exc}")
        if failed is not None:
            publish_job_event(
                forecast_job_id,
                {
                    "type": "job_failed",
                    "status": failed.status,
                    "progress_pct": failed.progress_pct,
                    "completed_runs": failed.completed_runs,
                    "total_runs": failed.total_runs,
                    "partial_result": None,
                    "error_message": failed.error_message,
                },
            )
    finally:
        session.close()


def requeue_stuck_jobs(timeout_minutes: int) -> list[str]:
    session = SessionLocal()
    try:
        jobs = ForecastJobRepository(session)
        stuck = list(jobs.find_stuck_running(timeout_minutes))
        requeued: list[str] = []
        for item in stuck:
            jobs.requeue(item.job_id)
            requeued.append(item.job_id)
        return requeued
    finally:
        session.close()


def read_job_result(job_id: str) -> ForecastResult:
    session = SessionLocal()
    try:
        jobs = ForecastJobRepository(session)
        job = jobs.get(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        if job.status != ForecastJobStatus.SUCCEEDED.value or not job.result_object_key:
            raise RuntimeError("JOB_NOT_READY")
        payload = storage_client.get_bytes(storage_client.results_bucket, job.result_object_key)
        return ForecastResult.model_validate_json(payload)
    finally:
        session.close()
