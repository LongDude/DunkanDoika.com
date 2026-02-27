from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.schemas import ForecastJobStatus, ScenarioParams
from app.db.models import ForecastJobModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ForecastJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, params: ScenarioParams, scenario_id: Optional[str] = None, expires_in_days: int = 30) -> ForecastJobModel:
        queued_at = now_utc()
        job = ForecastJobModel(
            dataset_id=params.dataset_id,
            scenario_id=scenario_id,
            params_json=params.model_dump(mode="json"),
            status=ForecastJobStatus.QUEUED.value,
            progress_pct=0,
            completed_runs=0,
            total_runs=params.mc_runs,
            queued_at=queued_at,
            expires_at=queued_at + timedelta(days=expires_in_days),
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get(self, job_id: str) -> ForecastJobModel | None:
        return self.session.get(ForecastJobModel, job_id)

    def mark_running(self, job_id: str, progress_pct: int = 10, total_runs: int | None = None) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = ForecastJobStatus.RUNNING.value
        job.progress_pct = progress_pct
        job.completed_runs = 0
        if total_runs is not None:
            job.total_runs = max(0, total_runs)
        job.started_at = now_utc()
        self.session.commit()
        self.session.refresh(job)
        return job

    def update_progress(
        self,
        job_id: str,
        progress_pct: int,
        completed_runs: int | None = None,
        total_runs: int | None = None,
    ) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.progress_pct = max(0, min(100, progress_pct))
        if completed_runs is not None:
            job.completed_runs = max(0, completed_runs)
        if total_runs is not None:
            job.total_runs = max(0, total_runs)
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_failed(self, job_id: str, message: str) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = ForecastJobStatus.FAILED.value
        job.error_message = message
        job.finished_at = now_utc()
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_succeeded(
        self,
        job_id: str,
        result_object_key: str,
        csv_object_key: str,
        xlsx_object_key: str,
    ) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = ForecastJobStatus.SUCCEEDED.value
        job.progress_pct = 100
        job.completed_runs = max(job.completed_runs, job.total_runs)
        job.error_message = None
        job.result_object_key = result_object_key
        job.csv_object_key = csv_object_key
        job.xlsx_object_key = xlsx_object_key
        job.finished_at = now_utc()
        self.session.commit()
        self.session.refresh(job)
        return job

    def find_stuck_running(self, timeout_minutes: int) -> Iterable[ForecastJobModel]:
        threshold = now_utc() - timedelta(minutes=timeout_minutes)
        stmt = select(ForecastJobModel).where(
            and_(
                ForecastJobModel.status == ForecastJobStatus.RUNNING.value,
                ForecastJobModel.started_at.is_not(None),
                ForecastJobModel.started_at < threshold,
            )
        )
        return self.session.scalars(stmt).all()

    def requeue(self, job_id: str) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = ForecastJobStatus.QUEUED.value
        job.progress_pct = 0
        job.completed_runs = 0
        job.total_runs = int(job.params_json.get("mc_runs", 0)) if isinstance(job.params_json, dict) else 0
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        self.session.commit()
        self.session.refresh(job)
        return job
