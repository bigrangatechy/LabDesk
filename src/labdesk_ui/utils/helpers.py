"""Shared UI helpers."""

from __future__ import annotations


def format_error(exc: BaseException) -> tuple[str, str]:
    """Return (code, message) from a labdesk_core error string."""
    text = str(exc)
    try:
        import labdesk_core

        # PYTHONPATH=src can import an empty namespace package named
        # labdesk_core (the Rust crate dir) when the PyO3 module is not built.
        parse = getattr(labdesk_core, "parse_error_message", None)
        if parse is not None:
            parsed = parse(text)
            return parsed.get("code") or "LD-SYS-001", parsed.get("message") or text
    except Exception:
        pass
    return _parse_bracket_code(text)


def _parse_bracket_code(text: str) -> tuple[str, str]:
    """Pure-Python fallback for ``[LD-…] message`` strings."""
    if text.startswith("[") and "]" in text:
        code, _, rest = text[1:].partition("]")
        code = code.strip()
        msg = rest.lstrip(" :").strip() or text
        if code.startswith("LD-"):
            return code, msg
    return "LD-SYS-001", text
