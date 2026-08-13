"""Config URL validation (LAN HTTP allowlist) via labdesk_core."""

from __future__ import annotations

import pytest

labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "validate_base_url"):
    pytest.skip(
        "labdesk_core extension module not built (namespace package only)",
        allow_module_level=True,
    )


def _code_from_exc(exc: BaseException) -> str:
    parsed = labdesk_core.parse_error_message(str(exc))
    return parsed.get("code") or "LD-SYS-001"


def test_validate_https_ok():
    labdesk_core.validate_base_url("https://gitlab.example.com")


def test_validate_http_rfc1918_ok():
    labdesk_core.validate_base_url("http://192.168.0.214:8929")
    labdesk_core.validate_base_url("http://10.1.2.3")
    labdesk_core.validate_base_url("http://172.16.0.1")
    labdesk_core.validate_base_url("http://127.0.0.1")
    labdesk_core.validate_base_url("http://localhost:8080")


def test_validate_http_public_hostname_rejected():
    with pytest.raises(Exception) as ei:
        labdesk_core.validate_base_url("http://gitlab.example.com")
    assert _code_from_exc(ei.value) == "LD-CFG-003"


def test_validate_saas_rejected():
    with pytest.raises(Exception) as ei:
        labdesk_core.validate_base_url("https://gitlab.com")
    assert _code_from_exc(ei.value) == "LD-CFG-004"


def test_validate_github_saas_rejected():
    with pytest.raises(Exception) as ei:
        labdesk_core.validate_base_url("https://github.com")
    assert _code_from_exc(ei.value) == "LD-CFG-004"
