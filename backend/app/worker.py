from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable
from uuid import uuid4

from app.publisher import PublishResult, publish_remote

JobRunner = Callable[..., PublishResult]


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

    def execute(self, runner: JobRunner | None = None) -> PublishResult:
        callback = runner or self.runner or publish_remote
        return callback(
            remote_url=self.remote_url,
            workspace=self.workspace,
            branch=self.branch,
            raw_source=self.raw_source,
            raw_path=self.raw_path,
            curated_path=self.curated_path,
            curated_markdown=self.curated_markdown,
            commit_message=self.commit_message,
        )


class PublishQueue:
    """Small in-process queue that can later be replaced by Redis/arq."""

    def __init__(self, runner: JobRunner | None = None) -> None:
        self._runner = runner or publish_remote
        self._jobs: deque[PublishJob] = deque()
        self._lock = Lock()

    @property
    def runner(self) -> JobRunner:
        return self._runner

    @property
    def pending_count(self) -> int:
        return len(self._jobs)

    def enqueue(self, job: PublishJob) -> PublishJob:
        with self._lock:
            self._jobs.append(job)
        return job

    def run_next(self) -> PublishResult:
        with self._lock:
            if not self._jobs:
                raise RuntimeError("No publish jobs are queued")
            job = self._jobs.popleft()
        return job.execute(runner=self._runner)

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
