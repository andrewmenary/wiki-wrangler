import subprocess

from app.publisher import build_curated_document, publish_remote, publish_worktree


def initialize_git_repository(path):
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Wiki Wrangler"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "wiki@example.com"], check=True
    )


def test_build_curated_document_includes_provenance() -> None:
    document = build_curated_document(
        "Service Guide",
        "Restart instructions",
        "https://example.com/guide",
        "raw/web/item-1/source.html",
        "# Guide\n",
        ["operations", "runbook"],
        "operations/runbooks",
        "private",
    )

    assert 'title: "Service Guide"' in document
    assert 'source: "https://example.com/guide"' in document
    assert 'raw_path: "raw/web/item-1/source.html"' in document
    assert 'tags: ["operations", "runbook"]' in document
    assert 'category: "operations/runbooks"' in document
    assert 'visibility: "private"' in document
    assert document.endswith("# Guide\n")

    public_document = build_curated_document(
        "Public Guide",
        None,
        None,
        None,
        "# Public guide\n",
        ["public", "guide"],
        "public",
        "public",
    )
    assert "source_redacted: true" in public_document
    assert "raw_path:" not in public_document
    assert 'tags: ["public", "guide"]' in public_document
    assert 'category: "public"' in public_document
    assert 'visibility: "public"' in public_document


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


def test_publish_remote_clones_pushes_and_updates_worker_checkout(tmp_path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    initialize_git_repository(seed)
    (seed / "README.md").write_text("Wiki", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-m", "Initial"], check=True)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "remote", "add", "origin", str(remote)], check=True
    )
    subprocess.run(
        ["git", "-C", str(seed), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )

    source = tmp_path / "source.md"
    source.write_text("Source", encoding="utf-8")
    workspace = tmp_path / "workspace"
    result = publish_remote(
        str(remote),
        workspace,
        "main",
        source,
        "raw/file/item-2/source.md",
        "curated/notes/item-2.md",
        "# Notes\n",
        "Add notes",
    )

    assert result.changed is True
    verification = tmp_path / "verification"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(verification)],
        check=True,
        capture_output=True,
    )
    assert (verification / "raw/file/item-2/source.md").read_text(encoding="utf-8") == "Source"
    assert (verification / "curated/notes/item-2.md").read_text(encoding="utf-8") == "# Notes\n"