"""Active-host URL helpers: clone/Open-in must follow Base URL, not forge public host."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core", exc_type=ImportError)


@pytest.mark.skipif(
    not hasattr(labdesk_core, "http_clone_url_for"),
    reason="labdesk_core needs rebuild for http_clone_url_for",
)
def test_http_clone_url_for_uses_active_base():
    assert (
        labdesk_core.http_clone_url_for(
            "http://192.168.0.214:8929", "Ranga/labdesk"
        )
        == "http://192.168.0.214:8929/Ranga/labdesk.git"
    )
    assert (
        labdesk_core.http_clone_url_for(
            "https://git.example.com/", "group/proj.git"
        )
        == "https://git.example.com/group/proj.git"
    )


@pytest.mark.skipif(
    not hasattr(labdesk_core, "rebase_http_url_to_base"),
    reason="labdesk_core needs rebuild for rebase_http_url_to_base",
)
def test_rebase_http_url_to_base_rewrites_public_host():
    base = "http://192.168.0.214:8929"
    assert (
        labdesk_core.rebase_http_url_to_base(
            "https://gitlab.example.com/Ranga/labdesk/-/pipelines/9", base
        )
        == "http://192.168.0.214:8929/Ranga/labdesk/-/pipelines/9"
    )
    assert (
        labdesk_core.rebase_http_url_to_base(
            "https://gitlab.example.com/Ranga/labdesk.git", base
        )
        == "http://192.168.0.214:8929/Ranga/labdesk.git"
    )
    assert (
        labdesk_core.rebase_http_url_to_base(
            "git@gitlab.example.com:Ranga/labdesk.git", base
        )
        is None
    )


@pytest.mark.skipif(
    not hasattr(labdesk_core, "rebase_http_url_to_base"),
    reason="labdesk_core needs rebuild for rebase_http_url_to_base",
)
def test_rebase_is_noop_when_already_on_base():
    base = "http://10.0.0.5:8929"
    url = "http://10.0.0.5:8929/Ranga/labdesk"
    assert labdesk_core.rebase_http_url_to_base(url, base) == url
