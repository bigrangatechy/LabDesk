"""Shared UI helpers."""

from __future__ import annotations


def format_error(exc: BaseException) -> tuple[str, str]:
    """Return (code, message) from a labdesk_core error string."""
    text = str(exc)
    try:
        import labdesk_core

        parsed = labdesk_core.parse_error_message(text)
        return parsed.get("code") or "LD-SYS-001", parsed.get("message") or text
    except Exception:
        return "LD-SYS-001", text
