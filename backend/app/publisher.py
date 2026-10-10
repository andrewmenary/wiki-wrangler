import subprocess
from dataclasses import dataclass
from pathlib import Path


class PublishError(RuntimeError):
    """Raised when a Git worktree cannot be updated or committed."""


@dataclass(frozen=True)
class PublishResult:
    commit_sha: str
    changed: bool


def _run_git(worktree: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise PublishError(message)
    return result.stdout.strip()


def _safe_target(worktree: Path, relative_path: str) -> Path:
    target = (worktree / relative_path).resolve()
    root = worktree.resolve()
    if target != root and root not in target.parents:
        raise PublishError("Publication path escapes the repository worktree")
    return target


def publish_worktree(
    worktree: Path,
    raw_source: Path,
    raw_path: str,
    curated_path: str,
    curated_markdown: str,
    commit_message: str,
) -> PublishResult:
    """Write publication files and create an idempotent commit in a Git worktree."""
    if not worktree.is_dir() or not (worktree / ".git").exists():
        raise PublishError("Publication worktree is not a Git repository")
    if not raw_source.is_file():
        raise PublishError("Raw source file is unavailable")

    raw_target = _safe_target(worktree, raw_path)
    curated_target = _safe_target(worktree, curated_path)
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    curated_target.parent.mkdir(parents=True, exist_ok=True)
    raw_target.write_bytes(raw_source.read_bytes())
    curated_target.write_text(curated_markdown, encoding="utf-8")

    _run_git(worktree, "add", "--", raw_path, curated_path)
    staged_check = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--cached", "--quiet"],
        check=False,
    )
    if staged_check.returncode == 0:
        return PublishResult(_run_git(worktree, "rev-parse", "HEAD"), changed=False)
    if staged_check.returncode != 1:
        raise PublishError("Unable to inspect staged Git changes")

    _run_git(worktree, "commit", "-m", commit_message)
    return PublishResult(_run_git(worktree, "rev-parse", "HEAD"), changed=True)


def _clone_or_update_worktree(remote_url: str, workspace: Path, branch: str) -> None:
    if not (workspace / ".git").exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--branch", branch, remote_url, str(workspace)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Git clone failed"
            raise PublishError(message)
        return

    _run_git(workspace, "fetch", "origin", branch)
    _run_git(workspace, "checkout", branch)
    _run_git(workspace, "merge", "--ff-only", f"origin/{branch}")


def publish_remote(
    remote_url: str,
    workspace: Path,
    branch: str,
    raw_source: Path,
    raw_path: str,
    curated_path: str,
    curated_markdown: str,
    commit_message: str,
) -> PublishResult:
    """Clone or update a worker checkout, publish files, and push changed commits."""
    _clone_or_update_worktree(remote_url, workspace, branch)
    result = publish_worktree(
        workspace,
        raw_source,
        raw_path,
        curated_path,
        curated_markdown,
        commit_message,
    )
    if result.changed:
        _run_git(workspace, "push", "origin", branch)
    return result