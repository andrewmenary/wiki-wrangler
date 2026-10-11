import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class PublishError(RuntimeError):
    """Raised when a Git worktree cannot be updated or committed."""


@dataclass(frozen=True)
class PublishResult:
    commit_sha: str
    changed: bool


def build_curated_document(
    title: str,
    summary: str | None,
    source_ref: str | None,
    raw_path: str | None,
    markdown: str,
    tags: list[str] | None = None,
    category_path: str | None = None,
    visibility: str | None = None,
) -> str:
    """Add stable provenance metadata to the curated Markdown document."""
    front_matter = [
        "---",
        f"title: {json.dumps(title)}",
        f"summary: {json.dumps(summary or '')}",
        f"tags: {json.dumps(tags or [], ensure_ascii=False)}",
        f"category: {json.dumps(category_path or '', ensure_ascii=False)}",
        f"visibility: {json.dumps(visibility or 'private')}",
    ]
    if source_ref:
        front_matter.append(f"source: {json.dumps(source_ref)}")
    else:
        front_matter.append("source_redacted: true")
    if raw_path:
        front_matter.append(f"raw_path: {json.dumps(raw_path)}")
    else:
        front_matter.append("raw_published: false")
    front_matter.append("---")
    return "\n".join(front_matter) + "\n\n" + markdown.rstrip() + "\n"


def _run_git(worktree: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=_git_environment(),
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise PublishError(message)
    return result.stdout.strip()


def _git_environment() -> dict[str, str] | None:
    token = os.getenv("WIKI_WRANGLER_GIT_TOKEN")
    if not token:
        return None
    environment = os.environ.copy()
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_KEY_0"] = "http.extraheader"
    environment["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {token}"
    return environment


def _safe_target(worktree: Path, relative_path: str) -> Path:
    target = (worktree / relative_path).resolve()
    root = worktree.resolve()
    if target != root and root not in target.parents:
        raise PublishError("Publication path escapes the repository worktree")
    return target


def publish_worktree(
    worktree: Path,
    raw_source: Path | None,
    raw_path: str | None,
    curated_path: str,
    curated_markdown: str,
    commit_message: str,
    commit_author_name: str | None = None,
    commit_author_email: str | None = None,
) -> PublishResult:
    """Write publication files and create an idempotent commit in a Git worktree."""
    if not worktree.is_dir() or not (worktree / ".git").exists():
        raise PublishError("Publication worktree is not a Git repository")
    if raw_source is not None and not raw_source.is_file():
        raise PublishError("Raw source file is unavailable")

    raw_target = _safe_target(worktree, raw_path) if raw_path else None
    curated_target = _safe_target(worktree, curated_path)
    if raw_target is not None:
        raw_target.parent.mkdir(parents=True, exist_ok=True)
    curated_target.parent.mkdir(parents=True, exist_ok=True)
    if raw_target is not None and raw_source is not None:
        raw_target.write_bytes(raw_source.read_bytes())
    curated_target.write_text(curated_markdown, encoding="utf-8")

    paths = [curated_path] + ([raw_path] if raw_path else [])
    _run_git(worktree, "add", "--", *paths)
    staged_check = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--cached", "--quiet"],
        check=False,
        env=_git_environment(),
    )
    if staged_check.returncode == 0:
        return PublishResult(_run_git(worktree, "rev-parse", "HEAD"), changed=False)
    if staged_check.returncode != 1:
        raise PublishError("Unable to inspect staged Git changes")

    author_name = commit_author_name or os.getenv("WIKI_WRANGLER_GIT_AUTHOR_NAME", "Wiki Wrangler")
    author_email = commit_author_email or os.getenv(
        "WIKI_WRANGLER_GIT_AUTHOR_EMAIL", "wiki-wrangler@localhost"
    )
    _run_git(
        worktree,
        "-c",
        f"user.name={author_name}",
        "-c",
        f"user.email={author_email}",
        "commit",
        "-m",
        commit_message,
    )
    return PublishResult(_run_git(worktree, "rev-parse", "HEAD"), changed=True)


def _clone_or_update_worktree(remote_url: str, workspace: Path, branch: str) -> None:
    if not (workspace / ".git").exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--branch", branch, remote_url, str(workspace)],
            check=False,
            capture_output=True,
            text=True,
            env=_git_environment(),
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
    raw_source: Path | None,
    raw_path: str | None,
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