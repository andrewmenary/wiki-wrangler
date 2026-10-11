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

from sqlalchemy import text

try:
    from redis import Redis
except ImportError:  # pragma: no cover - optional dependency fallback
    Redis = None

from app.db import create_database_engine
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
    max_retries: int = 0
    attempts: int = 0
    item_id: str | None = None
    repository_id: str | None = None
    published_by: str | None = None
    database_url: str | None = None
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
            "max_retries": self.max_retries,
            "attempts": self.attempts,
            "item_id": self.item_id,
            "repository_id": self.repository_id,
            "published_by": self.published_by,
            "database_url": self.database_url,
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
            max_retries=int(payload.get("max_retries", 0)),
            attempts=int(payload.get("attempts", 0)),
            item_id=payload.get("item_id"),
            repository_id=payload.get("repository_id"),
            published_by=payload.get("published_by"),
            database_url=payload.get("database_url"),
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


def _persist_job_status(
    job: PublishJob,
    status: PublishJobStatus,
    *,
    error_message: str | None = None,
) -> None:
    if not job.database_url:
        return
    engine = create_database_engine(job.database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE publish_jobs
                    SET status = :status, attempts = :attempts,
                        error_message = :error_message, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "id": job.id,
                    "status": status.value,
                    "attempts": job.attempts,
                    "error_message": error_message,
                },
            )
            if status is PublishJobStatus.FAILED and job.item_id:
                connection.execute(
                    text(
                        """
                        INSERT INTO audit_events (id, item_id, user_id, action, details_json)
                        VALUES (:id, :item_id, :user_id, 'item.publish_failed', :details_json)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "item_id": job.item_id,
                        "user_id": job.published_by,
                        "details_json": json.dumps(
                            {
                                "repository_id": job.repository_id,
                                "job_id": job.id,
                                "error": error_message,
                            }
                        ),
                    },
                )
    finally:
        engine.dispose()


def _persist_job_success(job: PublishJob, result: PublishResult) -> None:
    if not job.database_url or not job.item_id or not job.repository_id:
        return
    engine = create_database_engine(job.database_url)
    publication_id = str(uuid4())
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE publish_jobs
                    SET status = 'succeeded', attempts = :attempts,
                        commit_sha = :commit_sha, error_message = NULL,
                        updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": job.id, "attempts": job.attempts, "commit_sha": result.commit_sha},
            )
            connection.execute(
                text("UPDATE items SET status = 'published' WHERE id = :item_id"),
                {"item_id": job.item_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO publications
                        (id, item_id, repository_id, raw_path, curated_path,
                         commit_sha, branch, published_by)
                    VALUES
                        (:id, :item_id, :repository_id, :raw_path, :curated_path,
                         :commit_sha, :branch, :published_by)
                    """
                ),
                {
                    "id": publication_id,
                    "item_id": job.item_id,
                    "repository_id": job.repository_id,
                    "raw_path": job.raw_path or "",
                    "curated_path": job.curated_path,
                    "commit_sha": result.commit_sha,
                    "branch": job.branch,
                    "published_by": job.published_by,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, item_id, user_id, action, details_json)
                    VALUES (:id, :item_id, :user_id, 'item.published', :details_json)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "item_id": job.item_id,
                    "user_id": job.published_by,
                    "details_json": json.dumps(
                        {"repository_id": job.repository_id, "commit_sha": result.commit_sha}
                    ),
                },
            )
    finally:
        engine.dispose()


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
        self._attempts: dict[str, int] = {}
        self._lock = Lock()
        self._redis_url = redis_url or os.getenv("WIKI_WRANGLER_REDIS_URL")
        self._queue_name = queue_name or os.getenv(
            "WIKI_WRANGLER_PUBLISH_QUEUE", "wiki-wrangler:publish"
        )
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

    def _retry_or_fail(self, job: PublishJob, error_message: str) -> None:
        attempts = max(self._attempts.get(job.id, 0), job.attempts)
        self._attempts[job.id] = attempts
        job.attempts = attempts
        if attempts <= job.max_retries:
            self._statuses[job.id] = PublishJobStatus.QUEUED
            _persist_job_status(
                job, PublishJobStatus.QUEUED, error_message=error_message
            )
            if self._client is not None:
                self._client.rpush(self._queue_name, json.dumps(job.to_dict()))
            else:
                with self._lock:
                    self._jobs.append(job)
            return
        self._statuses[job.id] = PublishJobStatus.FAILED
        _persist_job_status(job, PublishJobStatus.FAILED, error_message=error_message)

    def _mark_running(self, job: PublishJob) -> None:
        job.attempts = max(self._attempts.get(job.id, 0), job.attempts) + 1
        self._attempts[job.id] = job.attempts
        self._statuses[job.id] = PublishJobStatus.RUNNING
        _persist_job_status(job, PublishJobStatus.RUNNING)

    def _mark_succeeded(self, job: PublishJob, result: PublishResult) -> None:
        self._statuses[job.id] = PublishJobStatus.SUCCEEDED
        _persist_job_success(job, result)

    def get_status(self, job_id: str) -> PublishJobStatus | None:
        return self._statuses.get(job_id)

    def run_next(self) -> PublishResult:
        if self._client is not None:
            payload = self._client.lpop(self._queue_name)
            if payload is None:
                raise RuntimeError("No publish jobs are queued")
            job = PublishJob.from_dict(json.loads(payload))
            self._mark_running(job)
            try:
                result = job.execute(runner=self._runner)
            except Exception as error:
                self._retry_or_fail(job, str(error))
                raise
            self._mark_succeeded(job, result)
            return result
        with self._lock:
            if not self._jobs:
                raise RuntimeError("No publish jobs are queued")
            job = self._jobs.popleft()
        self._mark_running(job)
        try:
            result = job.execute(runner=self._runner)
        except Exception as error:
            self._retry_or_fail(job, str(error))
            raise
        self._mark_succeeded(job, result)
        return result

    async def run_next_async(self) -> PublishResult:
        if self._client is not None:
            payload = self._client.lpop(self._queue_name)
            if payload is None:
                raise RuntimeError("No publish jobs are queued")
            job = PublishJob.from_dict(json.loads(payload))
            self._mark_running(job)
            try:
                result = await job.execute_async(runner=self._runner)
            except Exception as error:
                self._retry_or_fail(job, str(error))
                raise
            self._mark_succeeded(job, result)
            return result
        with self._lock:
            if not self._jobs:
                raise RuntimeError("No publish jobs are queued")
            job = self._jobs.popleft()
        self._mark_running(job)
        try:
            result = await job.execute_async(runner=self._runner)
        except Exception as error:
            self._retry_or_fail(job, str(error))
            raise
        self._mark_succeeded(job, result)
        return result

    def drain(self) -> list[PublishResult]:
        results: list[PublishResult] = []
        while True:
            try:
                results.append(self.run_next())
            except RuntimeError:
                return results


