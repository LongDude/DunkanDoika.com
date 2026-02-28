from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from redis import Redis
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import api_error
from app.api.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteSkipItem,
    CreateForecastJobResponse,
    DatasetInfo,
    DatasetQualityIssue,
    DatasetUploadResponse,
    HistoryJobDetail,
    HistoryJobListItem,
    HistoryJobsPageResponse,
    ForecastJobInfo,
    ForecastJobStatus,
    ForecastResult,
    ScenarioCreateRequest,
    ScenarioDetail,
    ScenarioInfo,
    ScenarioParams,
    UserPresetCreateRequest,
    UserPresetResponse,
    UserPresetUpdateRequest,
)
from app.core.config import settings
from app.db.session import SessionLocal, get_db_session
from app.jobs.forecast_jobs import read_job_result
from app.live.events import iter_job_events
from app.queueing import enqueue_forecast_job
from app.repositories.datasets import DatasetRepository
from app.repositories.forecast_jobs import ForecastJobRepository
from app.repositories.scenarios import ScenarioRepository
from app.repositories.user_presets import UserPresetRepository
from app.security.jwt_auth import AuthUser, get_current_user, get_optional_user
from app.simulator.loader import DatasetValidationError
from app.storage.object_storage import storage_client

router = APIRouter()


def _to_job_info(item) -> ForecastJobInfo:
    return ForecastJobInfo(
        job_id=item.job_id,
        dataset_id=item.dataset_id,
        scenario_id=item.scenario_id,
        status=ForecastJobStatus(item.status),
        progress_pct=item.progress_pct,
        completed_runs=item.completed_runs,
        total_runs=item.total_runs,
        error_message=item.error_message,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        expires_at=item.expires_at,
    )


def _to_history_item(item) -> HistoryJobListItem:
    return HistoryJobListItem(
        **_to_job_info(item).model_dump(),
        has_result=bool(item.result_object_key),
    )


