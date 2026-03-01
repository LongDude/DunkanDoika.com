# 未経産牛の乳生産能力の予測
Hackaton 2026 - 未経産牛の乳生産能力の予測

Backend-first application for dairy herd forecasting with async jobs, live progress, and scenario-based Monte Carlo simulation.

## URL
### [DunkanDoika (link)](http://dunkandoika.liveisfpv.ru:8080/)

## Прогнозы
Размещены в директории [Results](./Results/README.md)

# Описание проекта
## Используемый стек

- Backend: FastAPI
- Database: PostgreSQL
- Queue: Redis + RQ
- Object storage: MinIO
- Frontend: Vue 3 + Vite

## Локальный запуск
Предварительно настраиваем [переменные окружения](./docs/Environment.md) в корне проекта.

```bash
cp .env.example .env
docker compose up --build
```

Доступ к проекту осуществляется по следующим портам:
- Frontend: `http://127.0.0.1:5173`
- Backend OpenAPI: `http://127.0.0.1:8081/docs`
- MinIO Console: `http://127.0.0.1:9001`

Описание API приведено в [детальной документация](./docs/API.md)
