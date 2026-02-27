from __future__ import annotations

import io
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    DatasetUploadResponse,
    ScenarioParams,
    ForecastResult,
    ScenarioCreateRequest,
    ScenarioInfo,
    ScenarioDetail,
)
from app.storage.datasets import dataset_store
from app.storage.scenarios import scenario_store
from app.simulator.forecast import run_forecast
from app.simulator.exporter import export_forecast_csv, export_forecast_xlsx

router = APIRouter()

@router.post("/datasets/upload", response_model=DatasetUploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file")
    content = await file.read()
    return dataset_store.save_uploaded_csv(file.filename, content)

@router.get("/datasets/{dataset_id}")
def get_dataset_info(dataset_id: str):
    ds = dataset_store.get(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds.public_info()

@router.post("/forecast/run", response_model=ForecastResult)
def forecast_run(params: ScenarioParams):
    ds = dataset_store.get(params.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return run_forecast(ds, params)


@router.post("/forecast/export/csv")
def forecast_export_csv(params: ScenarioParams):
    ds = dataset_store.get(params.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    res = run_forecast(ds, params)
    content = export_forecast_csv(res)
    bio = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=forecast.csv"},
    )


@router.post("/forecast/export/xlsx")
def forecast_export_xlsx(params: ScenarioParams):
    ds = dataset_store.get(params.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    res = run_forecast(ds, params)
    data = export_forecast_xlsx(res)
    bio = io.BytesIO(data)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=forecast.xlsx"},
    )


@router.post("/scenarios", response_model=ScenarioDetail)
def scenario_create(req: ScenarioCreateRequest):
    ds = dataset_store.get(req.params.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    s = scenario_store.create(req.name, req.params)
    return {
        "scenario_id": s.scenario_id,
        "name": s.name,
        "created_at": s.created_at.isoformat(timespec="seconds"),
        "params": s.params,
    }


@router.get("/scenarios", response_model=list[ScenarioInfo])
def scenario_list():
    return [ScenarioInfo(**s.public_info()) for s in scenario_store.list()]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
def scenario_get(scenario_id: str):
    s = scenario_store.get(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {
        "scenario_id": s.scenario_id,
        "name": s.name,
        "created_at": s.created_at.isoformat(timespec="seconds"),
        "params": s.params,
    }


@router.post("/scenarios/{scenario_id}/run", response_model=ForecastResult)
def scenario_run(scenario_id: str):
    s = scenario_store.get(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    ds = dataset_store.get(s.params.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return run_forecast(ds, s.params)
