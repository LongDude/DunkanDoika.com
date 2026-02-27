from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import copy

import numpy as np
import pandas as pd

from app.storage.datasets import Dataset
from app.api.schemas import ScenarioParams, ForecastResult, ForecastSeries, ForecastPoint, EventsByMonth
from app.simulator.types import Animal, Status, EventType
from app.simulator.engine import SimulationEngine, EngineConfig
from app.simulator.policies import ServicePeriodPolicy, HeiferInsemPolicy, CullingPolicy, ReplacementPolicy


def none_if_na(x):
    return None if pd.isna(x) else x

def month_starts_next(from_date: date, months: int) -> List[date]:
    """First day of each next month, length = months."""
    # start from first day of next month
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
        aid = int(r["Номер животного"])
        birth = r["Дата рождения"]
        lact = int(r["Лактация"]) if pd.notna(r["Лактация"]) else 0
        arch = none_if_na(r.get("Дата архива", None))
        last_calv = none_if_na(r.get("Дата начала тек.лакт", None))
        success = none_if_na(r.get("Дата успешного осеменения", None))
        dryoff = none_if_na(r.get("Дата запуска тек.лакт", None))

        a = Animal(
            animal_id=aid,
            birth_date=birth,
            lactation_no=lact,
            last_calving_date=last_calv,
            success_insem_date=success,
            dryoff_date=dryoff,
            archive_date=arch,
        )

        # Determine status on report_date
        if arch is not None and arch <= report_date:
            a.status = Status.ARCHIVED
        else:
            if lact == 0:
                # heifer/pregnant heifer
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
                # cow
                if dryoff is not None and dryoff <= report_date:
                    a.status = Status.DRY
                else:
                    a.status = Status.MILKING

                # if pregnant and next calving in future, store it
                if success is not None:
                    calv = success + timedelta(days=280)
                    if calv > report_date:
                        a.next_calving_date = calv

                # if dry cow but missing success, infer from dryoff (220d)
                if a.status == Status.DRY and a.success_insem_date is None and a.dryoff_date is not None:
                    inferred_success = a.dryoff_date - timedelta(days=220)
                    a.success_insem_date = inferred_success
                    a.next_calving_date = inferred_success + timedelta(days=280)

        animals[aid] = a

    return animals

def run_one(df: pd.DataFrame, params: ScenarioParams, seed: int) -> Tuple[List[dict], Dict[date, dict], Optional[dict]]:
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
    )

    eng = SimulationEngine(animals=animals, rng=rng, cfg=cfg)

    # schedule known future events from dataset first
    for a in eng.animals.values():
        if a.status == Status.ARCHIVED:
            continue
        # known next calving from dataset success_insem
        if a.success_insem_date is not None:
            calv = a.success_insem_date + timedelta(days=280)
            if calv > report_date and calv <= horizon_end:
                eng.push(calv, EventType.CALVING, a.animal_id)
                a.next_calving_date = calv
            # dryoff: prefer explicit date, else rule +220
            if a.lactation_no > 0:
                if a.dryoff_date is not None and a.dryoff_date > report_date and a.dryoff_date <= horizon_end:
                    eng.push(a.dryoff_date, EventType.DRYOFF, a.animal_id)
                elif a.dryoff_date is None:
                    dry = a.success_insem_date + timedelta(days=220)
                    if dry > report_date and dry <= horizon_end:
                        eng.push(dry, EventType.DRYOFF, a.animal_id)

    # apply purchases (events at date_in)
    for p in params.purchases:
        payload = {
            "count": p.count,
            "expected_calving_date": p.expected_calving_date,
            "days_pregnant": p.days_pregnant,
        }
        eng.push(p.date_in, EventType.PURCHASE_IN, None, payload=payload)

    # init schedules (culls + insems for non-pregnant)
    eng.init_schedules(report_date)

    # snapshots: first day of months, plus optional future_date
    snaps = [report_date] + month_starts_next(report_date, params.horizon_months)
    future_point = None
    if params.future_date is not None and report_date <= params.future_date <= horizon_end:
        # insert while preserving order
        if params.future_date not in snaps:
            snaps = sorted(snaps + [params.future_date])
    series = eng.run(snaps)

    # convert month_events to dict per month
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

    # pull future point if needed
    if params.future_date is not None:
        for row in series:
            if row["date"] == params.future_date:
                future_point = row
                break

    return series, events, future_point

def _to_series(rows: List[dict]) -> ForecastSeries:
    pts = [ForecastPoint(**r) for r in rows]
    return ForecastSeries(points=pts)

def _percentile_series(runs: List[List[dict]], q: float) -> List[dict]:
    # assumes same dates in each run, same length
    dates = [r["date"] for r in runs[0]]
    out = []
    for i, d in enumerate(dates):
        vals = [run[i]["avg_days_in_milk"] for run in runs if run[i]["avg_days_in_milk"] is not None]
        if len(vals) == 0:
            avg = None
        else:
            avg = float(np.percentile(vals, q))
        # counts: take median (should be similar), but we can take first run for simplicity
        base = runs[0][i].copy()
        base["avg_days_in_milk"] = avg
        out.append(base)
    return out

def run_forecast(ds: Dataset, params: ScenarioParams) -> ForecastResult:
    df = ds.df
    runs = []
    events_accum: Dict[date, dict] = {}
    future_points = []

    for i in range(params.mc_runs):
        seed = params.seed + i * 9973
        series, events, future_point = run_one(df, params, seed)
        runs.append(series)
        future_points.append(future_point)

        # accumulate events (sum across MC runs, then average later)
        for m, e in events.items():
            if m not in events_accum:
                events_accum[m] = e.copy()
            else:
                for k in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
                    events_accum[m][k] += e[k]

    # average events if MC
    events_list = []
    for m in sorted(events_accum.keys()):
        e = events_accum[m]
        if params.mc_runs > 1:
            for k in ("calvings", "dryoffs", "culls", "purchases_in", "heifer_intros"):
                e[k] = int(round(e[k] / params.mc_runs))
        events_list.append(EventsByMonth(**e))

    if params.mc_runs == 1:
        p50 = _to_series(runs[0])
        fp = ForecastPoint(**future_points[0]) if future_points[0] is not None else None
        return ForecastResult(series_p50=p50, events=events_list, future_point=fp)

    p50_rows = _percentile_series(runs, 50)
    p10_rows = _percentile_series(runs, 10)
    p90_rows = _percentile_series(runs, 90)

    # future point: take p50 for avg_days_in_milk, and counts from first
    fp = None
    if params.future_date is not None:
        # locate in p50_rows
        for r in p50_rows:
            if r["date"] == params.future_date:
                fp = ForecastPoint(**r)
                break

    return ForecastResult(
        series_p50=_to_series(p50_rows),
        series_p10=_to_series(p10_rows),
        series_p90=_to_series(p90_rows),
        events=events_list,
        future_point=fp,
    )
