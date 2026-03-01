from __future__ import annotations

import csv
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from app.api.schemas import EventsByMonth, ForecastPoint, ForecastResult, ForecastResultMeta, ForecastSeries, ScenarioParams
from app.simulator.herd_m5.cows_with_death import Cow, get_max_date_from_file, init_empirical_data, load_active_cows
from app.simulator.herd_m5.monte_carlo import _run_one
from app.simulator.herd_m5.samplers import EmpiricalDiscreteSampler, build_theoretical_samplers_from_empirical
from app.simulator.herd_m5.simulation import DailyMetrics, ModelConfig

ProgressCallback = Callable[[int, int, ForecastResult], None]


def month_starts_next(from_date: date, months: int) -> List[date]:
    if from_date.month == 12:
        y, m = from_date.year + 1, 1
    else:
        y, m = from_date.year, from_date.month + 1
    out: List[date] = []
    for _ in range(months):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def parse_dataset_rows(csv_bytes: bytes) -> list[dict]:
    text = csv_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(text.splitlines(), delimiter=";", quotechar='"')
    return list(reader)


def resolve_dataset_start_date(csv_bytes: bytes) -> date:
    rows = parse_dataset_rows(csv_bytes)
    return get_max_date_from_file(rows)


def validate_future_date_is_month_start(future_date: Optional[date]) -> None:
    if future_date is None:
        return
    if future_date.day != 1:
        raise ValueError("FUTURE_DATE_NOT_SUPPORTED: future_date must be month start for herd_m5")


def _initial_snapshot(base_herd: list[Cow], snap_date: date) -> dict:
    milking = 0
    dry = 0
    heifer = 0
    pregnant_heifer = 0
    dim_sum = 0

    for c in base_herd:
        if c.status == "culled":
            continue
        if c.status == "dry":
            dry += 1
        elif c.status == "heifer":
            heifer += 1
        elif c.status == "pregnant_heifer":
            pregnant_heifer += 1

        if c.is_milking():
            milking += 1
            dim_sum += c.days_in_milk

    avg_dim = float(dim_sum / milking) if milking else None
    return {
        "date": snap_date,
        "milking_count": milking,
        "dry_count": dry,
        "heifer_count": heifer,
        "pregnant_heifer_count": pregnant_heifer,
        "avg_days_in_milk": avg_dim,
    }


def _metric_to_row(metric: DailyMetrics) -> dict:
    return {
        "date": metric.day,
        "milking_count": metric.milking_count,
        "dry_count": metric.dry_count,
        "heifer_count": metric.heifer_count,
        "pregnant_heifer_count": metric.pregnant_heifer_count,
        "avg_days_in_milk": float(metric.avg_days_in_milk),
    }


def _find_latest_metric_before(metrics_sorted: list[DailyMetrics], target: date) -> Optional[DailyMetrics]:
    latest = None
    for m in metrics_sorted:
        if m.day <= target:
            latest = m
        else:
            break
    return latest


def _build_run_outputs(
    history: list[DailyMetrics],
    base_herd: list[Cow],
    report_date: date,
    target_dates: list[date],
) -> Tuple[list[dict], Dict[date, dict]]:
    metrics_sorted = sorted(history, key=lambda x: x.day)
    metrics_by_date = {m.day: m for m in metrics_sorted}

    initial = _initial_snapshot(base_herd, report_date)

    rows: list[dict] = []
    events: Dict[date, dict] = {}

    for d in target_dates:
        if d == report_date:
            rows.append(initial)
            continue

        metric = metrics_by_date.get(d)
        if metric is None:
            metric = _find_latest_metric_before(metrics_sorted, d)

        if metric is None:
            rows.append(initial.copy())
            row = rows[-1]
            row["date"] = d
            events[d] = {
                "month": d,
                "calvings": 0,
                "dryoffs": 0,
                "culls": 0,
                "purchases_in": 0,
                "heifer_intros": 0,
            }
            continue

        row = _metric_to_row(metric)
        row["date"] = d
        rows.append(row)

        events[d] = {
            "month": d,
            "calvings": int(metric.calvings_count),
            "dryoffs": int(metric.dryoffs_count),
            "culls": int(metric.culled_count),
            "purchases_in": int(metric.purchases_in_count),
            "heifer_intros": int(metric.heifer_intros_count),
        }

    return rows, events


def _to_series(rows: List[dict]) -> ForecastSeries:
    return ForecastSeries(points=[ForecastPoint(**item) for item in rows])


def _accumulate_events(events_accum: Dict[date, dict], run_events: Dict[date, dict]) -> None:
    for month, event_item in run_events.items():
        if month not in events_accum:
            events_accum[month] = event_item.copy()
            continue
        for key in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
            events_accum[month][key] += int(event_item.get(key, 0))


