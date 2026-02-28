from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


def _run_dataset(api_base: str, csv_path: Path, mc_runs: int) -> dict:
    with httpx.Client(timeout=120) as client:
        with csv_path.open("rb") as fh:
            upload = client.post(
                f"{api_base}/datasets/upload",
                files={"file": (csv_path.name, fh, "text/csv")},
            )
        upload.raise_for_status()
        dataset = upload.json()

        payload = {
            "dataset_id": dataset["dataset_id"],
            "report_date": dataset.get("report_date_suggested") or "2026-02-20",
            "horizon_months": 36,
            "future_date": None,
            "seed": 42,
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

        created = client.post(f"{api_base}/forecast/jobs", json=payload, timeout=60)
        created.raise_for_status()
        job_id = created.json()["job"]["job_id"]
        start = time.perf_counter()

        job = None
        for _ in range(900):
            time.sleep(1)
            poll = client.get(f"{api_base}/forecast/jobs/{job_id}", timeout=30)
            poll.raise_for_status()
            job = poll.json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
        if job is None:
            raise RuntimeError("Failed to poll job state")

        output = {
            "dataset_file": csv_path.name,
            "dataset_id": dataset["dataset_id"],
            "job_id": job_id,
            "status": job["status"],
            "duration_sec": round(time.perf_counter() - start, 2),
            "progress_pct": job.get("progress_pct"),
            "completed_runs": job.get("completed_runs"),
            "total_runs": job.get("total_runs"),
        }

        if job["status"] == "succeeded":
            result = client.get(f"{api_base}/forecast/jobs/{job_id}/result", timeout=60)
            result.raise_for_status()
            payload = result.json()
            points = payload["series_p50"]["points"]
            output.update(
                {
                    "points_count": len(points),
                    "nonnull_dim_count": sum(1 for x in points if x.get("avg_days_in_milk") is not None),
                    "events_count": len(payload.get("events", [])),
                }
            )
        else:
            output["error_message"] = job.get("error_message")
        return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Regression smoke for Data Set 1/2/3")
    parser.add_argument("--api-base", default="http://localhost:8081/api")
    parser.add_argument("--datasets-dir", required=True)
    parser.add_argument("--mc-runs", type=int, default=30)
    parser.add_argument("--output", default="regression-smoke-report.json")
    args = parser.parse_args()

    base_dir = Path(args.datasets_dir)
    csv_files = sorted(base_dir.glob("Data Set *.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No Data Set *.csv found in {base_dir}")

    report = {"api_base": args.api_base, "mc_runs": args.mc_runs, "results": []}
    for csv_path in csv_files:
        report["results"].append(_run_dataset(args.api_base, csv_path, args.mc_runs))

    out_path = Path(args.output)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved report to {out_path.resolve()}")


if __name__ == "__main__":
    main()
