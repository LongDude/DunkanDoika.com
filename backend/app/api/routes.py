from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from redis import Redis
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import api_error
from app.api.schemas import (
    CreateForecastJobResponse,
    DatasetInfo,
    DatasetUploadResponse,
    ForecastJobInfo,
    ForecastJobStatus,
    ForecastResult,
    ScenarioCreateRequest,
    ScenarioDetail,
    ScenarioInfo,
    ScenarioParams,
)
from app.core.config import settings
from app.db.session import SessionLocal, get_db_session
from app.jobs.forecast_jobs import read_job_result
from app.queueing import enqueue_forecast_job
from app.repositories.datasets import DatasetRepository
from app.repositories.forecast_jobs import ForecastJobRepository
from app.repositories.scenarios import ScenarioRepository
from app.storage.object_storage import storage_client

router = APIRouter()


def _to_job_info(item) -> ForecastJobInfo:
    return ForecastJobInfo(
        job_id=item.job_id,
        dataset_id=item.dataset_id,
        scenario_id=item.scenario_id,
        status=ForecastJobStatus(item.status),
        progress_pct=item.progress_pct,
        error_message=item.error_message,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        expires_at=item.expires_at,
    )


def _to_dataset_upload_response(item) -> DatasetUploadResponse:
    return DatasetUploadResponse(
        dataset_id=item.dataset_id,
        n_rows=item.n_rows,
        report_date_suggested=item.report_date_suggested,
        status_counts=item.status_counts_json,
    )


def _to_dataset_info(item) -> DatasetInfo:
    return DatasetInfo(
        dataset_id=item.dataset_id,
        n_rows=item.n_rows,
        report_date_suggested=item.report_date_suggested,
        status_counts=item.status_counts_json,
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
    except Exception as exc:
        raise api_error(422, "DATASET_PARSE_FAILED", "Failed to parse dataset", {"reason": str(exc)})
    return _to_dataset_upload_response(row)


@router.get("/datasets/{dataset_id}", response_model=DatasetInfo)
def get_dataset_info(dataset_id: str, session: Session = Depends(get_db_session)) -> DatasetInfo:
    dataset = DatasetRepository(session).get(dataset_id)
    if dataset is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    return _to_dataset_info(dataset)


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
) -> CreateForecastJobResponse:
    if DatasetRepository(session).get(params.dataset_id) is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    job = ForecastJobRepository(session).create(params=params)
    enqueue_forecast_job(job.job_id)
    return CreateForecastJobResponse(job=_to_job_info(job))


@router.get("/forecast/jobs/{job_id}", response_model=ForecastJobInfo)
def get_forecast_job(job_id: str, session: Session = Depends(get_db_session)) -> ForecastJobInfo:
    job = ForecastJobRepository(session).get(job_id)
    if job is None:
        raise api_error(404, "JOB_NOT_FOUND", "Forecast job not found")
    return _to_job_info(job)


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


@router.post(
    "/scenarios/{scenario_id}/run",
    response_model=CreateForecastJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def scenario_run(scenario_id: str, session: Session = Depends(get_db_session)) -> CreateForecastJobResponse:
    scenario = ScenarioRepository(session).get(scenario_id)
    if scenario is None:
        raise api_error(404, "SCENARIO_NOT_FOUND", "Scenario not found")
    try:
        params = ScenarioParams.model_validate(scenario.params_json)
    except ValidationError as exc:
        raise api_error(422, "SCENARIO_PARAMS_INVALID", "Scenario params are inconsistent", {"reason": str(exc)})
    if DatasetRepository(session).get(params.dataset_id) is None:
        raise api_error(404, "DATASET_NOT_FOUND", "Dataset not found")
    job = ForecastJobRepository(session).create(params=params, scenario_id=scenario.scenario_id)
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
