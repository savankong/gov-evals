"""The worker's queue client survives a quiet queue.

A worker waits on the queue for BLOCK_SECONDS at a time, and an empty queue
answers only when that wait expires. redis-py 8.0 began timing out socket reads
after 5 seconds by default -- exactly BLOCK_SECONDS -- so the first quiet poll
raised TimeoutError, the worker exited, and App Platform refused every deploy
with DeployContainerExitNonZero while the API beside it was healthy.

These run against the real redis-py the image installs, which is why the redis
extra is part of dev.
"""

from __future__ import annotations

import json
import os
import time

import pytest
import redis

from aegis.runner import queue as queue_module
from aegis.runner.queue import BLOCK_SECONDS, QUEUE_NAME, RedisQueue


def _queue() -> RedisQueue:
    # from_url does not connect, so no server is needed to inspect the client.
    return RedisQueue("redis://127.0.0.1:1/0")


def test_the_client_waits_longer_than_the_queue_blocks():
    """The regression itself, independent of which redis-py is installed."""
    timeout = _queue()._client.connection_pool.connection_kwargs["socket_timeout"]
    assert timeout is not None and timeout > BLOCK_SECONDS, (
        f"socket_timeout={timeout!r} does not outlast BLOCK_SECONDS={BLOCK_SECONDS}: an empty "
        "queue answers exactly when the block expires, so the client gives up first and the "
        "worker exits."
    )


def test_a_quiet_queue_is_an_empty_poll_not_a_crash(monkeypatch):
    q = _queue()

    def timed_out(*args, **kwargs):
        raise redis.exceptions.TimeoutError("Timeout reading from socket")

    monkeypatch.setattr(q._client, "blpop", timed_out)
    assert q.poll() is None


def test_an_expired_block_is_an_empty_poll(monkeypatch):
    q = _queue()
    monkeypatch.setattr(q._client, "blpop", lambda *a, **k: None)
    assert q.poll() is None


def test_a_message_comes_back_whole(monkeypatch):
    q = _queue()
    body = json.dumps({"campaign_id": "c-1", "judge": {"model": "m"}})
    monkeypatch.setattr(q._client, "blpop", lambda *a, **k: (QUEUE_NAME.encode(), body))
    assert q.poll() == {"campaign_id": "c-1", "judge": {"model": "m"}}


def test_the_worker_loop_keeps_going_past_a_quiet_poll(monkeypatch):
    """consume_forever must treat None as "wait again", not as a stop."""
    q = _queue()
    polls = iter([None, {"campaign_id": "c-2", "judge": None}])
    ran: list[str] = []

    class Stop(Exception):
        pass

    def poll():
        try:
            return next(polls)
        except StopIteration:
            raise Stop from None

    monkeypatch.setattr(q, "poll", poll)
    monkeypatch.setattr(queue_module, "_run_campaign", lambda cid, judge: ran.append(cid))
    with pytest.raises(Stop):
        q.consume_forever()
    assert ran == ["c-2"]


@pytest.mark.skipif(
    not os.environ.get("AEGIS_TEST_REDIS_URL"),
    reason="set AEGIS_TEST_REDIS_URL to run against a real Redis or Valkey",
)
def test_a_full_block_against_a_real_server_returns_empty():
    """End to end: one complete BLOCK_SECONDS wait on an empty queue."""
    q = RedisQueue(os.environ["AEGIS_TEST_REDIS_URL"])
    q._client.delete(QUEUE_NAME)
    started = time.monotonic()
    assert q.poll() is None
    assert time.monotonic() - started >= BLOCK_SECONDS - 0.5
