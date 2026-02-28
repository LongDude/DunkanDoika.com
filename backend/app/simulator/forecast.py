from __future__ import annotations

import io
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from typing import Callable, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from app.api.schemas import (
    EventsByMonth,
    ForecastPoint,
    ForecastResult,
    ForecastResultMeta,
    ForecastSeries,
    ScenarioParams,
)
from app.simulator.engine import EngineConfig, SimulationEngine
from app.simulator.loader import (
    COL_ANIMAL_ID,
    COL_ARCHIVE_DATE,
    COL_BIRTH_DATE,
    COL_DAYS_IN_MILK,
    COL_DRYOFF_DATE,
    COL_LACTATION,
    COL_LACTATION_START,
    COL_SUCCESS_INSEM_DATE,
)
from app.simulator.policies import CullingPolicy, HeiferInsemPolicy, ReplacementPolicy, ServicePeriodPolicy
from app.simulator.types import Animal, EventType, Status


def none_if_na(x):
    return None if pd.isna(x) else x


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


def build_initial_animals(df: pd.DataFrame, report_date: date) -> Dict[int, Animal]:
    animals: Dict[int, Animal] = {}

    for _, r in df.iterrows():
        aid = int(r[COL_ANIMAL_ID])
        birth = r[COL_BIRTH_DATE]
        lact = int(r[COL_LACTATION]) if pd.notna(r[COL_LACTATION]) else 0
        arch = none_if_na(r.get(COL_ARCHIVE_DATE, None))
        last_calv = none_if_na(r.get(COL_LACTATION_START, None))
        success = none_if_na(r.get(COL_SUCCESS_INSEM_DATE, None))
        dryoff = none_if_na(r.get(COL_DRYOFF_DATE, None))
        dim_days = none_if_na(r.get(COL_DAYS_IN_MILK, None))

        a = Animal(
            animal_id=aid,
            birth_date=birth,
            lactation_no=lact,
            last_calving_date=last_calv,
            success_insem_date=success,
            dryoff_date=dryoff,
            archive_date=arch,
        )
        if lact > 0 and dim_days is not None:
            try:
                a.dim_anchor_date = report_date
                a.dim_anchor_value = max(0, int(dim_days))
            except Exception:
                a.dim_anchor_date = None
                a.dim_anchor_value = None

        if arch is not None and arch <= report_date:
            a.status = Status.ARCHIVED
        else:
            if lact == 0:
                if success is not None:
                    calv = success + timedelta(days=280)
                    if calv > report_date:
                        a.status = Status.PREGNANT_HEIFER
                        a.next_calving_date = calv
                    else:
                        a.status = Status.HEIFER
                else:
                    a.status = Status.HEIFER
            else:
                if dryoff is not None and dryoff <= report_date:
                    a.status = Status.DRY
                else:
                    a.status = Status.MILKING

                if success is not None:
                    calv = success + timedelta(days=280)
                    if calv > report_date:
                        a.next_calving_date = calv

                if a.status == Status.DRY and a.success_insem_date is None and a.dryoff_date is not None:
                    inferred_success = a.dryoff_date - timedelta(days=220)
                    a.success_insem_date = inferred_success
                    a.next_calving_date = inferred_success + timedelta(days=280)

        animals[aid] = a

    return animals


