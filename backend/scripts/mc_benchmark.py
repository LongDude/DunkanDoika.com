from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from app.api.schemas import ScenarioParams
from app.simulator.forecast_herd_m5 import resolve_dataset_start_date, run_forecast_herd_m5


def _build_params(
    *,
    dataset_id: str,
    report_date: str,
    mc_runs: int,
    seed: int,
    horizon_months: int,
    mode: str,
) -> ScenarioParams:
    return ScenarioParams.model_validate(
        {
            "dataset_id": dataset_id,
            "report_date": report_date,
            "horizon_months": horizon_months,
            "future_date": None,
            "seed": seed,
            "mc_runs": mc_runs,
            "mode": mode,
            "purchase_policy": "manual",
            "lead_time_days": 90,
            "confidence_central": 0.8,
            "model": {
                "min_first_insem_age_days": 365,
                "voluntary_waiting_period": 50,
                "max_service_period_after_vwp": 300,
                "population_regulation": 1.0,
                "gestation_lo": 275,
                "gestation_hi": 280,
                "gestation_mu": 277.5,
                "gestation_sigma": 2.0,
                "heifer_birth_prob": 0.5,
                "purchased_days_to_calving_lo": 1,
                "purchased_days_to_calving_hi": 280,
            },
            "purchases": [],
        }
    )


def _measure(
    *,
    label: str,
    csv_bytes: bytes,
    params: ScenarioParams,
    parallel_enabled: bool,
    max_processes: int,
    batch_size: int,
) -> dict:
    started = time.perf_counter()
    result = run_forecast_herd_m5(
        csv_bytes,
        params,
        parallel_enabled=parallel_enabled,
        max_processes=max_processes,
        batch_size=batch_size,
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


def _resolve_report_date(csv_bytes: bytes, explicit_report_date: str | None) -> date:
    if explicit_report_date:
        return date.fromisoformat(explicit_report_date)
    return resolve_dataset_start_date(csv_bytes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Monte Carlo sequential vs parallel herd_m5")
    parser.add_argument("--dataset", required=True, help="Path to CSV dataset")
    parser.add_argument("--report-date", default=None, help="YYYY-MM-DD; defaults to inferred dataset report date")
    parser.add_argument("--mc-runs", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon-months", type=int, default=36)
    parser.add_argument("--mode", choices=["empirical", "theoretical"], default="empirical")
    parser.add_argument("--max-processes", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output", default="", help="Optional JSON file output path")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    csv_bytes = dataset_path.read_bytes()
    report_date = _resolve_report_date(csv_bytes, args.report_date)

    params = _build_params(
        dataset_id="benchmark-dataset",
        report_date=report_date.isoformat(),
        mc_runs=args.mc_runs,
        seed=args.seed,
        horizon_months=args.horizon_months,
        mode=args.mode,
    )

    sequential = _measure(
        label="single_process",
        csv_bytes=csv_bytes,
        params=params,
        parallel_enabled=False,
        max_processes=1,
        batch_size=max(1, args.batch_size),
    )
    parallel = _measure(
        label="parallel",
        csv_bytes=csv_bytes,
        params=params,
        parallel_enabled=True,
        max_processes=max(1, args.max_processes),
        batch_size=max(1, args.batch_size),
    )

    speedup = 0.0
    if parallel["duration_sec"] > 0:
        speedup = round(sequential["duration_sec"] / parallel["duration_sec"], 3)

    report = {
        "dataset": str(dataset_path.resolve()),
        "mc_runs": args.mc_runs,
        "horizon_months": args.horizon_months,
        "mode": args.mode,
        "max_processes": max(1, args.max_processes),
        "batch_size": max(1, args.batch_size),
        "report_date": report_date.isoformat(),
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
