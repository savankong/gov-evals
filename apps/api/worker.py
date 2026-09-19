"""Standalone evaluation worker.

Run one or more of these alongside the API when AEGIS_QUEUE_BACKEND=redis.
Workers execute campaigns; they do not serve HTTP.
"""

from __future__ import annotations

import logging

from aegis.config import get_settings
from aegis.migrate import upgrade_to_head
from aegis.runner.queue import RedisQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("aegis.worker")


def main() -> None:
    settings = get_settings()
    if settings.queue_backend != "redis":
        raise SystemExit(
            "This worker requires AEGIS_QUEUE_BACKEND=redis. With the inline backend the API "
            "process executes campaigns itself and no separate worker is needed."
        )
    upgrade_to_head()
    log.info("Worker starting against %s", settings.redis_url)
    RedisQueue(settings.redis_url).consume_forever()


if __name__ == "__main__":
    main()
