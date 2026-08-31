"""Pluggable UI views for LabDesk.

Views register with the global registry and can be swapped in the main
window (and later other hosts) without rewriting the shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from PySide6.QtWidgets import QWidget


class AppContext(Protocol):
    """Minimal host API plugins can rely on."""

    def set_status(self, text: str) -> None: ...
    def set_detail(self, text: str) -> None: ...
    def open_repo_window(self, path: str, title: str | None = None) -> None: ...
    def show_connect_dialog(self, *, mode: str | None = None) -> None: ...
    def refresh_connection_banner(self) -> None: ...
    def switch_view(self, view_id: str, *, persist: bool = True) -> None: ...


class ViewPlugin(Protocol):
    id: str
    title: str
    order: int

    def create_widget(self, parent: QWidget, ctx: AppContext) -> QWidget: ...

    def on_activated(self) -> None:
        """Called when the view becomes visible."""

    def on_deactivated(self) -> None:
        """Called when leaving the view."""


@dataclass
class RegisteredView:
    id: str
    title: str
    order: int
    factory: Callable[[QWidget, AppContext], QWidget]


_REGISTRY: dict[str, RegisteredView] = {}


def register_view(
    view_id: str,
    title: str,
    factory: Callable[[QWidget, AppContext], QWidget],
    *,
    order: int = 100,
) -> None:
    _REGISTRY[view_id] = RegisteredView(
        id=view_id, title=title, order=order, factory=factory
    )


def unregister_view(view_id: str) -> None:
    _REGISTRY.pop(view_id, None)


def get_view(view_id: str) -> RegisteredView | None:
    return _REGISTRY.get(view_id)


def list_views() -> list[RegisteredView]:
    return sorted(_REGISTRY.values(), key=lambda v: (v.order, v.title.lower()))


def ensure_builtin_views() -> None:
    """Import built-in plugins so they register themselves."""
    # Local imports avoid cycles at package import time.
    from labdesk_ui.plugins import admin_view as _admin  # noqa: F401
    from labdesk_ui.plugins import projects_view as _projects  # noqa: F401
    from labdesk_ui.plugins import settings_view as _settings  # noqa: F401
