from pathlib import Path

from app.publisher import PublishResult
from app.worker import PublishJob, PublishQueue


def test_publish_queue_executes_enqueued_jobs() -> None:
    events: list[str] = []

    def fake_runner(*, remote_url: str, workspace: Path, branch: str, **kwargs):
        events.append(f"{remote_url}:{branch}:{workspace.name}")
        return PublishResult(commit_sha="abc123", changed=True)

    queue = PublishQueue(runner=fake_runner)
    job = PublishJob(
        id="job-1",
        remote_url="https://github.com/example/wiki.git",
        workspace=Path("/tmp/workspace"),
        branch="main",
        raw_source=None,
        raw_path=None,
        curated_path="curated/notes.md",
        curated_markdown="# Notes\n",
        commit_message="Publish notes",
    )

    queue.enqueue(job)
    result = queue.run_next()

    assert result.commit_sha == "abc123"
    assert events == ["https://github.com/example/wiki.git:main:workspace"]
    assert queue.pending_count == 0


def test_publish_job_is_created_with_a_unique_id() -> None:
    job = PublishJob(
        id="job-123",
        remote_url="https://github.com/example/wiki.git",
        workspace=Path("/tmp/workspace"),
        branch="main",
        raw_source=None,
        raw_path=None,
        curated_path="curated/notes.md",
        curated_markdown="# Notes\n",
        commit_message="Publish notes",
    )

    assert job.id == "job-123"
    assert job.commit_message == "Publish notes"