def _percentile_rows(runs: List[List[dict]], q: float) -> list[dict]:
    out: list[dict] = []
    keys = ["milking_count", "dry_count", "heifer_count", "pregnant_heifer_count", "avg_days_in_milk"]
    for idx in range(len(runs[0])):
        row = {"date": runs[0][idx]["date"]}
        for key in keys:
            values = [run[idx][key] for run in runs if run[idx][key] is not None]
            if not values:
                row[key] = None
                continue
            pct = float(np.percentile(values, q))
            if key != "avg_days_in_milk":
                row[key] = int(round(pct))
            else:
                row[key] = pct
        out.append(row)
    return out


def _build_meta(params: ScenarioParams, simulation_version: str, warnings: list[str]) -> ForecastResultMeta:
    return ForecastResultMeta(
        engine="herd_m5",
        mode=params.mode,
        purchase_policy=params.purchase_policy,
        confidence_central=params.confidence_central,
        assumptions=[
            "mode=empirical uses discrete samples from dataset",
            "mode=theoretical uses fitted lognormal/mixture samplers",
            "manual purchases use only date/count in herd_m5",
        ],
        warnings=warnings,
        simulation_version=simulation_version,
    )


def _build_result_from_runs(
    *,
    runs: List[List[dict]],
    events_accum: Dict[date, dict],
    completed_runs: int,
    params: ScenarioParams,
    simulation_version: str,
    warnings: list[str],
) -> ForecastResult:
    lower_q = ((1.0 - params.confidence_central) / 2.0) * 100.0
    upper_q = 100.0 - lower_q

    p50_rows = _percentile_rows(runs, 50.0)
    plo_rows = _percentile_rows(runs, lower_q)
    phi_rows = _percentile_rows(runs, upper_q)

    events_list: list[EventsByMonth] = []
    divider = max(1, completed_runs)
    for month in sorted(events_accum.keys()):
        base = events_accum[month].copy()
        if completed_runs > 1:
            for key in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
                base[key] = int(round(base[key] / divider))
        events_list.append(EventsByMonth(**base))

    future_point = None
    if params.future_date is not None:
        for row in p50_rows:
            if row["date"] == params.future_date:
                future_point = ForecastPoint(**row)
                break

    return ForecastResult(
        series_p50=_to_series(p50_rows),
        series_p10=_to_series(plo_rows),
        series_p90=_to_series(phi_rows),
        events=events_list,
        future_point=future_point,
        meta=_build_meta(params, simulation_version, warnings),
    )


def _prepare_model_config(file_path: str, mode: str, params: ScenarioParams) -> ModelConfig:
    init_empirical_data(file_path)

    from app.simulator.herd_m5.cows_with_death import get_empirical_lists

    ages, dtd, sp = get_empirical_lists()

    if mode == "empirical":
        age_sampler = EmpiricalDiscreteSampler(list(ages))
        sp_sampler = EmpiricalDiscreteSampler(list(sp))
        dtd_sampler = EmpiricalDiscreteSampler(list(dtd))
    else:
        age_sampler, sp_sampler, dtd_sampler = build_theoretical_samplers_from_empirical(ages, sp, dtd)

    model = params.model
    return ModelConfig(
        age_first_insem_days=age_sampler,
        service_period_days=sp_sampler,
        conception_to_dry_days=dtd_sampler,
        min_first_insem_age_days=model.min_first_insem_age_days,
        voluntary_waiting_period=model.voluntary_waiting_period,
        max_service_period_after_vwp=model.max_service_period_after_vwp,
        population_regulation=model.population_regulation,
        gestation_lo=model.gestation_lo,
        gestation_hi=model.gestation_hi,
        gestation_mu=model.gestation_mu,
        gestation_sigma=model.gestation_sigma,
        heifer_birth_prob=model.heifer_birth_prob,
        purchased_days_to_calving_lo=model.purchased_days_to_calving_lo,
        purchased_days_to_calving_hi=model.purchased_days_to_calving_hi,
    )


def _build_manual_purchase_plan(params: ScenarioParams) -> list[Tuple[date, int]]:
    return [(item.date_in, int(item.count)) for item in params.purchases]


def _warnings_for_params(params: ScenarioParams) -> list[str]:
    warnings: list[str] = []
    if params.purchase_policy == "manual" and any(
        item.expected_calving_date is not None or item.days_pregnant is not None for item in params.purchases
    ):
        warnings.append("manual purchase expected_calving_date/days_pregnant are ignored by herd_m5")
    return warnings


