from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api import routes


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeForecastJobRepository:
    job = SimpleNamespace(
        job_id="job-user-1",
        owner_user_id="user-1",
        dataset_id="dataset-1",
        scenario_id=None,
        status="succeeded",
        progress_pct=100,
        completed_runs=50,
        total_runs=50,
        error_message=None,
        queued_at=_now(),
        started_at=_now(),
        finished_at=_now(),
        expires_at=_now(),
        params_json={
            "dataset_id": "dataset-1",
            "report_date": "2026-02-20",
            "horizon_months": 12,
            "future_date": None,
            "seed": 42,
            "mc_runs": 50,
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
        },
        result_object_key="results/job-user-1.json",
        csv_object_key="exports/job-user-1.csv",
        xlsx_object_key="exports/job-user-1.xlsx",
    )

    def __init__(self, _session):
        pass

    def list_for_owner(self, _owner_user_id, **_kwargs):
        return [self.job], 1

    def get_for_owner(self, job_id: str, _owner_user_id: str):
        if job_id == self.job.job_id:
            return self.job
        return None

    def soft_delete_for_owner(self, job_id: str, _owner_user_id: str):
        if job_id != self.job.job_id:
            return None
        self.job.deleted_at = _now()
        return self.job


class FakePresetRepository:
    preset = SimpleNamespace(
        preset_id="preset-1",
        owner_user_id="user-1",
        name="Baseline personal",
        params_json={
            "report_date": "2026-02-20",
            "horizon_months": 12,
            "future_date": None,
            "seed": 42,
            "mc_runs": 50,
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
        },
        created_at=_now(),
        updated_at=_now(),
    )

    def __init__(self, _session):
        pass

    def list_for_owner(self, _owner_user_id: str):
        return [self.preset]

    def create(self, owner_user_id: str, name: str, params_json: dict):
        self.preset.owner_user_id = owner_user_id
        self.preset.name = name
        self.preset.params_json = params_json
        return self.preset

    def update(self, preset_id: str, _owner_user_id: str, *, name=None, params_json=None):
        if preset_id != self.preset.preset_id:
            return None
        if name is not None:
            self.preset.name = name
        if params_json is not None:
            self.preset.params_json = params_json
        self.preset.updated_at = _now()
        return self.preset

    def soft_delete(self, preset_id: str, _owner_user_id: str):
        if preset_id != self.preset.preset_id:
            return None
        return self.preset

    def bulk_soft_delete(self, preset_ids, _owner_user_id: str):
        deleted = [x for x in preset_ids if x == self.preset.preset_id]
        missing = [x for x in preset_ids if x != self.preset.preset_id]
        return deleted, missing


def test_me_history_and_presets_endpoints(monkeypatch):
    monkeypatch.setattr(main_module.storage_client, "ensure_buckets", lambda: None)
    monkeypatch.setattr(routes, "ForecastJobRepository", FakeForecastJobRepository)
    monkeypatch.setattr(routes, "UserPresetRepository", FakePresetRepository)
    monkeypatch.setattr(routes.storage_client, "get_bytes", lambda _b, _k: b'{"series_p50":{"points":[]},"events":[]}')
    monkeypatch.setattr(routes.storage_client, "delete_object", lambda _b, _k: None)

    main_module.app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="user-1", claims={})

    with TestClient(main_module.app) as client:
        page = client.get("/api/me/history/jobs")
        assert page.status_code == 200
        assert page.json()["total"] == 1

        detail = client.get("/api/me/history/jobs/job-user-1")
        assert detail.status_code == 200
        assert detail.json()["job_id"] == "job-user-1"

        result = client.get("/api/me/history/jobs/job-user-1/result")
        assert result.status_code == 200

        deleted = client.delete("/api/me/history/jobs/job-user-1")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_ids"] == ["job-user-1"]

        presets = client.get("/api/me/presets")
        assert presets.status_code == 200
        assert len(presets.json()) == 1

        created = client.post(
            "/api/me/presets",
            json={
                "name": "P1",
                "params": {
                    "report_date": "2026-02-20",
                    "horizon_months": 12,
                    "future_date": None,
                    "seed": 42,
                    "mc_runs": 50,
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
                },
            },
        )
        assert created.status_code == 201

    main_module.app.dependency_overrides.clear()
