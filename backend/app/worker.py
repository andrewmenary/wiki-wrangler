from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

try:
    from redis import Redis
except ImportError:  # pragma: no cover - optional dependency fallback
    Redis = None

from app.publisher import PublishResult, publish_remote

JobRunner = Callable[..., PublishResult]


class PublishJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class PublishJob:
    """A queued publish task for a single Git publication."""

    id: str
    remote_url: str
    workspace: Path
    branch: str
    raw_source: Path | None
    raw_path: str | None
    curated_path: str
    curated_markdown: str
    commit_message: str
    runner: JobRunner | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "remote_url": self.remote_url,
            "workspace": str(self.workspace),
            "branch": self.branch,
            "raw_source": str(self.raw_source) if self.raw_source else None,
            "raw_path": self.raw_path,
            "curated_path": self.curated_path,
            "curated_markdown": self.curated_markdown,
            "commit_message": self.commit_message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PublishJob":
        raw_source = payload.get("raw_source")
        return cls(
            id=str(payload["id"]),
            remote_url=str(payload["remote_url"]),
            workspace=Path(str(payload["workspace"])),
            branch=str(payload["branch"]),
            raw_source=Path(raw_source) if raw_source else None,
            raw_path=payload.get("raw_path"),
            curated_path=str(payload["curated_path"]),
            curated_markdown=str(payload["curated_markdown"]),
            commit_message=str(payload["commit_message"]),
        )

    def execute(self, runner: JobRunner | None = None) -> PublishResult:
        callback = runner or self.runner or publish_remote
        result = callback(
            remote_url=self.remote_url,
            workspace=self.workspace,
            branch=self.branch,
            raw_source=self.raw_source,
            raw_path=self.raw_path,
            curated_path=self.curated_path,
            curated_markdown=self.curated_markdown,
            commit_message=self.commit_message,
        )
        if inspect.isawaitable(result):
            raise TypeError("Use execute_async for coroutine-based runners")
        return result

    async def execute_async(self, runner: JobRunner | None = None) -> PublishResult:
        callback = runner or self.runner or publish_remote
        result = callback(
            remote_url=self.remote_url,
            workspace=self.workspace,
            branch=self.branch,
            raw_source=self.raw_source,
            raw_path=self.raw_path,
            curated_path=self.curated_path,
            curated_markdown=self.curated_markdown,
            commit_message=self.commit_message,
        )
        if inspect.isawaitable(result):
            return await result
        return result


