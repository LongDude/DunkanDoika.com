from __future__ import annotations

from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class DatasetModel(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    report_date_suggested: Mapped[date | None] = mapped_column(Date, nullable=True)
    status_counts_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)

    scenarios: Mapped[list["ScenarioModel"]] = relationship(back_populates="dataset", cascade="all,delete")
    forecast_jobs: Mapped[list["ForecastJobModel"]] = relationship(back_populates="dataset")

    __table_args__ = (Index("ix_datasets_created_at", "created_at"),)


class ScenarioModel(Base):
    __tablename__ = "scenarios"

    scenario_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)

    dataset: Mapped[DatasetModel] = relationship(back_populates="scenarios")
    forecast_jobs: Mapped[list["ForecastJobModel"]] = relationship(back_populates="scenario")

    __table_args__ = (Index("ix_scenarios_dataset_created", "dataset_id", "created_at"),)


class ForecastJobModel(Base):
    __tablename__ = "forecast_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.scenario_id", ondelete="SET NULL"), nullable=True)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_object_key: Mapped[str | None] = mapped_column(String(50000), nullable=True)
    csv_object_key: Mapped[str | None] = mapped_column(String(50000), nullable=True)
    xlsx_object_key: Mapped[str | None] = mapped_column(String(50000), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped[DatasetModel] = relationship(back_populates="forecast_jobs")
    scenario: Mapped[ScenarioModel | None] = relationship(back_populates="forecast_jobs")

    __table_args__ = (Index("ix_forecast_jobs_status_queued", "status", "queued_at"),)
