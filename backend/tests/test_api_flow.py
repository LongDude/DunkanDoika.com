from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api import routes
from app.api.schemas import ForecastResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeDatasetRepository:
    datasets: dict[str, SimpleNamespace] = {}

    def __init__(self, _session):
        pass

    def create_dataset(self, original_filename: str, _file_bytes: bytes):
        dataset_id = "d-test"
        row = SimpleNamespace(
            dataset_id=dataset_id,
            n_rows=3,
            report_date_suggested=date(2026, 2, 20),
            status_counts_json={"ok": 3},
            quality_issues_json=[],
            original_filename=original_filename,
            created_at=_now(),
            object_key="datasets/d-test.csv",
        )
        self.datasets[dataset_id] = row
        return row

    def get(self, dataset_id: str):
        return self.datasets.get(dataset_id)


class FakeForecastJobRepository:
    jobs: dict[str, SimpleNamespace] = {}

    def __init__(self, _session):
        pass

    def create(self, params, scenario_id=None, expires_in_days=30):
        job = SimpleNamespace(
            job_id="job-test",
            dataset_id=params.dataset_id,
            scenario_id=scenario_id,
            status="succeeded",
            progress_pct=100,
            completed_runs=params.mc_runs,
            total_runs=params.mc_runs,
            error_message=None,
            queued_at=_now(),
            started_at=_now(),
            finished_at=_now(),
            expires_at=_now(),
            result_object_key="results/job-test.json",
            csv_object_key="exports/job-test.csv",
            xlsx_object_key="exports/job-test.xlsx",
        )
        self.jobs[job.job_id] = job
        return job

    def get(self, job_id: str):
        return self.jobs.get(job_id)


def _sample_result() -> ForecastResult:
    return ForecastResult.model_validate(
        {
            "series_p50": {
                "points": [
                    {
                        "date": "2026-02-20",
                        "milking_count": 10,
                        "dry_count": 2,
                        "heifer_count": 5,
                        "pregnant_heifer_count": 3,
                        "avg_days_in_milk": 120.0,
                    }
                ]
            },
            "events": [
                {
                    "month": "2026-02-01",
                    "calvings": 1,
                    "dryoffs": 1,
                    "culls": 0,
                    "purchases_in": 0,
                    "heifer_intros": 0,
                }
            ],
        }
    )


def test_api_validation_and_async_flow(monkeypatch):
    monkeypatch.setattr(main_module.storage_client, "ensure_buckets", lambda: None)
    monkeypatch.setattr(routes, "DatasetRepository", FakeDatasetRepository)
    monkeypatch.setattr(routes, "ForecastJobRepository", FakeForecastJobRepository)
    monkeypatch.setattr(routes, "enqueue_forecast_job", lambda _job_id: "rq-job-id")
    monkeypatch.setattr(routes, "read_job_result", lambda _job_id: _sample_result())
    monkeypatch.setattr(routes.storage_client, "iter_object", lambda _b, _k: iter([b"ok"]))

    with TestClient(main_module.app) as client:
        bad = client.post("/api/forecast/jobs", json={})
        assert bad.status_code == 422
        assert bad.json()["detail"]["error_code"] == "REQUEST_VALIDATION_ERROR"

        upload = client.post(
            "/api/datasets/upload",
            files={"file": ("d.csv", b"a;b\n1;2\n", "text/csv")},
        )
        assert upload.status_code == 200
        dataset_id = upload.json()["dataset_id"]

        payload = {
            "dataset_id": dataset_id,
            "report_date": "2026-02-20",
            "horizon_months": 12,
            "future_date": None,
            "seed": 42,
            "mc_runs": 2,
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
        created = client.post("/api/forecast/jobs", json=payload)
        assert created.status_code == 202
        job_id = created.json()["job"]["job_id"]

        job = client.get(f"/api/forecast/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "succeeded"

        result = client.get(f"/api/forecast/jobs/{job_id}/result")
        assert result.status_code == 200
        assert len(result.json()["series_p50"]["points"]) > 0

        with client.websocket_connect(f"/api/ws/forecast/jobs/{job_id}") as ws:
            event = ws.receive_json()
            assert event["job_id"] == job_id
            assert event["status"] == "succeeded"

        csv_export = client.get(f"/api/forecast/jobs/{job_id}/export/csv")
        assert csv_export.status_code == 200
        xlsx_export = client.get(f"/api/forecast/jobs/{job_id}/export/xlsx")
        assert xlsx_export.status_code == 200
