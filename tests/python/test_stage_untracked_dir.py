"""Regression: stage must expand untracked directory rows (git add <dir>/)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "repo_stage"):
    pytest.skip("labdesk_core.repo_stage missing", allow_module_level=True)


def _git(cwd: Path, *args: str) -> None:
    import os

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
    )
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        env=env,
        capture_output=True,
    )


def test_repo_stage_expands_untracked_directory(tmp_path: Path):
    """Status may list only `feature/`; staging that path must add nested files."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "init")

    nested = repo / "feature" / "deep"
    nested.mkdir(parents=True)
    (repo / "feature" / "a.rs").write_text("a\n", encoding="utf-8")
    (nested / "b.rs").write_text("b\n", encoding="utf-8")

    statuses = labdesk_core.repo_status(str(repo)) or []
    paths = [e.get("path") for e in statuses if isinstance(e, dict)]
    assert any(p in ("feature", "feature/") for p in paths), paths
    assert not any(p and "a.rs" in p for p in paths), paths

    n = labdesk_core.repo_stage(str(repo), ["feature"])
    assert n >= 2

    after = labdesk_core.repo_status(str(repo)) or []
    staged_paths = [
        e.get("path")
        for e in after
        if isinstance(e, dict) and e.get("staged")
    ]
    assert any(p and str(p).endswith("a.rs") for p in staged_paths), after
    assert any(p and str(p).endswith("b.rs") for p in staged_paths), after
