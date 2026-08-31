"""Slice J admin/runners capabilities and UI smoke."""

from __future__ import annotations

import sys
import types

import pytest

from labdesk_ui.plugins.admin_view import AdminView, _runner_row_text, _user_row_text
from labdesk_ui.plugins import ensure_builtin_views, get_view


def _core_for_patch(monkeypatch):
    try:
        import labdesk_core

        return labdesk_core
    except ImportError:
        mod = types.ModuleType("labdesk_core")
        monkeypatch.setitem(sys.modules, "labdesk_core", mod)
        return mod


def test_forge_matrix_includes_runner_caps():
    labdesk_core = pytest.importorskip("labdesk_core")
    if not hasattr(labdesk_core, "forge_feature_matrix"):
        pytest.skip("labdesk_core extension not built")
    matrix = labdesk_core.forge_feature_matrix()
    assert matrix["gitlab"]["supports_runners"] is True
    assert matrix["gitlab"]["supports_runner_pause"] is True
    assert matrix["gitlab"]["supports_runner_delete"] is True
    assert matrix["gitea"]["supports_runner_pause"] is True
    assert matrix["forgejo"]["supports_runners"] is True
    assert matrix["onedev"]["supports_runners"] is True
    assert matrix["onedev"]["supports_runner_pause"] is False
    assert matrix["onedev"]["supports_runner_delete"] is False
    assert matrix["onedev"]["runners_label"] == "Agents"


def test_admin_view_registered():
    ensure_builtin_views()
    view = get_view("admin")
    assert view is not None
    assert view.title == "Admin"


def test_admin_view_smoke(qapp, monkeypatch):
    ensure_builtin_views()
    labdesk_core = _core_for_patch(monkeypatch)

    class Ctx:
        def switch_view(self, _vid, persist=True):
            pass

        def set_status(self, _t):
            pass

        def set_detail(self, _t):
            pass

    def immediate(parent, work, on_success=None, on_error=None, **_kw):
        try:
            result = work()
            if on_success:
                on_success(result)
        except Exception as exc:
            if on_error:
                on_error("LD-TEST", str(exc), exc)

    monkeypatch.setattr(
        "labdesk_ui.utils.async_jobs.run_in_background", immediate
    )
    monkeypatch.setattr(
        labdesk_core,
        "list_instance_runners",
        lambda: [
            {
                "id": "1",
                "description": "docker",
                "active": True,
                "online": True,
                "paused": False,
                "tag_list": ["linux"],
                "scope": "instance",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(labdesk_core, "list_admin_users", lambda: [], raising=False)
    monkeypatch.setattr(
        labdesk_core,
        "active_forge_info",
        lambda: {
            "display_name": "GitLab",
            "runners_label": "Runners",
            "supports_runner_pause": True,
            "supports_runner_delete": True,
            "open_in_label": "Open in GitLab",
        },
        raising=False,
    )
    w = AdminView(None, Ctx())
    w.on_activated()
    assert w.tabs.count() == 2
    assert not w.btn_pause.isHidden()
    assert not w.btn_delete.isHidden()
    assert w.runners.count() == 1
    w.close()


def test_runner_and_user_row_text():
    assert "docker" in _runner_row_text(
        {"id": "9", "description": "docker", "online": True, "active": True}
    )
    assert "admin" in _user_row_text(
        {"username": "root", "name": "Root", "is_admin": True}
    )
