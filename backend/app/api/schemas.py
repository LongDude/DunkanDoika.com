from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SchemaVersion = Literal["legacy_v1", "herd_m5_v2"]
ScenarioMode = Literal["empirical", "theoretical"]
PurchasePolicy = Literal["manual", "auto_counter", "auto_forecast"]


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


class HerdM5ModelParams(BaseModel):
    min_first_insem_age_days: int = Field(default=365, ge=250, le=800)
    voluntary_waiting_period: int = Field(default=50, ge=0, le=200)
    max_service_period_after_vwp: int = Field(default=300, ge=50, le=600)
    population_regulation: float = Field(default=0.5, ge=0.0, le=1.0)

    gestation_lo: int = Field(default=275, ge=240, le=320)
    gestation_hi: int = Field(default=280, ge=240, le=330)
    gestation_mu: float = Field(default=277.5, ge=240.0, le=320.0)
    gestation_sigma: float = Field(default=2.0, ge=0.1, le=20.0)

    heifer_birth_prob: float = Field(default=0.5, ge=0.0, le=1.0)

    purchased_days_to_calving_lo: int = Field(default=1, ge=1, le=280)
    purchased_days_to_calving_hi: int = Field(default=280, ge=1, le=330)

    @model_validator(mode="after")
    def validate_bounds(self) -> "HerdM5ModelParams":
        if self.gestation_hi < self.gestation_lo:
            raise ValueError("gestation_hi must be >= gestation_lo")
        if self.purchased_days_to_calving_hi < self.purchased_days_to_calving_lo:
            raise ValueError("purchased_days_to_calving_hi must be >= purchased_days_to_calving_lo")
        return self


class ScenarioParams(BaseModel):
    dataset_id: str
    report_date: Optional[date] = None
    horizon_months: int = Field(default=36, ge=1, le=120)
    future_date: Optional[date] = None
    seed: int = 42
    mc_runs: int = Field(default=50, ge=1, le=50000)

    mode: ScenarioMode = "empirical"
    purchase_policy: PurchasePolicy = "manual"
    lead_time_days: int = Field(default=90, ge=1, le=365)
    confidence_central: float = Field(default=0.90, ge=0.50, le=0.99)

    model: HerdM5ModelParams = Field(default_factory=HerdM5ModelParams)
    purchases: List[PurchaseItem] = Field(default_factory=list)

    @field_validator("future_date", mode="before")
    @classmethod
    def empty_future_date_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "ScenarioParams":
        if self.purchase_policy != "manual" and len(self.purchases) > 0:
            raise ValueError("purchases are supported only when purchase_policy='manual'")
        if self.future_date is not None and self.future_date.day != 1:
            raise ValueError("future_date must be the first day of month")
        return self


class DatasetQualityIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    row_count: Optional[int] = None
    sample_rows: Optional[List[int]] = None


class ForecastResultMeta(BaseModel):
    engine: Literal["herd_m5"] = "herd_m5"
    mode: ScenarioMode
    purchase_policy: PurchasePolicy
    confidence_central: float
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    simulation_version: str


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    n_rows: int
    report_date_suggested: Optional[date] = None
    status_counts: Dict[str, int]
    quality_issues: List[DatasetQualityIssue] = Field(default_factory=list)


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
    meta: Optional[ForecastResultMeta] = None


class ScenarioCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: ScenarioParams


class ScenarioInfo(BaseModel):
    scenario_id: str
    name: str
    created_at: str
    dataset_id: str
    report_date: Optional[date] = None
    horizon_months: Optional[int] = None
    schema_version: SchemaVersion
    is_legacy: bool
    legacy_reason: Optional[str] = None


class ScenarioDetail(BaseModel):
    scenario_id: str
    name: str
    created_at: str
    schema_version: SchemaVersion
    is_legacy: bool
    legacy_reason: Optional[str] = None
    params: Optional[ScenarioParams] = None


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


class HistoryJobListItem(ForecastJobInfo):
    has_result: bool = False


class HistoryJobDetail(HistoryJobListItem):
    params: ScenarioParams


class HistoryJobsPageResponse(BaseModel):
    items: list[HistoryJobListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=100)


class BulkDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class BulkDeleteSkipItem(BaseModel):
    id: str
    reason: str


class BulkDeleteResponse(BaseModel):
    deleted_ids: list[str] = Field(default_factory=list)
    skipped: list[BulkDeleteSkipItem] = Field(default_factory=list)


class UserPresetParams(BaseModel):
    report_date: Optional[date] = None
    horizon_months: int = Field(default=36, ge=1, le=120)
    future_date: Optional[date] = None
    seed: int = 42
    mc_runs: int = Field(default=50, ge=1, le=50000)

    mode: ScenarioMode = "empirical"
    purchase_policy: PurchasePolicy = "manual"
    lead_time_days: int = Field(default=90, ge=1, le=365)
    confidence_central: float = Field(default=0.90, ge=0.50, le=0.99)

    model: HerdM5ModelParams = Field(default_factory=HerdM5ModelParams)
    purchases: List[PurchaseItem] = Field(default_factory=list)

    @field_validator("future_date", mode="before")
    @classmethod
    def empty_future_date_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "UserPresetParams":
        if self.purchase_policy != "manual" and len(self.purchases) > 0:
            raise ValueError("purchases are supported only when purchase_policy='manual'")
        if self.future_date is not None and self.future_date.day != 1:
            raise ValueError("future_date must be the first day of month")
        return self


class UserPresetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: UserPresetParams


class UserPresetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    params: Optional[UserPresetParams] = None

    @model_validator(mode="after")
    def validate_any_payload(self) -> "UserPresetUpdateRequest":
        if self.name is None and self.params is None:
            raise ValueError("Provide at least one field to update")
        return self


class UserPresetResponse(BaseModel):
    preset_id: str
    owner_user_id: str
    name: str
    schema_version: SchemaVersion
    is_legacy: bool
    legacy_reason: Optional[str] = None
    params: Optional[UserPresetParams] = None
    created_at: datetime
    updated_at: datetime
