from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Literal
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.schemas import ScenarioParams
from app.simulator.forecast import run_forecast
from app.simulator.loader import load_dataset_with_quality


def _build_params(report_date: str, mc_runs: int, seed: int, horizon_months: int) -> ScenarioParams:
    return ScenarioParams.model_validate(
        {
            "dataset_id": "benchmark-dataset",
            "report_date": report_date,
            "horizon_months": horizon_months,
            "future_date": None,
            "seed": seed,
            "mc_runs": mc_runs,
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


def _measure(
    *,
    label: str,
    df,
    params: ScenarioParams,
    parallel_enabled: bool,
    max_processes: int,
    batch_size: int,
    dim_mode: Literal["from_calving", "from_dataset_field"],
) -> dict:
    started = time.perf_counter()
    result = run_forecast(
        df,
        params,
        parallel_enabled=parallel_enabled,
        max_processes=max_processes,
        batch_size=batch_size,
        dim_mode=dim_mode,
        simulation_version="benchmark",
    )
    elapsed = time.perf_counter() - started
    points = result.series_p50.points
    return {
        "label": label,
        "duration_sec": round(elapsed, 3),
        "points_count": len(points),
        "nonnull_dim_count": sum(1 for p in points if p.avg_days_in_milk is not None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Monte Carlo sequential vs parallel run_forecast")
    parser.add_argument("--dataset", required=True, help="Path to CSV dataset")
    parser.add_argument("--report-date", default=None, help="YYYY-MM-DD; defaults to suggested report date")
    parser.add_argument("--mc-runs", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon-months", type=int, default=36)
    parser.add_argument("--max-processes", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--dim-mode", choices=["from_calving", "from_dataset_field"], default="from_calving")
    parser.add_argument("--output", default="", help="Optional JSON file output path")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    loaded = load_dataset_with_quality(dataset_path)
    report_date = args.report_date or (
        loaded.report_date_suggested.isoformat() if loaded.report_date_suggested is not None else None
    )
    if report_date is None:
        raise ValueError("Report date is not inferable. Provide --report-date YYYY-MM-DD.")

    params = _build_params(
        report_date=report_date,
        mc_runs=args.mc_runs,
        seed=args.seed,
        horizon_months=args.horizon_months,
    )

    sequential = _measure(
        label="single_process",
        df=loaded.dataframe,
        params=params,
        parallel_enabled=False,
        max_processes=1,
        batch_size=args.batch_size,
        dim_mode=args.dim_mode,
    )
    parallel = _measure(
        label="parallel",
        df=loaded.dataframe,
        params=params,
        parallel_enabled=True,
        max_processes=max(1, args.max_processes),
        batch_size=max(1, args.batch_size),
        dim_mode=args.dim_mode,
    )

    speedup = 0.0
    if parallel["duration_sec"] > 0:
        speedup = round(sequential["duration_sec"] / parallel["duration_sec"], 3)

    report = {
        "dataset": str(dataset_path.resolve()),
        "mc_runs": args.mc_runs,
        "horizon_months": args.horizon_months,
        "dim_mode": args.dim_mode,
        "max_processes": max(1, args.max_processes),
        "batch_size": max(1, args.batch_size),
        "report_date": report_date,
        "quality_issues_count": len(loaded.quality_issues),
        "sequential": sequential,
        "parallel": parallel,
        "speedup_x": speedup,
        "recommendation": {
            "mc_parallel_enabled": True,
            "mc_max_processes": max(1, args.max_processes),
            "mc_batch_size": max(1, args.batch_size),
        },
    }

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved benchmark report to {output_path.resolve()}")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
