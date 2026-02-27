from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router

app = FastAPI(title="Dairy Forecast API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for MVP; restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
