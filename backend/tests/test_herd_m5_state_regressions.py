from __future__ import annotations

from datetime import date, timedelta

from app.simulator.herd_m5 import simulation as simulation_module
from app.simulator.herd_m5.cows_with_death import Cow
from app.simulator.herd_m5.purchase import ManualPurchasePolicy
from app.simulator.herd_m5.samplers import EmpiricalDiscreteSampler
from app.simulator.herd_m5.simulation import ModelConfig, Simulation
from app.simulator.forecast_herd_m5 import (
    _apply_initial_dim_limit,
    _build_manual_purchase_plan,
    _initial_snapshot,
    _run_seed_job,
)
from app.api.schemas import ScenarioParams


def _config(
    *,
    ages: list[int] | None = None,
    service_periods: list[int] | None = None,
    days_to_dry: list[int] | None = None,
) -> ModelConfig:
    return ModelConfig(
        age_first_insem_days=EmpiricalDiscreteSampler(ages or [400]),
        service_period_days=EmpiricalDiscreteSampler(service_periods or [120]),
        conception_to_dry_days=EmpiricalDiscreteSampler(days_to_dry or [220]),
        gestation_lo=280,
        gestation_hi=280,
        gestation_mu=280,
        gestation_sigma=0.1,
        heifer_birth_prob=0.0,
        population_regulation=0.0,
        max_days_in_milk=350,
    )


def _simulation(monkeypatch, cows: list[Cow], cfg: ModelConfig, start: date, seed: int = 42) -> Simulation:
    monkeypatch.setattr(simulation_module, "cull_cow_combined", lambda *_args, **_kwargs: False)
    return Simulation(
        initial_cows=cows,
        cfg=cfg,
        start_date=start,
        file_path="unused.csv",
        purchase_policy=ManualPurchasePolicy(plan={}),
        random_seed=seed,
    )


def test_pregnant_cow_without_plans_derives_dates_from_conception(monkeypatch) -> None:
    conception = date(2025, 1, 1)
    cow = Cow(
        id="cow",
        birth_date=date(2022, 1, 1),
        status="pregnant",
        lactation_number=1,
        last_calving_date=date(2024, 11, 1),
        conception_date=conception,
        days_in_milk=181,
    )
    sim = _simulation(monkeypatch, [cow], _config(), date(2025, 5, 1))

    sim.step_day()

    assert cow.planned_dry_date == conception + timedelta(days=220)
    assert cow.planned_calving_date == conception + timedelta(days=280)
    assert cow.status == "pregnant"


def test_pregnant_heifer_and_dry_cow_recover_missing_calving_plan(monkeypatch) -> None:
    conception = date(2025, 1, 1)
    heifer = Cow(
        id="heifer",
        birth_date=date(2023, 10, 1),
        status="pregnant_heifer",
        conception_date=conception,
    )
    dry = Cow(
        id="dry",
        birth_date=date(2021, 1, 1),
        status="dry",
        lactation_number=2,
        last_calving_date=date(2024, 9, 1),
        conception_date=conception,
        dry_date=date(2025, 7, 1),
    )
    sim = _simulation(monkeypatch, [heifer, dry], _config(), date(2025, 7, 2))

    sim.step_day()

    expected = conception + timedelta(days=280)
    assert heifer.planned_calving_date == expected
    assert dry.planned_calving_date == expected


def test_calving_clears_conception_plan_from_previous_lactation(monkeypatch) -> None:
    start = date(2025, 8, 1)
    cow = Cow(
        id="calving",
        birth_date=date(2021, 1, 1),
        status="pregnant",
        lactation_number=2,
        last_calving_date=date(2024, 10, 1),
        conception_date=start - timedelta(days=280),
        planned_conception_date=start - timedelta(days=280),
        planned_calving_date=start,
        days_in_milk=304,
    )
    sim = _simulation(monkeypatch, [cow], _config(), start)

    sim.step_day()

    assert cow.status == "fresh"
    assert cow.planned_conception_date is None