class PublishQueue:
    """Queue wrapper with an in-memory fallback and optional Redis backend."""

    def __init__(
        self,
        runner: JobRunner | None = None,
        *,
        redis_url: str | None = None,
        queue_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._runner = runner or publish_remote
        self._jobs: deque[PublishJob] = deque()
        self._statuses: dict[str, PublishJobStatus] = {}
        self._lock = Lock()
        self._redis_url = redis_url or os.getenv("WIKI_WRANGLER_REDIS_URL")
        self._queue_name = queue_name or os.getenv("WIKI_WRANGLER_PUBLISH_QUEUE", "wiki-wrangler:publish")
        self._client = client
        if self._client is None and self._redis_url and Redis is not None:
            self._client = Redis.from_url(self._redis_url, decode_responses=True)

    @property
    def runner(self) -> JobRunner:
        return self._runner

    @property
    def pending_count(self) -> int:
        if self._client is not None:
            return int(self._client.llen(self._queue_name))
        return len(self._jobs)

    def enqueue(self, job: PublishJob) -> PublishJob:
        self._statuses[job.id] = PublishJobStatus.QUEUED
        if self._client is not None:
            self._client.rpush(self._queue_name, json.dumps(job.to_dict()))
            return job
        with self._lock:
            self._jobs.append(job)
        return job

    def get_status(self, job_id: str) -> PublishJobStatus | None:
        return self._statuses.get(job_id)

    def run_next(self) -> PublishResult:
        if self._client is not None:
            payload = self._client.lpop(self._queue_name)
            if payload is None:
                raise RuntimeError("No publish jobs are queued")
            job = PublishJob.from_dict(json.loads(payload))
            self._statuses[job.id] = PublishJobStatus.RUNNING
            try:
                result = job.execute(runner=self._runner)
            except Exception:
                self._statuses[job.id] = PublishJobStatus.FAILED
                raise
            self._statuses[job.id] = PublishJobStatus.SUCCEEDED
            return result
        with self._lock:
            if not self._jobs:
                raise RuntimeError("No publish jobs are queued")
            job = self._jobs.popleft()
        self._statuses[job.id] = PublishJobStatus.RUNNING
        try:
            result = job.execute(runner=self._runner)
        except Exception:
            self._statuses[job.id] = PublishJobStatus.FAILED
            raise
        self._statuses[job.id] = PublishJobStatus.SUCCEEDED
        return result

    async def run_next_async(self) -> PublishResult:
        if self._client is not None:
            payload = self._client.lpop(self._queue_name)
            if payload is None:
                raise RuntimeError("No publish jobs are queued")
            job = PublishJob.from_dict(json.loads(payload))
            self._statuses[job.id] = PublishJobStatus.RUNNING
            try:
                result = await job.execute_async(runner=self._runner)
            except Exception:
                self._statuses[job.id] = PublishJobStatus.FAILED
                raise
            self._statuses[job.id] = PublishJobStatus.SUCCEEDED
            return result
        with self._lock:
            if not self._jobs:
                raise RuntimeError("No publish jobs are queued")
            job = self._jobs.popleft()
        self._statuses[job.id] = PublishJobStatus.RUNNING
        try:
            result = await job.execute_async(runner=self._runner)
        except Exception:
            self._statuses[job.id] = PublishJobStatus.FAILED
            raise
        self._statuses[job.id] = PublishJobStatus.SUCCEEDED
        return result

    def drain(self) -> list[PublishResult]:
        results: list[PublishResult] = []
        while True:
            try:
                results.append(self.run_next())
            except RuntimeError:
                return results


DEFAULT_PUBLISH_QUEUE = PublishQueue()


def queue_publish_job(
    *,
    remote_url: str,
    workspace: Path,
    branch: str,
    raw_source: Path | None,
    raw_path: str | None,
    curated_path: str,
    curated_markdown: str,
    commit_message: str,
    queue: PublishQueue | None = None,
    job_id: str | None = None,
    runner: JobRunner | None = None,
) -> PublishJob:
    target_queue = queue or DEFAULT_PUBLISH_QUEUE
    job = PublishJob(
        id=job_id or str(uuid4()),
        remote_url=remote_url,
        workspace=workspace,
        branch=branch,
        raw_source=raw_source,
        raw_path=raw_path,
        curated_path=curated_path,
        curated_markdown=curated_markdown,
        commit_message=commit_message,
        runner=runner,
    )
    target_queue.enqueue(job)
    return job


def run_publish_job(job: PublishJob, queue: PublishQueue | None = None) -> PublishResult:
    target_queue = queue or DEFAULT_PUBLISH_QUEUE
    return job.execute(runner=target_queue.runner)


def start_publish_worker(
    queue: PublishQueue | None = None,
    *,
    poll_interval: float = 1.0,
    max_jobs: int | None = None,
) -> list[PublishResult]:
    """Process queued publish jobs until the queue is empty or max_jobs is reached."""
    target_queue = queue or DEFAULT_PUBLISH_QUEUE
    results: list[PublishResult] = []
    processed = 0

    while True:
        if target_queue.pending_count == 0:
            if max_jobs is None or processed >= max_jobs:
                return results
            time.sleep(poll_interval)
            continue

        try:
            results.append(target_queue.run_next())
            processed += 1
        except RuntimeError:
            time.sleep(poll_interval)
            continue

        if max_jobs is not None and processed >= max_jobs:
            return results


async def async_start_publish_worker(
    queue: PublishQueue | None = None,
    *,
    poll_interval: float = 1.0,
    max_jobs: int | None = None,
) -> list[PublishResult]:
    """Async worker loop that can execute both sync and coroutine-based job runners."""
    target_queue = queue or DEFAULT_PUBLISH_QUEUE
    results: list[PublishResult] = []
    processed = 0

    while True:
        if target_queue.pending_count == 0:
            if max_jobs is None or processed >= max_jobs:
                return results
            await asyncio.sleep(poll_interval)
            continue

        try:
            results.append(await target_queue.run_next_async())
            processed += 1
        except RuntimeError:
            await asyncio.sleep(poll_interval)
            continue

        if max_jobs is not None and processed >= max_jobs:
            return results


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the Wiki Wrangler publish worker")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--redis-url", default=os.getenv("WIKI_WRANGLER_REDIS_URL"))
    parser.add_argument("--queue-name", default=os.getenv("WIKI_WRANGLER_PUBLISH_QUEUE", "wiki-wrangler:publish"))
    args = parser.parse_args()

    queue = PublishQueue(redis_url=args.redis_url, queue_name=args.queue_name)
    while True:
        start_publish_worker(queue, poll_interval=args.poll_interval, max_jobs=args.max_jobs)
        if args.max_jobs is not None:
            return
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    _main()
