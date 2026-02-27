from __future__ import annotations

from redis import Redis
from rq import Worker

from app.core.config import settings
from app.jobs.forecast_jobs import requeue_stuck_jobs
from app.queueing import QUEUE_NAME, enqueue_forecast_job


def main() -> None:
    requeued = requeue_stuck_jobs(settings.stuck_job_timeout_minutes)
    for job_id in requeued:
        enqueue_forecast_job(job_id)

    redis_conn = Redis.from_url(settings.redis_url)
    worker = Worker([QUEUE_NAME], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