def _to_preset_response(item) -> UserPresetResponse:
    return UserPresetResponse(
        preset_id=item.preset_id,
        owner_user_id=item.owner_user_id,
        name=item.name,
        params=item.params_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_state_event(item) -> dict:
    if item.status == ForecastJobStatus.SUCCEEDED.value:
        event_type = "job_succeeded"
    elif item.status == ForecastJobStatus.FAILED.value:
        event_type = "job_failed"
    else:
        event_type = "job_progress"

    return {
        "type": event_type,
        "job_id": item.job_id,
        "status": item.status,
        "progress_pct": item.progress_pct,
        "completed_runs": item.completed_runs,
        "total_runs": item.total_runs,
        "partial_result": None,
        "error_message": item.error_message,
        "ts": _utc_now_iso(),
    }


def _to_dataset_upload_response(item) -> DatasetUploadResponse:
    return DatasetUploadResponse(
        dataset_id=item.dataset_id,
        n_rows=item.n_rows,
        report_date_suggested=item.report_date_suggested,
        status_counts=item.status_counts_json,
        quality_issues=item.quality_issues_json or [],
    )


def _to_dataset_info(item) -> DatasetInfo:
    return DatasetInfo(
        dataset_id=item.dataset_id,
        n_rows=item.n_rows,
        report_date_suggested=item.report_date_suggested,
        status_counts=item.status_counts_json,
        quality_issues=item.quality_issues_json or [],
        original_filename=item.original_filename,
        created_at=item.created_at,
    )


def _allowed_csv_mime(content_type: str | None) -> bool:
    return content_type in {
        None,
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
    }


def _date_from_start_utc(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min).replace(tzinfo=timezone.utc)


def _date_to_end_utc(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max).replace(tzinfo=timezone.utc)


def _delete_job_artifacts_best_effort(job) -> list[BulkDeleteSkipItem]:
    skipped: list[BulkDeleteSkipItem] = []
    object_targets = [
        (storage_client.results_bucket, job.result_object_key, "result"),
        (storage_client.exports_bucket, job.csv_object_key, "csv"),
        (storage_client.exports_bucket, job.xlsx_object_key, "xlsx"),
    ]
    for bucket, object_key, alias in object_targets:
        if not object_key:
            continue
        try:
            storage_client.delete_object(bucket, object_key)
        except Exception as exc:
            skipped.append(
                BulkDeleteSkipItem(
                    id=job.job_id,
                    reason=f"OBJECT_DELETE_FAILED:{alias}:{exc}",
                )
            )
    return skipped


@router.get("/health/live")
def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready() -> dict:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        Redis.from_url(settings.redis_url).ping()
        storage_client.healthcheck()
    except Exception as exc:
        raise api_error(
            status_code=503,
            error_code="DEPENDENCY_UNAVAILABLE",
            message="Service dependencies are not ready",
            details={"reason": str(exc)},
        )
    return {"status": "ready"}


@router.post("/datasets/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> DatasetUploadResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise api_error(400, "INVALID_FILE_TYPE", "Expected a .csv file")
    if not _allowed_csv_mime(file.content_type):
        raise api_error(400, "INVALID_CONTENT_TYPE", "CSV MIME type expected", {"content_type": file.content_type})

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_upload_bytes:
                raise api_error(
                    413,
                    "UPLOAD_TOO_LARGE",
                    "Uploaded file exceeds maximum allowed size",
                    {"max_upload_bytes": settings.max_upload_bytes},
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise api_error(
                413,
                "UPLOAD_TOO_LARGE",
                "Uploaded file exceeds maximum allowed size",
                {"max_upload_bytes": settings.max_upload_bytes},
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    datasets = DatasetRepository(session)
    try:
        row = datasets.create_dataset(filename, content)
    except DatasetValidationError as exc:
        raise api_error(422, exc.error_code, str(exc), exc.details)
    except Exception as exc:
        raise api_error(422, "DATASET_PARSE_FAILED", "Failed to parse dataset", {"reason": str(exc)})
    return _to_dataset_upload_response(row)


@router.get("/datasets/{dataset_id}", response_model=DatasetInfo)
def get_dataset_info(dataset_id: str, session: Session = Depends(get_db_session)) -> DatasetInfo:
    dataset = DatasetRepository(session).get(dataset_id)
    if dataset is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    return _to_dataset_info(dataset)


@router.get("/datasets/{dataset_id}/quality", response_model=list[DatasetQualityIssue])
def get_dataset_quality(dataset_id: str, session: Session = Depends(get_db_session)) -> list[DatasetQualityIssue]:
    dataset = DatasetRepository(session).get(dataset_id)
    if dataset is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    return dataset.quality_issues_json or []


@router.post("/scenarios", response_model=ScenarioDetail)
def scenario_create(req: ScenarioCreateRequest, session: Session = Depends(get_db_session)) -> ScenarioDetail:
    datasets = DatasetRepository(session)
    if datasets.get(req.params.dataset_id) is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")

    scenario = ScenarioRepository(session).create(req.name, req.params)
    return ScenarioDetail(
        scenario_id=scenario.scenario_id,
        name=scenario.name,
        created_at=scenario.created_at.isoformat(timespec="seconds"),
        params=req.params,
    )


@router.get("/scenarios", response_model=list[ScenarioInfo])
def scenario_list(session: Session = Depends(get_db_session)) -> list[ScenarioInfo]:
    rows = ScenarioRepository(session).list()
    out: list[ScenarioInfo] = []
    for row in rows:
        try:
            params = ScenarioParams.model_validate(row.params_json)
        except ValidationError:
            continue
        out.append(
            ScenarioInfo(
                scenario_id=row.scenario_id,
                name=row.name,
                created_at=row.created_at.isoformat(timespec="seconds"),
                dataset_id=row.dataset_id,
                report_date=params.report_date,
                horizon_months=params.horizon_months,
            )
        )
    return out


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
def scenario_get(scenario_id: str, session: Session = Depends(get_db_session)) -> ScenarioDetail:
    row = ScenarioRepository(session).get(scenario_id)
    if row is None:
        raise api_error(404, "SCENARIO_NOT_FOUND", "Scenario not found")
    try:
        params = ScenarioParams.model_validate(row.params_json)
    except ValidationError as exc:
        raise api_error(422, "SCENARIO_PARAMS_INVALID", "Scenario params are inconsistent", {"reason": str(exc)})
    return ScenarioDetail(
        scenario_id=row.scenario_id,
        name=row.name,
        created_at=row.created_at.isoformat(timespec="seconds"),
        params=params,
    )


@router.post(
    "/forecast/jobs",
    response_model=CreateForecastJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_forecast_job(
    params: ScenarioParams,
    session: Session = Depends(get_db_session),
    user: AuthUser | None = Depends(get_optional_user),
) -> CreateForecastJobResponse:
    if DatasetRepository(session).get(params.dataset_id) is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    create_kwargs: dict[str, str] = {}
    if user is not None:
        create_kwargs["owner_user_id"] = user.user_id
    job = ForecastJobRepository(session).create(params=params, **create_kwargs)
    enqueue_forecast_job(job.job_id)
    return CreateForecastJobResponse(job=_to_job_info(job))


@router.get("/forecast/jobs/{job_id}", response_model=ForecastJobInfo)
def get_forecast_job(job_id: str, session: Session = Depends(get_db_session)) -> ForecastJobInfo:
    job = ForecastJobRepository(session).get(job_id)
    if job is None:
        raise api_error(404, "JOB_NOT_FOUND", "Forecast job not found")
    return _to_job_info(job)


@router.websocket("/ws/forecast/jobs/{job_id}")
async def stream_forecast_job(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    with SessionLocal() as session:
        job = ForecastJobRepository(session).get(job_id)
        if job is None:
            await websocket.send_json(
                {
                    "type": "job_failed",
                    "job_id": job_id,
                    "status": ForecastJobStatus.FAILED.value,
                    "progress_pct": 0,
                    "completed_runs": 0,
                    "total_runs": 0,
                    "partial_result": None,
                    "error_message": "JOB_NOT_FOUND",
                    "ts": _utc_now_iso(),
                }
            )
            await websocket.close(code=4404)
            return
        snapshot = _job_state_event(job)
        await websocket.send_json(snapshot)
        if snapshot["type"] in {"job_succeeded", "job_failed"}:
            await websocket.close()
            return

    try:
        async for event in iter_job_events(job_id, settings.ws_heartbeat_seconds):
            await websocket.send_json(event)
            if event.get("type") in {"job_succeeded", "job_failed"}:
                return
    except WebSocketDisconnect:
        return


@router.get("/forecast/jobs/{job_id}/result", response_model=ForecastResult)
def get_forecast_result(job_id: str, session: Session = Depends(get_db_session)) -> ForecastResult:
    job = ForecastJobRepository(session).get(job_id)
    if job is None:
        raise api_error(404, "JOB_NOT_FOUND", "Forecast job not found")
    if job.status != ForecastJobStatus.SUCCEEDED.value:
        raise api_error(409, "JOB_NOT_READY", "Forecast result is not ready yet")
    try:
        return read_job_result(job_id)
    except Exception as exc:
        raise api_error(500, "RESULT_READ_FAILED", "Unable to read forecast result", {"reason": str(exc)})


def _stream_export(
    *,
    job_id: str,
    export_type: str,
    media_type: str,
    filename: str,
    session: Session,
) -> StreamingResponse:
    jobs = ForecastJobRepository(session)
    job = jobs.get(job_id)
    if job is None:
        raise api_error(404, "JOB_NOT_FOUND", "Forecast job not found")
    if job.status != ForecastJobStatus.SUCCEEDED.value:
        raise api_error(409, "JOB_NOT_READY", "Forecast exports are not ready yet")

    object_key = job.csv_object_key if export_type == "csv" else job.xlsx_object_key
    if not object_key:
        raise api_error(409, "EXPORT_NOT_READY", "Requested export object is not available yet")

    stream = storage_client.iter_object(storage_client.exports_bucket, object_key)
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/forecast/jobs/{job_id}/export/csv")
def get_forecast_export_csv(job_id: str, session: Session = Depends(get_db_session)) -> StreamingResponse:
    return _stream_export(
        job_id=job_id,
        export_type="csv",
        media_type="text/csv; charset=utf-8",
        filename="forecast.csv",
        session=session,
    )


@router.get("/forecast/jobs/{job_id}/export/xlsx")
def get_forecast_export_xlsx(job_id: str, session: Session = Depends(get_db_session)) -> StreamingResponse:
    return _stream_export(
        job_id=job_id,
        export_type="xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="forecast.xlsx",
        session=session,
    )


@router.get("/me/history/jobs", response_model=HistoryJobsPageResponse)
def list_my_history_jobs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: ForecastJobStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> HistoryJobsPageResponse:
    if date_from and date_to and date_from > date_to:
        raise api_error(422, "REQUEST_VALIDATION_ERROR", "date_from must be less than or equal to date_to")
    jobs, total = ForecastJobRepository(session).list_for_owner(
        user.user_id,
        status=status_filter.value if status_filter else None,
        q=q,
        date_from=_date_from_start_utc(date_from),
        date_to=_date_to_end_utc(date_to),
        page=page,
        limit=limit,
    )
    return HistoryJobsPageResponse(
        items=[_to_history_item(item) for item in jobs],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/me/history/jobs/{job_id}", response_model=HistoryJobDetail)
def get_my_history_job(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> HistoryJobDetail:
    row = ForecastJobRepository(session).get_for_owner(job_id, user.user_id)
    if row is None:
        raise api_error(404, "HISTORY_ITEM_NOT_FOUND", "History job not found")
    try:
        params = ScenarioParams.model_validate(row.params_json)
    except ValidationError as exc:
        raise api_error(422, "HISTORY_PARAMS_INVALID", "History job params are inconsistent", {"reason": str(exc)})

    return HistoryJobDetail(
        **_to_history_item(row).model_dump(),
        params=params,
    )


@router.get("/me/history/jobs/{job_id}/result", response_model=ForecastResult)
def get_my_history_job_result(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ForecastResult:
    row = ForecastJobRepository(session).get_for_owner(job_id, user.user_id)
    if row is None:
        raise api_error(404, "HISTORY_ITEM_NOT_FOUND", "History job not found")
    if row.status != ForecastJobStatus.SUCCEEDED.value or not row.result_object_key:
        raise api_error(409, "JOB_NOT_READY", "History result is not available")

    try:
        payload = storage_client.get_bytes(storage_client.results_bucket, row.result_object_key)
        return ForecastResult.model_validate_json(payload)
    except Exception as exc:
        raise api_error(
            409,
            "HISTORY_RESULT_EXPIRED",
            "History result object is not available",
            {"reason": str(exc)},
        )


@router.delete("/me/history/jobs/{job_id}", response_model=BulkDeleteResponse)
def delete_my_history_job(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BulkDeleteResponse:
    jobs = ForecastJobRepository(session)
    row = jobs.get_for_owner(job_id, user.user_id)
    if row is None:
        raise api_error(404, "HISTORY_ITEM_NOT_FOUND", "History job not found")
    if row.status in {ForecastJobStatus.QUEUED.value, ForecastJobStatus.RUNNING.value}:
        raise api_error(409, "HISTORY_JOB_ACTIVE", "Cannot delete queued or running job")

    skipped = _delete_job_artifacts_best_effort(row)
    jobs.soft_delete_for_owner(job_id, user.user_id)
    return BulkDeleteResponse(
        deleted_ids=[job_id],
        skipped=skipped,
    )


@router.post("/me/history/jobs/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_my_history_jobs(
    req: BulkDeleteRequest,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BulkDeleteResponse:
    jobs = ForecastJobRepository(session)
    deleted_ids: list[str] = []
    skipped: list[BulkDeleteSkipItem] = []

    for job_id in req.ids:
        row = jobs.get_for_owner(job_id, user.user_id)
        if row is None:
            skipped.append(BulkDeleteSkipItem(id=job_id, reason="NOT_FOUND"))
            continue
        if row.status in {ForecastJobStatus.QUEUED.value, ForecastJobStatus.RUNNING.value}:
            skipped.append(BulkDeleteSkipItem(id=job_id, reason="JOB_ACTIVE"))
            continue
        skipped.extend(_delete_job_artifacts_best_effort(row))
        jobs.soft_delete_for_owner(job_id, user.user_id)
        deleted_ids.append(job_id)

    return BulkDeleteResponse(deleted_ids=deleted_ids, skipped=skipped)


@router.get("/me/presets", response_model=list[UserPresetResponse])
def list_my_presets(
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[UserPresetResponse]:
    rows = UserPresetRepository(session).list_for_owner(user.user_id)
    return [_to_preset_response(row) for row in rows]


@router.post("/me/presets", response_model=UserPresetResponse, status_code=status.HTTP_201_CREATED)
def create_my_preset(
    req: UserPresetCreateRequest,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> UserPresetResponse:
    row = UserPresetRepository(session).create(
        owner_user_id=user.user_id,
        name=req.name,
        params_json=req.params.model_dump(mode="json"),
    )
    return _to_preset_response(row)


@router.put("/me/presets/{preset_id}", response_model=UserPresetResponse)
def update_my_preset(
    preset_id: str,
    req: UserPresetUpdateRequest,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> UserPresetResponse:
    row = UserPresetRepository(session).update(
        preset_id=preset_id,
        owner_user_id=user.user_id,
        name=req.name,
        params_json=req.params.model_dump(mode="json") if req.params is not None else None,
    )
    if row is None:
        raise api_error(404, "PRESET_NOT_FOUND", "Preset not found")
    return _to_preset_response(row)


@router.delete("/me/presets/{preset_id}", response_model=BulkDeleteResponse)
def delete_my_preset(
    preset_id: str,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BulkDeleteResponse:
    row = UserPresetRepository(session).soft_delete(preset_id, user.user_id)
    if row is None:
        raise api_error(404, "PRESET_NOT_FOUND", "Preset not found")
    return BulkDeleteResponse(deleted_ids=[preset_id], skipped=[])


@router.post("/me/presets/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_my_presets(
    req: BulkDeleteRequest,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BulkDeleteResponse:
    repo = UserPresetRepository(session)
    deleted, missing = repo.bulk_soft_delete(req.ids, user.user_id)
    return BulkDeleteResponse(
        deleted_ids=deleted,
        skipped=[BulkDeleteSkipItem(id=item, reason="NOT_FOUND") for item in missing],
    )


@router.post(
    "/scenarios/{scenario_id}/run",
    response_model=CreateForecastJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def scenario_run(
    scenario_id: str,
    session: Session = Depends(get_db_session),
    user: AuthUser | None = Depends(get_optional_user),
) -> CreateForecastJobResponse:
    scenario = ScenarioRepository(session).get(scenario_id)
    if scenario is None:
        raise api_error(404, "SCENARIO_NOT_FOUND", "Scenario not found")
    try:
        params = ScenarioParams.model_validate(scenario.params_json)
    except ValidationError as exc:
        raise api_error(422, "SCENARIO_PARAMS_INVALID", "Scenario params are inconsistent", {"reason": str(exc)})
    if DatasetRepository(session).get(params.dataset_id) is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    create_kwargs: dict[str, str] = {}
    if user is not None:
        create_kwargs["owner_user_id"] = user.user_id
    job = ForecastJobRepository(session).create(params=params, scenario_id=scenario.scenario_id, **create_kwargs)
    enqueue_forecast_job(job.job_id)
    return CreateForecastJobResponse(job=_to_job_info(job))


@router.post("/forecast/run", status_code=status.HTTP_410_GONE, deprecated=True)
def forecast_run_deprecated() -> None:
    raise api_error(
        410,
        "SYNC_ENDPOINT_REMOVED",
        "Use POST /api/forecast/jobs and poll /api/forecast/jobs/{job_id}",
    )


@router.post("/forecast/export/csv", status_code=status.HTTP_410_GONE, deprecated=True)
def forecast_export_csv_deprecated() -> None:
    raise api_error(
        410,
        "SYNC_ENDPOINT_REMOVED",
        "Use GET /api/forecast/jobs/{job_id}/export/csv",
    )


@router.post("/forecast/export/xlsx", status_code=status.HTTP_410_GONE, deprecated=True)
def forecast_export_xlsx_deprecated() -> None:
    raise api_error(
        410,
        "SYNC_ENDPOINT_REMOVED",
        "Use GET /api/forecast/jobs/{job_id}/export/xlsx",
    )
