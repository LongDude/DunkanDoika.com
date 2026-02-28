from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import ForecastJobStatus, ScenarioParams
from app.db.models import ForecastJobModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ForecastJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        params: ScenarioParams,
        scenario_id: Optional[str] = None,
        expires_in_days: int = 30,
        owner_user_id: str | None = None,
    ) -> ForecastJobModel:
        queued_at = now_utc()
        job = ForecastJobModel(
            owner_user_id=owner_user_id,
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

    def get(self, job_id: str, include_deleted: bool = False) -> ForecastJobModel | None:
        stmt = select(ForecastJobModel).where(ForecastJobModel.job_id == job_id)
        if not include_deleted:
            stmt = stmt.where(ForecastJobModel.deleted_at.is_(None))
        return self.session.scalar(stmt)

    def get_for_owner(self, job_id: str, owner_user_id: str) -> ForecastJobModel | None:
        stmt = (
            select(ForecastJobModel)
            .where(ForecastJobModel.job_id == job_id)
            .where(ForecastJobModel.owner_user_id == owner_user_id)
            .where(ForecastJobModel.deleted_at.is_(None))
        )
        return self.session.scalar(stmt)

    def list_for_owner(
        self,
        owner_user_id: str,
        *,
        status: str | None = None,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ForecastJobModel], int]:
        base = (
            select(ForecastJobModel)
            .where(ForecastJobModel.owner_user_id == owner_user_id)
            .where(ForecastJobModel.deleted_at.is_(None))
        )
        if status:
            base = base.where(ForecastJobModel.status == status)
        if q:
            term = f"%{q}%"
            base = base.where(
                or_(
                    ForecastJobModel.job_id.ilike(term),
                    ForecastJobModel.dataset_id.ilike(term),
                    ForecastJobModel.scenario_id.ilike(term),
                )
            )
        if date_from is not None:
            base = base.where(ForecastJobModel.queued_at >= date_from)
        if date_to is not None:
            base = base.where(ForecastJobModel.queued_at <= date_to)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = int(self.session.scalar(total_stmt) or 0)

        safe_page = max(1, page)
        safe_limit = max(1, min(100, limit))
        stmt = (
            base.order_by(desc(ForecastJobModel.queued_at))
            .offset((safe_page - 1) * safe_limit)
            .limit(safe_limit)
        )
        return list(self.session.scalars(stmt).all()), total

    def mark_running(self, job_id: str, progress_pct: int = 10, total_runs: int | None = None) -> ForecastJobModel | None:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in {ForecastJobStatus.SUCCEEDED.value, ForecastJobStatus.FAILED.value, ForecastJobStatus.CANCELED.value}:
            return job
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
        if job.status != ForecastJobStatus.RUNNING.value:
            return job
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
        if job.status in {ForecastJobStatus.SUCCEEDED.value, ForecastJobStatus.FAILED.value, ForecastJobStatus.CANCELED.value}:
            return job
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
        if job.status in {ForecastJobStatus.SUCCEEDED.value, ForecastJobStatus.FAILED.value, ForecastJobStatus.CANCELED.value}:
            return job
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
                ForecastJobModel.deleted_at.is_(None),
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

    def soft_delete_for_owner(self, job_id: str, owner_user_id: str) -> ForecastJobModel | None:
        job = self.get_for_owner(job_id, owner_user_id)
        if job is None:
            return None
        job.deleted_at = now_utc()
        self.session.commit()
        self.session.refresh(job)
        return job

    def bulk_soft_delete_for_owner(self, ids: Sequence[str], owner_user_id: str) -> tuple[list[str], list[str]]:
        deleted_ids: list[str] = []
        missing_ids: list[str] = []
        for job_id in ids:
            deleted = self.soft_delete_for_owner(job_id, owner_user_id)
            if deleted is None:
                missing_ids.append(job_id)
            else:
                deleted_ids.append(job_id)
        return deleted_ids, missing_ids
