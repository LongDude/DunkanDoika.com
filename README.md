# 未経産牛の乳生産能力の予測
Hackaton 2026 - 未経産牛の乳生産能力の予測

Веб‑продукт для прогноза показателя **«Средние дни доения»** на горизонте до 3 лет.

Внутри — **агентная модель** (каждое животное — агент), **событийная симуляция** (отёл/запуск/осеменение/выбытие), рождение телят (самки добавляются в стадо), сценарии покупки нетелей, авто‑компенсация выбытия через ввод собственных нетелей (≈30%/год), Монте‑Карло (p10/p50/p90).

## Run backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend docs: http://127.0.0.1:8000/docs

### Основные эндпоинты

- `POST /api/datasets/upload` — загрузка CSV
- `POST /api/forecast/run` — выполнить прогноз
- `POST /api/forecast/export/csv` — экспорт CSV
- `POST /api/forecast/export/xlsx` — экспорт XLSX
- `POST /api/scenarios` — сохранить сценарий
- `GET /api/scenarios` — список сценариев
- `GET /api/scenarios/{id}` — получить сценарий
- `POST /api/scenarios/{id}/run` — выполнить сценарий

## Run frontend

```bash
cd frontend
npm i
npm run dev
```

Frontend: http://127.0.0.1:5173

### UI умеет
- редактировать параметры модели (сервис‑период, осеменение тёлок, выбытие, ввод нетелей)
- задавать покупки нетелей таблицей
- сохранять/загружать сценарии
- сравнивать сценарии (оверлей p50)
- экспортировать результаты в CSV/XLSX

## Run with Docker

```bash
docker compose up --build
```

- Frontend: http://127.0.0.1:5173
- Backend API docs: http://127.0.0.1:8000/docs