def test_ready_cow_uses_residual_service_period_from_calving(monkeypatch) -> None:
    start = date(2025, 8, 1)
    calving = start - timedelta(days=100)
    cow = Cow(
        id="ready",
        birth_date=date(2022, 1, 1),
        status="ready_for_breeding",
        lactation_number=1,
        last_calving_date=calving,
        days_in_current_status=50,
        days_in_milk=100,
    )
    sim = _simulation(
        monkeypatch,
        [cow],
        _config(service_periods=[80, 130]),
        start,
    )

    sim.step_day()

    assert cow.planned_conception_date == calving + timedelta(days=130)
    assert cow.planned_conception_date != start + timedelta(days=130)


def test_fresh_cow_uses_calendar_elapsed_time_at_vwp_boundary(monkeypatch) -> None:
    start = date(2025, 8, 1)
    cow = Cow(
        id="fresh-boundary",
        birth_date=date(2022, 1, 1),
        status="fresh",
        lactation_number=1,
        last_calving_date=start - timedelta(days=50),
        days_in_current_status=49,
        days_in_milk=49,
    )
    sim = _simulation(monkeypatch, [cow], _config(service_periods=[50]), start)

    sim.step_day()

    assert cow.status == "pregnant"
    assert cow.conception_date == start


def test_overdue_heifers_are_spread_and_seed_reproducible(monkeypatch) -> None:
    start = date(2025, 8, 1)

    def run(seed: int) -> list[date]:
        cows = [
            Cow(
                id=f"h-{index}",
                birth_date=start - timedelta(days=500),
                status="heifer",
            )
            for index in range(100)
        ]
        sim = _simulation(monkeypatch, cows, _config(ages=[365]), start, seed)
        sim.step_day()
        return [cow.planned_first_insem_date for cow in cows if cow.planned_first_insem_date is not None]

    first = run(123)
    second = run(123)

    assert first == second
    assert len(set(first)) > 1
    assert all(day > start for day in first)
    assert max((day - start).days for day in first) > 21


def test_manual_purchase_is_applied_once(monkeypatch) -> None:
    start = date(2025, 8, 1)
    monkeypatch.setattr(simulation_module, "cull_cow_combined", lambda *_args, **_kwargs: False)
    plan = [(start, 2)]
    sim = Simulation(
        initial_cows=[],
        cfg=_config(),
        start_date=start,
        file_path="unused.csv",
        purchase_policy=ManualPurchasePolicy(plan=dict(plan)),
        manual_purchase_plan=plan,
        random_seed=42,
    )

    sim.step_day()

    assert len(sim.herd) == 2
    assert sim.history[0].purchases_in_count == 2
    assert sim.purchase_log.manual == [(start, 2)]


def test_report_date_purchase_is_scheduled_for_first_forecast_day() -> None:
    report_date = date(2025, 8, 1)
    params = ScenarioParams(
        dataset_id="test",
        report_date=report_date,
        purchases=[{"date_in": report_date, "count": 2, "days_pregnant": 150}],
    )

    assert _build_manual_purchase_plan(params, report_date) == [(report_date + timedelta(days=1), 2)]


