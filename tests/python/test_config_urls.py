"""Config URL validation (LAN HTTP allowlist) via labdesk_core."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core")


def _connect_code(url: str) -> str:
    """Attempt connect with a dummy PAT; return LD-… code from the failure."""
    try:
        labdesk_core.connect_instance("t", url, "dummy-pat-for-url-tests", "strict")
    except Exception as exc:
        parsed = labdesk_core.parse_error_message(str(exc))
        return parsed.get("code") or "LD-SYS-001"
    pytest.fail(f"connect unexpectedly succeeded for {url}")


def test_https_public_accepted_until_auth_or_network():
    # URL must pass validation; then auth/network fails with a dummy PAT.
    code = _connect_code("https://gitlab.example.com")
    assert code in {
        "LD-AUTH-001",
        "LD-AUTH-002",
        "LD-AUTH-003",
        "LD-NET-001",
        "LD-NET-010",
        "LD-NET-011",
        "LD-API-001",
        "LD-SYS-001",
    }
    assert code not in {"LD-CFG-003", "LD-CFG-004"}


def test_http_rfc1918_accepted_until_auth_or_network():
    code = _connect_code("http://192.168.0.214:8929")
    assert code not in {"LD-CFG-003", "LD-CFG-004"}


def test_http_public_hostname_rejected():
    assert _connect_code("http://gitlab.example.com") == "LD-CFG-003"


def test_saas_rejected():
    assert _connect_code("https://gitlab.com") == "LD-CFG-004"
