# Dairy Forecast (Hackathon 2026)

Backend-first application for dairy herd forecasting with async jobs, live progress, and scenario-based Monte Carlo simulation.

## Stack

- Backend: FastAPI
- Database: PostgreSQL
- Queue: Redis + RQ
- Object storage: MinIO
- Frontend: Vue 3 + Vite

## Local Run

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://127.0.0.1:5173`
- Backend OpenAPI: `http://127.0.0.1:8081/docs`
- MinIO Console: `http://127.0.0.1:9001`

## Backend Environment

Core variables:

- `DATABASE_URL`
- `REDIS_URL`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_SECURE`
- `MINIO_BUCKET_DATASETS`
- `MINIO_BUCKET_RESULTS`
- `MINIO_BUCKET_EXPORTS`
- `MAX_UPLOAD_BYTES`
- `ALLOWED_CORS_ORIGINS`
- `STUCK_JOB_TIMEOUT_MINUTES`
- `MC_PARALLEL_ENABLED`
- `MC_MAX_PROCESSES`
- `MC_BATCH_SIZE`
- `WS_HEARTBEAT_SECONDS`
- `DIM_MODE` (`from_calving` | `from_dataset_field`)
- `SIMULATION_VERSION`

## API Overview

### Health

- `GET /api/health/live`
- `GET /api/health/ready`

### Datasets

- `POST /api/datasets/upload`
- `GET /api/datasets/{dataset_id}`
- `GET /api/datasets/{dataset_id}/quality`

`POST /api/datasets/upload` response includes quality diagnostics:

- `quality_issues[]`
  - `code`
  - `severity` (`info|warning|error`)
  - `message`
  - `row_count` (optional)
  - `sample_rows` (optional)

### Scenarios

- `POST /api/scenarios`
- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `POST /api/scenarios/{scenario_id}/run` -> `202 Accepted` with async job id

### Forecast Jobs (async-only)

- `POST /api/forecast/jobs`
- `GET /api/forecast/jobs/{job_id}`
- `GET /api/forecast/jobs/{job_id}/result`
- `GET /api/forecast/jobs/{job_id}/export/csv`
- `GET /api/forecast/jobs/{job_id}/export/xlsx`
- `WS /api/ws/forecast/jobs/{job_id}`

Job states:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

Worker updates:

- Progress tracks `completed_runs/total_runs`
- Intermediate progress events are published via Redis pub/sub and streamed by WS
- Polling endpoints stay available as fallback

### Deprecated sync endpoints

These return `410 Gone`:

- `POST /api/forecast/run`
- `POST /api/forecast/export/csv`
- `POST /api/forecast/export/xlsx`

## Error Contract

All API errors are normalized:

```json
{
  "detail": {
    "error_code": "SOME_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

## Forecast Result Meta

`ForecastResult.meta` includes:

- `dim_mode`
- `assumptions[]`
- `simulation_version`

## Tests

Run tests in backend container:

```bash
docker compose build backend
docker compose run --rm backend python -m pytest tests -q
```

Current suite covers:

- input validators (`PurchaseItem`, `ScenarioParams`)
- dataset quality issue detection
- DIM mode behavior (`from_calving` vs `from_dataset_field`)
- async API flow (`upload -> job -> result -> exports`)

## Regression Smoke Script (Data Set 1/2/3)

```bash
docker compose run --rm backend python scripts/regression_smoke.py \
  --api-base http://host.docker.internal:8081/api \
  --datasets-dir /datasets \
  --mc-runs 30 \
  --output /tmp/regression-smoke-report.json
```

Mount your datasets directory into the container if needed (for example with `-v`).

## Monte Carlo Benchmark Script

Compares sequential vs parallel execution and prints speedup:

```bash
docker compose run --rm backend python scripts/mc_benchmark.py \
  --dataset /datasets/Data\ Set\ 1.csv \
  --mc-runs 300 \
  --max-processes 8 \
  --batch-size 8 \
  --output /tmp/mc-benchmark.json
```

Use the report values to tune:

- `MC_MAX_PROCESSES`
- `MC_BATCH_SIZE`
- `MC_PARALLEL_ENABLED`
