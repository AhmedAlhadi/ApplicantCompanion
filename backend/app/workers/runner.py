"""Background job processing (§53).

API → in-process task queue → worker → agents → database → SSE progress.

The runner uses a thread pool + an asyncio queue per consumer; the interface
(submit/run) mirrors a Celery-style API so swapping in Redis/Celery later is a
drop-in change (see docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-worker")
_subscribers: dict[str, list[asyncio.Queue]] = {}
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def submit(fn: Callable, *args, **kwargs) -> None:
    """Run a unit of work in the background (non-blocking for the request)."""

    def _wrapped():
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Background job failed: %s", getattr(fn, "__name__", fn))

    _executor.submit(_wrapped)


def publish(entity: str, entity_id: str, event: dict) -> None:
    """Fan out a progress event to SSE subscribers."""
    key = f"{entity}:{entity_id}"
    for queue in list(_subscribers.get(key, [])):
        if _loop is not None:
            _loop.call_soon_threadsafe(queue.put_nowait, event)


def subscribe(entity: str, entity_id: str) -> asyncio.Queue:
    key = f"{entity}:{entity_id}"
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.setdefault(key, []).append(queue)
    return queue


def unsubscribe(entity: str, entity_id: str, queue: asyncio.Queue) -> None:
    key = f"{entity}:{entity_id}"
    if queue in _subscribers.get(key, []):
        _subscribers[key].remove(queue)
    if not _subscribers.get(key):
        _subscribers.pop(key, None)


def notify_workflow(run_id: str, get_run: Callable[[], dict]) -> None:
    """Push the latest workflow state to subscribers (thread-safe)."""
    try:
        publish("workflow", run_id, {"type": "workflow", "data": get_run()})
    except Exception:
        logger.debug("Workflow notify failed for %s", run_id)


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
    for thread in threading.enumerate():
        if thread.name.startswith("agent-worker"):
            logger.debug("worker thread %s stopping", thread.name)
