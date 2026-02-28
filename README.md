# 未経産牛の乳生産能力の予測
Hackaton 2026 - 未経産牛の乳生産能力の予測
dunkandoika.liveisfpv.ru
Backend-first architecture for dairy herd forecasting with asynchronous simulation jobs.

## Stack

- Backend: FastAPI
- Database: PostgreSQL
- Queue: Redis + RQ
- Object storage: MinIO
- Frontend: Vue 3 + Vite

## Local Run (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://127.0.0.1:5173`
- Backend API docs: `http://127.0.0.1:8000/docs`
- MinIO console: `http://127.0.0.1:9001`

## Backend Environment

Key variables:

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

## API Overview (Async Forecast)

### Health

- `GET /api/health/live`
- `GET /api/health/ready`

### Datasets

- `POST /api/datasets/upload`
- `GET /api/datasets/{dataset_id}`

### Scenarios

- `POST /api/scenarios`
- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `POST /api/scenarios/{scenario_id}/run` -> creates forecast job

### Forecast Jobs

- `POST /api/forecast/jobs`
- `GET /api/forecast/jobs/{job_id}`
- `GET /api/forecast/jobs/{job_id}/result`
- `GET /api/forecast/jobs/{job_id}/export/csv`
- `GET /api/forecast/jobs/{job_id}/export/xlsx`
- `WS /api/ws/forecast/jobs/{job_id}` for live progress + partial snapshots

### Deprecated Sync Endpoints

These return `410 Gone`:

- `POST /api/forecast/run`
- `POST /api/forecast/export/csv`
- `POST /api/forecast/export/xlsx`

## Notes

- Forecast calculations are executed only by `backend-worker`.
- Database migrations are applied by `backend` startup command (worker does not run Alembic).
- Datasets, forecast results, and exports are stored in MinIO.
- Scenario and job metadata are persisted in PostgreSQL.
