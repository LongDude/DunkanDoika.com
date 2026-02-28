from datetime import date

import pytest

from app.api.schemas import PurchaseItem, ScenarioParams


def test_purchase_item_empty_strings_are_normalized() -> None:
    item = PurchaseItem.model_validate(
        {
            "date_in": "2026-02-20",
            "count": 10,
            "expected_calving_date": "",
            "days_pregnant": "150",
        }
    )
    assert item.expected_calving_date is None
    assert item.days_pregnant == 150


def test_purchase_item_mutually_exclusive_fields() -> None:
    with pytest.raises(ValueError):
        PurchaseItem.model_validate(
            {
                "date_in": "2026-02-20",
                "count": 10,
                "expected_calving_date": "2026-11-20",
                "days_pregnant": 100,
            }
        )


def test_scenario_params_empty_future_date_normalized_to_none() -> None:
    params = ScenarioParams.model_validate(
        {
            "dataset_id": "d1",
            "report_date": "2026-02-20",
            "future_date": "",
            "horizon_months": 12,
            "seed": 42,
            "mc_runs": 1,
            "service_period": {"mean_days": 115, "std_days": 10, "min_days_after_calving": 50},
            "heifer_insem": {"min_age_days": 365, "max_age_days": 395},
            "culling": {
                "estimate_from_dataset": True,
                "grouping": "lactation",
                "fallback_monthly_hazard": 0.008,
                "age_band_years": 2,
            },
            "replacement": {"enabled": True, "annual_heifer_ratio": 0.3, "lookahead_months": 12},
            "purchases": [],
        }
    )
    assert params.future_date is None
    assert params.report_date == date(2026, 2, 20)


def test_scenario_params_accepts_dim_mode_override() -> None:
    params = ScenarioParams.model_validate(
        {
            "dataset_id": "d1",
            "report_date": "2026-02-20",
            "future_date": None,
            "dim_mode": "from_dataset_field",
            "horizon_months": 12,
            "seed": 42,
            "mc_runs": 1,
            "service_period": {"mean_days": 115, "std_days": 10, "min_days_after_calving": 50},
            "heifer_insem": {"min_age_days": 365, "max_age_days": 395},
            "culling": {
                "estimate_from_dataset": True,
                "grouping": "lactation",
                "fallback_monthly_hazard": 0.008,
                "age_band_years": 2,
            },
            "replacement": {"enabled": True, "annual_heifer_ratio": 0.3, "lookahead_months": 12},
            "purchases": [],
        }
    )
    assert params.dim_mode == "from_dataset_field"
