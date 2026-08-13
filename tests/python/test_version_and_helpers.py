"""Version helper and error formatting."""

from __future__ import annotations

from labdesk_ui.utils.helpers import format_error
from labdesk_ui.version import APP_VERSION, user_agent


def test_app_version_is_nonempty_string():
    assert isinstance(APP_VERSION, str)
    assert APP_VERSION  # "dev" or YYYY.MM.DD


def test_user_agent_prefix():
    assert user_agent().startswith("LabDesk/")


def test_format_error_fallback_without_structured_message():
    code, msg = format_error(RuntimeError("plain failure"))
    assert code == "LD-SYS-001"
    assert "plain failure" in msg


def test_format_error_parses_bracket_code():
    """Must work even when the PyO3 module is not built (CI / PYTHONPATH=src)."""
    code, msg = format_error(
        RuntimeError("[LD-NET-001] Cannot reach instance. Working offline.")
    )
    assert code == "LD-NET-001"
    assert "Cannot reach instance" in msg


def test_format_error_parses_bracket_code_with_colon():
    code, msg = format_error(RuntimeError("[LD-GIT-020] Conflicts detected. Resolve externally."))
    assert code == "LD-GIT-020"
    assert "Conflicts" in msg
