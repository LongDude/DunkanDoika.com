from __future__ import annotations
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@postgres:5432/dairy_forecast")
    redis_url: str = Field(default="redis://redis:6379/0")

    minio_endpoint: str = Field(default="minio:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_secure: bool = Field(default=False)
    minio_bucket_datasets: str = Field(default="datasets")
    minio_bucket_results: str = Field(default="results")
    minio_bucket_exports: str = Field(default="exports")

    max_upload_bytes: int = Field(default=10 * 1024 * 1024)  # 10 MB
    allowed_cors_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173")
    stuck_job_timeout_minutes: int = Field(default=30)
    mc_parallel_enabled: bool = Field(default=True)
    mc_max_processes: int = Field(default=24)
    mc_batch_size: int = Field(default=32)
    ws_heartbeat_seconds: int = Field(default=15)
    dim_mode: Literal["from_calving", "from_dataset_field"] = Field(default="from_calving")
    simulation_version: str = Field(default="1.1.0")
    sso_jwt_secret: str = Field(default="")
    sso_jwt_algorithms: str = Field(default="HS256")
    sso_user_id_claim: str = Field(default="user_id")
    sso_issuer: str = Field(default="")
    sso_audience: str = Field(default="")

    @property
    def allowed_cors_origins_list(self) -> list[str]:
        return [x.strip() for x in self.allowed_cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