def get_publish_queue(
    *,
    redis_url: str | None = None,
    queue_name: str | None = None,
    runner: JobRunner | None = None,
) -> PublishQueue:
    return PublishQueue(
        runner=runner,
        redis_url=redis_url or os.getenv("WIKI_WRANGLER_REDIS_URL"),
        queue_name=queue_name or os.getenv("WIKI_WRANGLER_PUBLISH_QUEUE", "wiki-wrangler:publish"),
    )


DEFAULT_PUBLISH_QUEUE = get_publish_queue()


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
    max_retries: int = 0,
    item_id: str | None = None,
    repository_id: str | None = None,
    published_by: str | None = None,
    database_url: str | None = None,
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
        max_retries=max_retries,
        item_id=item_id,
        repository_id=repository_id,
        published_by=published_by,
        database_url=database_url,
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
        except Exception:
            processed += 1
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
        except Exception:
            processed += 1
            await asyncio.sleep(poll_interval)
            continue

        if max_jobs is not None and processed >= max_jobs:
            return results


async def run_worker_forever(
    *,
    poll_interval: float = 1.0,
    max_jobs: int | None = None,
    redis_url: str | None = None,
    queue_name: str | None = None,
) -> None:
    queue = get_publish_queue(redis_url=redis_url, queue_name=queue_name)
    while True:
        await async_start_publish_worker(queue, poll_interval=poll_interval, max_jobs=max_jobs)
        if max_jobs is not None:
            return
        await asyncio.sleep(poll_interval)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the Wiki Wrangler publish worker")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--redis-url", default=os.getenv("WIKI_WRANGLER_REDIS_URL"))
    parser.add_argument(
        "--queue-name",
        default=os.getenv("WIKI_WRANGLER_PUBLISH_QUEUE", "wiki-wrangler:publish"),
    )
    args = parser.parse_args()

    asyncio.run(
        run_worker_forever(
            poll_interval=args.poll_interval,
            max_jobs=args.max_jobs,
            redis_url=args.redis_url,
            queue_name=args.queue_name,
        )
    )


if __name__ == "__main__":
    _main()
