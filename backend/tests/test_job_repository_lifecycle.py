from __future__ import annotations

from types import SimpleNamespace

from app.api.schemas import ForecastJobStatus
from app.repositories.forecast_jobs import ForecastJobRepository


class _DummySession:
    def commit(self) -> None:
        return None

    def refresh(self, _obj) -> None:
        return None


def test_job_lifecycle_transitions_and_terminal_guards(monkeypatch) -> None:
    job = SimpleNamespace(
        job_id="job-1",
        status=ForecastJobStatus.QUEUED.value,
        progress_pct=0,
        completed_runs=0,
        total_runs=10,
        error_message=None,
        result_object_key=None,
        csv_object_key=None,
        xlsx_object_key=None,
        started_at=None,
        finished_at=None,
        params_json={"mc_runs": 10},
    )

    repo = ForecastJobRepository(_DummySession())
    monkeypatch.setattr(repo, "get", lambda _job_id: job)

    running = repo.mark_running(job.job_id, progress_pct=10, total_runs=10)
    assert running is job
    assert job.status == ForecastJobStatus.RUNNING.value
    assert job.progress_pct == 10
    assert job.started_at is not None

    progressed = repo.update_progress(job.job_id, progress_pct=50, completed_runs=5, total_runs=10)
    assert progressed is job
    assert job.progress_pct == 50
    assert job.completed_runs == 5

    failed = repo.mark_failed(job.job_id, "ERR")
    assert failed is job
    assert job.status == ForecastJobStatus.FAILED.value
    assert job.error_message == "ERR"
    assert job.finished_at is not None

    # Terminal guard: failed job must not be overwritten as succeeded.
    still_failed = repo.mark_succeeded(
        job.job_id,
        result_object_key="results/job-1.json",
        csv_object_key="exports/job-1.csv",
        xlsx_object_key="exports/job-1.xlsx",
    )
    assert still_failed is job
    assert job.status == ForecastJobStatus.FAILED.value
    assert job.result_object_key is None