def run_one(
    df: pd.DataFrame,
    params: ScenarioParams,
    seed: int,
    dim_mode: Literal["from_calving", "from_dataset_field"] = "from_calving",
) -> Tuple[List[dict], Dict[date, dict], Optional[dict]]:
    report_date = params.report_date
    horizon_end = report_date + timedelta(days=30 * params.horizon_months)

    animals = build_initial_animals(df, report_date)
    rng = np.random.default_rng(seed)

    service = ServicePeriodPolicy(
        mean_days=params.service_period.mean_days,
        std_days=params.service_period.std_days,
        min_days_after_calving=params.service_period.min_days_after_calving,
    )
    heifer = HeiferInsemPolicy(
        min_age_days=params.heifer_insem.min_age_days,
        max_age_days=params.heifer_insem.max_age_days,
    )

    if params.culling.estimate_from_dataset:
        cull = CullingPolicy.estimate_from_dataset(
            df,
            report_date,
            fallback_monthly_hazard=params.culling.fallback_monthly_hazard,
            grouping=getattr(params.culling, "grouping", "lactation"),
            age_band_years=getattr(params.culling, "age_band_years", 2),
        )
    else:
        cull = CullingPolicy(monthly_hazard_by_group={}, fallback_monthly_hazard=params.culling.fallback_monthly_hazard)

    repl = ReplacementPolicy(
        enabled=params.replacement.enabled,
        annual_heifer_ratio=params.replacement.annual_heifer_ratio,
        lookahead_months=params.replacement.lookahead_months,
    )

    cfg = EngineConfig(
        report_date=report_date,
        horizon_end=horizon_end,
        service_policy=service,
        heifer_policy=heifer,
        cull_policy=cull,
        replacement_policy=repl,
        dim_mode=dim_mode,
    )
    eng = SimulationEngine(animals=animals, rng=rng, cfg=cfg)

    for a in eng.animals.values():
        if a.status == Status.ARCHIVED:
            continue
        if a.success_insem_date is not None:
            calv = a.success_insem_date + timedelta(days=280)
            if calv > report_date and calv <= horizon_end:
                eng.push(calv, EventType.CALVING, a.animal_id)
                a.next_calving_date = calv
            if a.lactation_no > 0:
                if a.dryoff_date is not None and a.dryoff_date > report_date and a.dryoff_date <= horizon_end:
                    eng.push(a.dryoff_date, EventType.DRYOFF, a.animal_id)
                elif a.dryoff_date is None:
                    dry = a.success_insem_date + timedelta(days=220)
                    if dry > report_date and dry <= horizon_end:
                        eng.push(dry, EventType.DRYOFF, a.animal_id)

    for p in params.purchases:
        payload = {
            "count": p.count,
            "expected_calving_date": p.expected_calving_date,
            "days_pregnant": p.days_pregnant,
        }
        eng.push(p.date_in, EventType.PURCHASE_IN, None, payload=payload)

    eng.init_schedules(report_date)

    snaps = [report_date] + month_starts_next(report_date, params.horizon_months)
    future_point = None
    if params.future_date is not None and report_date <= params.future_date <= horizon_end:
        if params.future_date not in snaps:
            snaps = sorted(snaps + [params.future_date])
    series = eng.run(snaps)

    events = {}
    for m, v in eng.month_events.items():
        events[m] = {
            "month": m,
            "calvings": v.calvings,
            "dryoffs": v.dryoffs,
            "culls": v.culls,
            "purchases_in": v.purchases_in,
            "heifer_intros": v.heifer_intros,
        }

    if params.future_date is not None:
        for row in series:
            if row["date"] == params.future_date:
                future_point = row
                break

    return series, events, future_point


ProgressCallback = Callable[[int, int, ForecastResult], None]

_WORKER_DF: pd.DataFrame | None = None
_WORKER_PARAMS: ScenarioParams | None = None
_WORKER_DIM_MODE: Literal["from_calving", "from_dataset_field"] = "from_calving"


def _init_mc_worker(
    df_payload: bytes,
    params_payload: dict,
    dim_mode: Literal["from_calving", "from_dataset_field"],
) -> None:
    global _WORKER_DF, _WORKER_PARAMS, _WORKER_DIM_MODE
    _WORKER_DF = pd.read_pickle(io.BytesIO(df_payload))
    _WORKER_PARAMS = ScenarioParams.model_validate(params_payload)
    _WORKER_DIM_MODE = dim_mode


def _run_one_from_worker(seed: int) -> Tuple[List[dict], Dict[date, dict], Optional[dict]]:
    if _WORKER_DF is None or _WORKER_PARAMS is None:
        raise RuntimeError("MC worker is not initialized")
    return run_one(_WORKER_DF, _WORKER_PARAMS, seed, _WORKER_DIM_MODE)


def _to_series(rows: List[dict]) -> ForecastSeries:
    pts = [ForecastPoint(**r) for r in rows]
    return ForecastSeries(points=pts)


def _percentile_series(runs: List[List[dict]], q: float) -> List[dict]:
    dates = [r["date"] for r in runs[0]]
    out = []
    for i, _d in enumerate(dates):
        vals = [run[i]["avg_days_in_milk"] for run in runs if run[i]["avg_days_in_milk"] is not None]
        avg = None if len(vals) == 0 else float(np.percentile(vals, q))
        base = runs[0][i].copy()
        base["avg_days_in_milk"] = avg
        out.append(base)
    return out


def _accumulate_events(events_accum: Dict[date, dict], batch_events: Dict[date, dict]) -> None:
    for month, event_item in batch_events.items():
        if month not in events_accum:
            events_accum[month] = event_item.copy()
            continue
        for key in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
            events_accum[month][key] += event_item[key]


