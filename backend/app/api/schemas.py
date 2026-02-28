from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PurchaseItem(BaseModel):
    date_in: date
    count: int = Field(ge=1, le=5000)
    expected_calving_date: Optional[date] = None
    days_pregnant: Optional[int] = Field(default=None, ge=0, le=280)

    @field_validator("expected_calving_date", mode="before")
    @classmethod
    def empty_expected_calving_date_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("days_pregnant", mode="before")
    @classmethod
    def empty_days_pregnant_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_exclusive(self) -> "PurchaseItem":
        has_expected = self.expected_calving_date is not None
        has_days = self.days_pregnant is not None
        if has_expected and has_days:
            raise ValueError("Provide either expected_calving_date or days_pregnant (not both)")
        if not has_expected and not has_days:
            raise ValueError("Provide expected_calving_date or days_pregnant")
        return self


class ServicePeriodParams(BaseModel):
    mean_days: int = Field(default=115, ge=50, le=250)
    std_days: int = Field(default=10, ge=0, le=80)
    min_days_after_calving: int = Field(default=50, ge=0, le=120)


class HeiferInsemParams(BaseModel):
    min_age_days: int = Field(default=365, ge=250, le=700)
    max_age_days: int = Field(default=395, ge=250, le=800)


class CullingParams(BaseModel):
    estimate_from_dataset: bool = True
    grouping: Literal["lactation", "lactation_status", "age_band"] = "lactation"
    fallback_monthly_hazard: float = Field(default=0.008, ge=0.0, le=0.2)
    age_band_years: int = Field(default=2, ge=1, le=10)


class ReplacementParams(BaseModel):
    enabled: bool = True
    annual_heifer_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    lookahead_months: int = Field(default=12, ge=3, le=36)


class ScenarioParams(BaseModel):
    dataset_id: str
    report_date: date
    horizon_months: int = Field(default=36, ge=1, le=120)
    future_date: Optional[date] = None
    seed: int = 42
    mc_runs: int = Field(default=1, ge=1, le=50000)
    service_period: ServicePeriodParams = Field(default_factory=ServicePeriodParams)
    heifer_insem: HeiferInsemParams = Field(default_factory=HeiferInsemParams)
    culling: CullingParams = Field(default_factory=CullingParams)
    replacement: ReplacementParams = Field(default_factory=ReplacementParams)
    purchases: List[PurchaseItem] = Field(default_factory=list)

    @field_validator("future_date", mode="before")
    @classmethod
    def empty_future_date_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    n_rows: int
    report_date_suggested: Optional[date] = None
    status_counts: Dict[str, int]


class DatasetInfo(DatasetUploadResponse):
    original_filename: str
    created_at: datetime


class ForecastPoint(BaseModel):
    date: date
    milking_count: int
    dry_count: int
    heifer_count: int
    pregnant_heifer_count: int
    avg_days_in_milk: Optional[float] = None


class ForecastSeries(BaseModel):
    points: List[ForecastPoint]


class EventsByMonth(BaseModel):
    month: date
    calvings: int = 0
    dryoffs: int = 0
    culls: int = 0
    purchases_in: int = 0
    heifer_intros: int = 0


class ForecastResult(BaseModel):
    series_p50: ForecastSeries
    series_p10: Optional[ForecastSeries] = None
    series_p90: Optional[ForecastSeries] = None
    events: List[EventsByMonth]
    future_point: Optional[ForecastPoint] = None


class ScenarioCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: ScenarioParams


class ScenarioInfo(BaseModel):
    scenario_id: str
    name: str
    created_at: str
    dataset_id: str
    report_date: date
    horizon_months: int


class ScenarioDetail(BaseModel):
    scenario_id: str
    name: str
    created_at: str
    params: ScenarioParams


class ForecastJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class ForecastJobInfo(BaseModel):
    job_id: str
    dataset_id: str
    scenario_id: Optional[str] = None
    status: ForecastJobStatus
    progress_pct: int = Field(ge=0, le=100)
    completed_runs: int = Field(ge=0, default=0)
    total_runs: int = Field(ge=0, default=0)
    error_message: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class CreateForecastJobResponse(BaseModel):
    job: ForecastJobInfo


class JobProgressSnapshot(BaseModel):
    status: ForecastJobStatus
    progress_pct: int = Field(ge=0, le=100)


class ApiError(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None
