"""Work queue.

`inline` runs campaigns in a background thread inside the API process, which
is what a single-node or air-gapped install uses. `redis` hands work to
dedicated worker containers. Both satisfy the same interface, so nothing above
this layer changes when a deployment scales up.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from ..config import get_settings
from ..db import session_scope
from ..models import Campaign

log = logging.getLogger("aegis.queue")
QUEUE_NAME = "aegis:campaigns"


def _run_campaign(campaign_id: str, judge_config: dict | None) -> None:
    from .engine import execute_campaign

    with session_scope() as db:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            log.warning("Campaign %s disappeared before execution", campaign_id)
            return
        try:
            execute_campaign(db, campaign, judge_config)
        except Exception:
            log.exception("Campaign %s failed", campaign_id)
            campaign = db.get(Campaign, campaign_id)
            if campaign:
                campaign.status = "failed"


class InlineQueue:
    """Executes campaigns on a bounded background pool."""

    def __init__(self, concurrency: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="aegis-run")
        self._lock = threading.Lock()
        self._inflight: set[str] = set()

    def enqueue(self, campaign_id: str, judge_config: dict | None = None) -> str:
        with self._lock:
            if campaign_id in self._inflight:
                return "already_queued"
            self._inflight.add(campaign_id)

        def task() -> None:
            try:
                _run_campaign(campaign_id, judge_config)
            finally:
                with self._lock:
                    self._inflight.discard(campaign_id)

        self._pool.submit(task)
        return "queued"

    def depth(self) -> int:
        with self._lock:
            return len(self._inflight)


class RedisQueue:
    """Pushes campaign ids onto a Redis list consumed by worker processes."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url)

    def enqueue(self, campaign_id: str, judge_config: dict | None = None) -> str:
        self._client.rpush(
            QUEUE_NAME, json.dumps({"campaign_id": campaign_id, "judge": judge_config})
        )
        return "queued"

    def depth(self) -> int:
        return int(self._client.llen(QUEUE_NAME))

    def consume_forever(self) -> None:  # pragma: no cover - worker entry point
        log.info("Worker listening on %s", QUEUE_NAME)
        while True:
            item = self._client.blpop(QUEUE_NAME, timeout=5)
            if not item:
                continue
            message = json.loads(item[1])
            _run_campaign(message["campaign_id"], message.get("judge"))


_queue = None


def get_queue():
    global _queue
    if _queue is None:
        settings = get_settings()
        if settings.queue_backend == "redis":
            _queue = RedisQueue(settings.redis_url)
        else:
            _queue = InlineQueue(settings.worker_concurrency)
    return _queue
