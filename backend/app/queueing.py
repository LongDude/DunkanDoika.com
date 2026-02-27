from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import settings

QUEUE_NAME = "forecast"


def get_redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


def get_forecast_queue() -> Queue:
    return Queue(name=QUEUE_NAME, connection=get_redis_connection())


def enqueue_forecast_job(job_id: str) -> str:
    queue = get_forecast_queue()
    job = queue.enqueue("app.jobs.forecast_jobs.run_forecast_job", job_id)
    return job.id