def _run_seed_job(args: dict) -> Tuple[list[dict], Dict[date, dict]]:
    result = _run_one(
        {
            "base_herd": args["base_herd"],
            "cfg": args["cfg"],
            "start_date": args["report_date"],
            "file_path": args["temp_path"],
            "days": args["total_days"],
            "seed": args["seed"],
            "policy": args["purchase_policy"],
            "manual_purchase_plan": args["manual_plan"],
            "record_monthly": True,
            "lead_time_days": args["lead_time_days"],
        }
    )
    history = result["history"]
    return _build_run_outputs(history, args["base_herd"], args["report_date"], args["target_dates"])


def run_forecast_herd_m5(
    csv_bytes: bytes,
    params: ScenarioParams,
    *,
    parallel_enabled: bool,
    max_processes: int,
    batch_size: int,
    simulation_version: str,
    progress_callback: ProgressCallback | None = None,
) -> ForecastResult:
    validate_future_date_is_month_start(params.future_date)

    report_date = resolve_dataset_start_date(csv_bytes)
    if params.report_date is not None and params.report_date != report_date:
        raise ValueError("REPORT_DATE_MISMATCH: report_date does not match dataset factual date")

    target_dates = [report_date] + month_starts_next(report_date, params.horizon_months)
    if params.future_date is not None:
        horizon_end = target_dates[-1]
        if params.future_date < report_date or params.future_date > horizon_end:
            raise ValueError("FUTURE_DATE_OUT_OF_RANGE: future_date is outside forecast horizon")
        if params.future_date not in target_dates:
            target_dates.append(params.future_date)
            target_dates.sort()

    horizon_end = target_dates[-1]
    total_days = (horizon_end - report_date).days + 1

    temp_path: str | None = None
    runs: list[list[dict]] = []
    events_accum: Dict[date, dict] = {}
    completed_runs = 0
    warnings = _warnings_for_params(params)

    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
            tmp.write(csv_bytes)
            temp_path = tmp.name

        cfg = _prepare_model_config(temp_path, params.mode, params)
        base_herd = load_active_cows(temp_path)
        manual_plan = _build_manual_purchase_plan(params)

        safe_batch_size = max(1, batch_size)
        all_seeds = [params.seed + i * 9973 for i in range(params.mc_runs)]

        def on_batch_done(batch_outputs: list[Tuple[list[dict], Dict[date, dict]]]) -> None:
            nonlocal completed_runs
            for rows, run_events in batch_outputs:
                runs.append(rows)
                _accumulate_events(events_accum, run_events)
                completed_runs += 1
            if progress_callback and completed_runs > 0:
                partial = _build_result_from_runs(
                    runs=runs,
                    events_accum=events_accum,
                    completed_runs=completed_runs,
                    params=params,
                    simulation_version=simulation_version,
                    warnings=warnings,
                )
                progress_callback(completed_runs, params.mc_runs, partial)

        use_parallel = parallel_enabled and params.mc_runs >= 2 and max_processes > 1
        if use_parallel:
            process_count = max(1, min(max_processes, params.mc_runs))
            if process_count <= 1:
                use_parallel = False

        if use_parallel:
            with ProcessPoolExecutor(max_workers=process_count) as pool:
                for start in range(0, params.mc_runs, safe_batch_size):
                    seeds = all_seeds[start : start + safe_batch_size]
                    batch_args = [
                        {
                            "base_herd": base_herd,
                            "cfg": cfg,
                            "report_date": report_date,
                            "temp_path": temp_path,
                            "total_days": total_days,
                            "seed": seed,
                            "purchase_policy": params.purchase_policy,
                            "manual_plan": manual_plan,
                            "lead_time_days": params.lead_time_days,
                            "target_dates": target_dates,
                        }
                        for seed in seeds
                    ]
                    batch_outputs = list(pool.map(_run_seed_job, batch_args))
                    on_batch_done(batch_outputs)
        else:
            for start in range(0, params.mc_runs, safe_batch_size):
                seeds = all_seeds[start : start + safe_batch_size]
                batch_outputs = [
                    _run_seed_job(
                        {
                            "base_herd": base_herd,
                            "cfg": cfg,
                            "report_date": report_date,
                            "temp_path": temp_path,
                            "total_days": total_days,
                            "seed": seed,
                            "purchase_policy": params.purchase_policy,
                            "manual_plan": manual_plan,
                            "lead_time_days": params.lead_time_days,
                            "target_dates": target_dates,
                        }
                    )
                    for seed in seeds
                ]
                on_batch_done(batch_outputs)

        return _build_result_from_runs(
            runs=runs,
            events_accum=events_accum,
            completed_runs=max(1, completed_runs),
            params=params,
            simulation_version=simulation_version,
            warnings=warnings,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
