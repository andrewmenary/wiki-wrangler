import subprocess

from app.publisher import publish_worktree


def initialize_git_repository(path):
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Wiki Wrangler"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "wiki@example.com"], check=True
    )


def test_publish_worktree_writes_both_paths_and_is_idempotent(tmp_path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    initialize_git_repository(repository)
    source = tmp_path / "notes.txt"
    source.write_text("Original notes", encoding="utf-8")

    first = publish_worktree(
        repository,
        source,
        "raw/file/item-1/notes.txt",
        "curated/runbooks/service-guide-item-1.md",
        "# Service guide\n",
        "Add service guide",
    )

    assert first.changed is True
    assert (repository / "raw/file/item-1/notes.txt").read_text(encoding="utf-8") == (
        "Original notes"
    )
    assert (
        repository / "curated/runbooks/service-guide-item-1.md"
    ).read_text(encoding="utf-8") == "# Service guide\n"

    second = publish_worktree(
        repository,
        source,
        "raw/file/item-1/notes.txt",
        "curated/runbooks/service-guide-item-1.md",
        "# Service guide\n",
        "Add service guide",
    )

    assert second.changed is False
    assert second.commit_sha == first.commit_sha