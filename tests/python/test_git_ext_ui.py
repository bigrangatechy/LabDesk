"""Slice N: submodule list formatting helpers (no network)."""

from __future__ import annotations

from labdesk_ui.windows.repo_window import RepoWindow


def test_format_submodule_row_flags():
    text = RepoWindow._format_submodule_row(
        {
            "path": "vendor/lib",
            "workdir_id": "abcd1234",
            "status_summary": "uninitialized",
            "initialized": False,
            "dirty": True,
        }
    )
    assert "vendor/lib" in text
    assert "abcd1234" in text
    assert "uninit" in text
    assert "dirty" in text


def test_format_submodule_row_clean():
    text = RepoWindow._format_submodule_row(
        {
            "path": "deps/x",
            "index_id": "deadbeef",
            "status_summary": "ok",
            "initialized": True,
            "dirty": False,
        }
    )
    assert "deps/x" in text
    assert "deadbeef" in text
    assert "[" not in text
