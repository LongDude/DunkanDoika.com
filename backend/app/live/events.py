from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_channel(job_id: str) -> str:
    return f"forecast_job:{job_id}"


def publish_job_event(job_id: str, event: dict[str, Any]) -> bool:
    payload = dict(event)
    payload.setdefault("job_id", job_id)
    payload.setdefault("ts", _utc_now_iso())
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        try:
            redis_conn.publish(_job_channel(job_id), json.dumps(payload, ensure_ascii=False))
        finally:
            redis_conn.close()
    except Exception:
        return False
    return True


async def iter_job_events(job_id: str, heartbeat_seconds: int) -> AsyncIterator[dict[str, Any]]:
    redis_conn = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_conn.pubsub()
    channel = _job_channel(job_id)
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=heartbeat_seconds)
            if not message:
                yield {
                    "type": "heartbeat",
                    "job_id": job_id,
                    "ts": _utc_now_iso(),
                }
                continue

            if message.get("type") != "message":
                continue

            try:
                payload = json.loads(message.get("data", "{}"))
            except json.JSONDecodeError:
                continue

            yield payload
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis_conn.aclose()
