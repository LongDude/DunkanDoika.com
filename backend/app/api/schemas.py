from __future__ import annotations

from datetime import date
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, model_validator

class PurchaseItem(BaseModel):
    date_in: date
    count: int = Field(ge=1, le=5000)
    # Exactly one of the following should be provided:
    expected_calving_date: Optional[date] = None
    days_pregnant: Optional[int] = Field(default=None, ge=0, le=280)

    @model_validator(mode="after")
    def _validate_exclusive(cls, v: "PurchaseItem"):
        a = v.expected_calving_date is not None
        b = v.days_pregnant is not None
        if a and b:
            raise ValueError("Provide either expected_calving_date or days_pregnant (not both)")
        if not a and not b:
            raise ValueError("Provide expected_calving_date or days_pregnant")
        return v

class ServicePeriodParams(BaseModel):
    mean_days: int = Field(default=115, ge=50, le=250)
    std_days: int = Field(default=10, ge=0, le=80)
    min_days_after_calving: int = Field(default=50, ge=0, le=120)

class HeiferInsemParams(BaseModel):
    min_age_days: int = Field(default=365, ge=250, le=700)
    max_age_days: int = Field(default=395, ge=250, le=800)

class CullingParams(BaseModel):
    # If true, estimate monthly culling hazards from the dataset (730-day window).
    estimate_from_dataset: bool = True
    grouping: Literal["lactation", "lactation_status", "age_band"] = "lactation"
    # Fallback constant monthly hazard if estimation disabled or insufficient data.
    fallback_monthly_hazard: float = Field(default=0.008, ge=0.0, le=0.2)
    age_band_years: int = Field(default=2, ge=1, le=10)

class ReplacementParams(BaseModel):
    enabled: bool = True
    annual_heifer_ratio: float = Field(default=0.30, ge=0.0, le=1.0)  # 30% of milking herd per year
    lookahead_months: int = Field(default=12, ge=3, le=36)

class ScenarioParams(BaseModel):
    dataset_id: str
    report_date: date
    horizon_months: int = Field(default=36, ge=1, le=120)
    future_date: Optional[date] = None
    seed: int = 42
    mc_runs: int = Field(default=1, ge=1, le=500)

    service_period: ServicePeriodParams = Field(default_factory=ServicePeriodParams)
    heifer_insem: HeiferInsemParams = Field(default_factory=HeiferInsemParams)
    culling: CullingParams = Field(default_factory=CullingParams)
    replacement: ReplacementParams = Field(default_factory=ReplacementParams)

    purchases: List[PurchaseItem] = Field(default_factory=list)

class DatasetUploadResponse(BaseModel):
    dataset_id: str
    n_rows: int
    report_date_suggested: Optional[date] = None
    status_counts: Dict[str, int]

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
    month: date  # first day of month
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
