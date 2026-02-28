from datetime import date

import pandas as pd

from app.api.schemas import ScenarioParams
from app.simulator.forecast import run_forecast
from app.simulator.loader import (
    COL_ANIMAL_ID,
    COL_BIRTH_DATE,
    COL_DAYS_IN_MILK,
    COL_LACTATION,
    COL_LACTATION_START,
    COL_STATUS,
)


def _params() -> ScenarioParams:
    return ScenarioParams.model_validate(
        {
            "dataset_id": "d1",
            "report_date": "2026-02-09",
            "horizon_months": 1,
            "future_date": None,
            "seed": 42,
            "mc_runs": 1,
            "service_period": {"mean_days": 115, "std_days": 10, "min_days_after_calving": 50},
            "heifer_insem": {"min_age_days": 365, "max_age_days": 395},
            "culling": {
                "estimate_from_dataset": False,
                "grouping": "lactation",
                "fallback_monthly_hazard": 0.0,
                "age_band_years": 2,
            },
            "replacement": {"enabled": False, "annual_heifer_ratio": 0.3, "lookahead_months": 12},
            "purchases": [],
        }
    )


def test_dim_mode_from_dataset_field_differs_from_calving() -> None:
    df = pd.DataFrame(
        [
            {
                COL_ANIMAL_ID: 1,
                COL_BIRTH_DATE: date(2023, 1, 1),
                COL_STATUS: "milking",
                COL_LACTATION: 1,
                COL_LACTATION_START: date(2025, 12, 1),
                COL_DAYS_IN_MILK: 200,
            }
        ]
    )
    params = _params()

    from_calving = run_forecast(df, params, dim_mode="from_calving")
    from_dataset = run_forecast(df, params, dim_mode="from_dataset_field")

    dim_calving = from_calving.series_p50.points[0].avg_days_in_milk
    dim_dataset = from_dataset.series_p50.points[0].avg_days_in_milk

    assert dim_calving is not None
    assert dim_dataset is not None
    assert dim_dataset > dim_calving
    assert from_dataset.meta is not None
    assert from_dataset.meta.dim_mode == "from_dataset_field"
