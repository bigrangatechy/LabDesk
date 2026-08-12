"""User-visible LabDesk version (build date when packaged)."""

from __future__ import annotations

try:
    from labdesk_ui._build_version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "dev"


def user_agent() -> str:
    return f"LabDesk/{APP_VERSION}"