def _build_meta(
    dim_mode: Literal["from_calving", "from_dataset_field"],
    simulation_version: str,
) -> ForecastResultMeta:
    return ForecastResultMeta(
        dim_mode=dim_mode,
        assumptions=[
            "gestation_days=280",
            "dryoff_after_success_insem_days=220",
            "female_birth_probability=0.5",
        ],
        simulation_version=simulation_version,
    )


def _build_result_from_runs(
    *,
    runs: List[List[dict]],
    events_accum: Dict[date, dict],
    completed_runs: int,
    params: ScenarioParams,
    dim_mode: Literal["from_calving", "from_dataset_field"],
    simulation_version: str,
) -> ForecastResult:
    events_list: list[EventsByMonth] = []
    event_divider = max(1, completed_runs)

    for month in sorted(events_accum.keys()):
        event_item = events_accum[month].copy()
        if completed_runs > 1:
            for key in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
                event_item[key] = int(round(event_item[key] / event_divider))
        events_list.append(EventsByMonth(**event_item))

    if completed_runs == 1:
        p50 = _to_series(runs[0])
        fp = None
        if params.future_date is not None:
            for point in runs[0]:
                if point["date"] == params.future_date:
                    fp = ForecastPoint(**point)
                    break
        return ForecastResult(
            series_p50=p50,
            events=events_list,
            future_point=fp,
            meta=_build_meta(dim_mode, simulation_version),
        )

    p50_rows = _percentile_series(runs, 50)
    p10_rows = _percentile_series(runs, 10)
    p90_rows = _percentile_series(runs, 90)

    fp = None
    if params.future_date is not None:
        for row in p50_rows:
            if row["date"] == params.future_date:
                fp = ForecastPoint(**row)
                break

    return ForecastResult(
        series_p50=_to_series(p50_rows),
        series_p10=_to_series(p10_rows),
        series_p90=_to_series(p90_rows),
        events=events_list,
        future_point=fp,
        meta=_build_meta(dim_mode, simulation_version),
    )


def run_forecast(
    df: pd.DataFrame,
    params: ScenarioParams,
    *,
    parallel_enabled: bool = False,
    max_processes: int = 4,
    batch_size: int = 8,
    dim_mode: Literal["from_calving", "from_dataset_field"] = "from_calving",
    simulation_version: str = "1.1.0",
    progress_callback: ProgressCallback | None = None,
) -> ForecastResult:
    runs: list[list[dict]] = []
    events_accum: Dict[date, dict] = {}
    safe_batch_size = max(1, batch_size)
    total_runs = params.mc_runs
    completed_runs = 0

    use_parallel = parallel_enabled and total_runs >= 2 and max_processes > 1
    if use_parallel:
        process_count = max(1, min(max_processes, total_runs))
        if process_count <= 1:
            use_parallel = False

    def on_batch_done(batch_results: list[Tuple[List[dict], Dict[date, dict], Optional[dict]]]) -> None:
        nonlocal completed_runs
        for series_rows, batch_events, _future_point in batch_results:
            runs.append(series_rows)
            _accumulate_events(events_accum, batch_events)
            completed_runs += 1
        if progress_callback and completed_runs > 0:
            partial = _build_result_from_runs(
                runs=runs,
                events_accum=events_accum,
                completed_runs=completed_runs,
                params=params,
                dim_mode=dim_mode,
                simulation_version=simulation_version,
            )
            progress_callback(completed_runs, total_runs, partial)

    if use_parallel:
        params_payload = params.model_dump(mode="json")
        df_buffer = io.BytesIO()
        df.to_pickle(df_buffer)
        df_payload = df_buffer.getvalue()
        all_seeds = [params.seed + i * 9973 for i in range(total_runs)]

        with ProcessPoolExecutor(
            max_workers=process_count,
            initializer=_init_mc_worker,
            initargs=(df_payload, params_payload, dim_mode),
        ) as pool:
            for start in range(0, total_runs, safe_batch_size):
                seed_batch = all_seeds[start : start + safe_batch_size]
                batch_results = list(pool.map(_run_one_from_worker, seed_batch))
                on_batch_done(batch_results)
    else:
        for start in range(0, total_runs, safe_batch_size):
            batch_results: list[Tuple[List[dict], Dict[date, dict], Optional[dict]]] = []
            for i in range(start, min(start + safe_batch_size, total_runs)):
                seed = params.seed + i * 9973
                batch_results.append(run_one(df, params, seed, dim_mode))
            on_batch_done(batch_results)

    return _build_result_from_runs(
        runs=runs,
        events_accum=events_accum,
        completed_runs=max(1, completed_runs),
        params=params,
        dim_mode=dim_mode,
        simulation_version=simulation_version,
    )
