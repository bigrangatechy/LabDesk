"""Reusable UI widgets (from-scratch editor chrome, etc.)."""

from labdesk_ui.widgets.code_editor import EditorWindow, open_code_editor
from labdesk_ui.widgets.diff_view import DiffView

__all__ = ["DiffView", "EditorWindow", "open_code_editor"]