def test_initial_dim_limit_changes_state_instead_of_clamping() -> None:
    report_date = date(2025, 8, 1)
    normal = Cow(
        id="normal",
        birth_date=date(2020, 1, 1),
        status="ready_for_breeding",
        last_calving_date=report_date - timedelta(days=100),
        days_in_milk=100,
    )
    open_over_limit = Cow(
        id="open",
        birth_date=date(2020, 1, 1),
        status="ready_for_breeding",
        last_calving_date=report_date - timedelta(days=351),
        days_in_milk=351,
    )
    pregnant_over_limit = Cow(
        id="pregnant",
        birth_date=date(2020, 1, 1),
        status="pregnant",
        last_calving_date=report_date - timedelta(days=351),
        conception_date=report_date - timedelta(days=100),
        days_in_milk=351,
    )

    herd, stats = _apply_initial_dim_limit(
        [normal, open_over_limit, pregnant_over_limit],
        _config(),
        report_date,
    )
    snapshot = _initial_snapshot(herd, report_date)

    assert [cow.id for cow in herd] == ["normal", "pregnant"]
    assert pregnant_over_limit.status == "dry"
    assert pregnant_over_limit.days_in_milk == 0
    assert snapshot["milking_count"] == 1
    assert snapshot["avg_days_in_milk"] == 100.0
    assert stats == {"dried": 1, "removed": 1}


def test_projected_milking_count_respects_dim_limit_and_calving_reset(monkeypatch) -> None:
    today = date(2025, 8, 1)
    future = today + timedelta(days=1)
    open_cow = Cow(
        id="open",
        birth_date=date(2020, 1, 1),
        status="ready_for_breeding",
        last_calving_date=today - timedelta(days=350),
        days_in_milk=350,
    )
    calving_cow = Cow(
        id="calving",
        birth_date=date(2020, 1, 1),
        status="pregnant",
        last_calving_date=today - timedelta(days=350),
        conception_date=today - timedelta(days=279),
        days_in_milk=350,
    )
    sim = _simulation(monkeypatch, [open_cow, calving_cow], _config(), today)

    assert sim.forecast_milking_count(future) == 1


def test_projected_milking_count_uses_planned_conception(monkeypatch) -> None:
    today = date(2025, 8, 1)
    cow = Cow(
        id="planned-conception",
        birth_date=date(2020, 1, 1),
        status="ready_for_breeding",
        last_calving_date=today - timedelta(days=100),
        planned_conception_date=today + timedelta(days=1),
        days_in_milk=100,
    )
    sim = _simulation(monkeypatch, [cow], _config(), today)

    assert sim.forecast_milking_count(today + timedelta(days=365)) == 1


def test_milking_animal_never_crosses_dim_limit(monkeypatch) -> None:
    start = date(2025, 8, 1)
    cow = Cow(
        id="limit",
        birth_date=date(2021, 1, 1),
        status="ready_for_breeding",
        lactation_number=2,
        last_calving_date=start - timedelta(days=349),
        days_in_current_status=299,
        days_in_milk=349,
    )
    sim = _simulation(monkeypatch, [cow], _config(service_periods=[100]), start)

    sim.run(3)

    assert all(metric.avg_days_in_milk <= 350 for metric in sim.history)
    assert all(not item.is_milking() or item.days_in_milk <= 350 for item in sim.herd)
    assert not sim.herd


def test_monthly_point_does_not_count_report_date_twice(monkeypatch) -> None:
    monkeypatch.setattr(simulation_module, "cull_cow_combined", lambda *_args, **_kwargs: False)
    report_date = date(2025, 1, 1)
    cow = Cow(
        id="calendar",
        birth_date=date(2021, 1, 1),
        status="pregnant",
        lactation_number=2,
        last_calving_date=report_date - timedelta(days=100),
        conception_date=report_date - timedelta(days=20),
        planned_dry_date=date(2025, 6, 1),
        planned_calving_date=date(2025, 8, 1),
        days_in_milk=100,
    )

    rows, _events = _run_seed_job(
        {
            "base_herd": [cow],
            "cfg": _config(),
            "report_date": report_date,
            "temp_path": "unused.csv",
            "total_days": 31,
            "seed": 42,
            "purchase_policy": "manual",
            "manual_plan": [],
            "record_monthly": True,
            "lead_time_days": 90,
            "target_dates": [report_date, date(2025, 2, 1)],
        }
    )

    assert rows[0]["avg_days_in_milk"] == 100
    assert rows[1]["avg_days_in_milk"] == 131
