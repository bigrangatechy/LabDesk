"""Regression tests for projects layout helpers and progress overlay math."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from labdesk_ui.plugins.projects_view import (
    filter_projects,
    parse_overlay_color,
    progress_fraction_from_snapshot,
)


def test_parse_overlay_color_applies_alpha_and_hex():
    c = parse_overlay_color("#2ecc71", 70)
    assert c.isValid()
    assert c.red() == 0x2E
    assert c.green() == 0xCC
    assert c.blue() == 0x71
    assert c.alpha() == 70


def test_parse_overlay_color_clamps_alpha_and_falls_back():
    assert parse_overlay_color("#ff0000", 999).alpha() == 255
    assert parse_overlay_color("#00ff00", -3).alpha() == 0
    bad = parse_overlay_color("not-a-color", 40)
    assert bad.isValid()
    assert bad.name() == QColor("#2ecc71").name()
    assert bad.alpha() == 40


def test_progress_fraction_inactive_is_zero():
    assert progress_fraction_from_snapshot(None) == 0.0
    assert progress_fraction_from_snapshot({}) == 0.0
    assert progress_fraction_from_snapshot({"active": False, "fraction": 0.9}) == 0.0


def test_progress_fraction_clamps_active_values():
    assert progress_fraction_from_snapshot({"active": True, "fraction": 0.42}) == 0.42
    assert progress_fraction_from_snapshot({"active": True, "fraction": 1.5}) == 1.0
    assert progress_fraction_from_snapshot({"active": True, "fraction": -1}) == 0.0
    assert progress_fraction_from_snapshot({"active": True, "fraction": "nope"}) == 0.0


def test_layout_mode_toggle_shows_cards_or_table(qapp, monkeypatch, process_events):
    """Switching projects_layout must flip visibility (would catch a no-op toggle)."""
    from labdesk_ui.plugins.projects_view import ProjectsView

    class Ctx:
        def set_status(self, text: str) -> None:
            pass

        def set_detail(self, text: str) -> None:
            pass

        def open_repo_window(self, path: str, title: str | None = None) -> None:
            pass

        def show_connect_dialog(self, *, mode: str | None = None) -> None:
            pass

        def refresh_connection_banner(self) -> None:
            pass

        def switch_view(self, view_id: str, *, persist: bool = True) -> None:
            pass

        def is_network_available(self) -> bool:
            return True

    monkeypatch.setattr(
        "labdesk_core.load_config",
        lambda: {
            "general": {
                "projects_layout": "table",
                "progress_overlay_color": "#2ecc71",
                "progress_overlay_alpha": 70,
            }
        },
        raising=False,
    )

    # Import may fail if labdesk_core missing; patch at module use sites.
    import labdesk_ui.plugins.projects_view as pv

    class FakeCore:
        @staticmethod
        def load_config():
            return {
                "general": {
                    "projects_layout": FakeCore.layout,
                    "progress_overlay_color": "#ff0000",
                    "progress_overlay_alpha": 90,
                }
            }

    FakeCore.layout = "table"

    monkeypatch.setattr(pv, "labdesk_core", FakeCore, raising=False)

    # apply_prefs imports labdesk_core inside the method — patch sys.modules style
    import sys
    import types

    fake = types.ModuleType("labdesk_core")
    fake.load_config = FakeCore.load_config
    monkeypatch.setitem(sys.modules, "labdesk_core", fake)

    parent = QWidget()
    view = ProjectsView(parent, Ctx())
    parent.show()
    view.show()
    process_events()
    assert view._layout_stack.currentWidget() is view.table

    FakeCore.layout = "cards"
    view.apply_prefs()
    process_events()
    assert view._layout_stack.currentWidget() is view.cards_scroll
    assert view._layout_mode == "cards"
    assert view._overlay_color.alpha() == 90
    assert view._overlay_color.red() == 255

    view._all_projects = [
        {
            "project_id": 1,
            "name": "labdesk",
            "path_with_namespace": "Ranga/labdesk",
            "name_with_namespace": "Ranga / labdesk",
        },
        {
            "project_id": 2,
            "name": "other",
            "path_with_namespace": "Ranga/other",
            "name_with_namespace": "Ranga / other",
        },
    ]
    view.filter_edit.setText("labdesk")
    view._apply_filter()
    process_events()
    assert len(view._cards) == 1
    assert view._cards[0]._project["project_id"] == 1

    # Progress only on matching project id.
    view._model.set_progress(1, 0.5, view._overlay_color)
    view._sync_card_progress()
    assert view._cards[0]._fraction == 0.5

    parent.close()
    process_events(20)


def test_settings_save_reads_cards_item_data(qapp, monkeypatch, process_events):
    """Regression: currentData() None must not force table when Cards is selected."""
    from PySide6.QtWidgets import QComboBox

    box = QComboBox()
    box.addItem("Table", "table")
    box.addItem("Cards", "cards")
    box.setCurrentIndex(1)
    # Mimic a flaky currentData() while itemData stays correct.
    monkeypatch.setattr(box, "currentData", lambda *a, **k: None)
    choice = box.itemData(box.currentIndex())
    assert choice == "cards"
    assert str(choice or "table") == "cards"
    # The old expression would wrongly persist table:
    assert str(box.currentData() or "table") == "table"


def test_settings_save_snapshots_layout_before_shell_reload(qapp, monkeypatch, process_events):
    """Save must not re-read the combo after set_ui_shell triggers Settings._load."""
    from PySide6.QtWidgets import QMessageBox

    from labdesk_ui.plugins.settings_view import SettingsView

    saved: dict = {}

    class FakeCore:
        @staticmethod
        def load_config():
            return {
                "general": {
                    "theme": saved.get("theme", "system"),
                    "ui_shell": saved.get("shell", "classic"),
                    # Mid-save shell reload still sees disk table until set_projects_layout.
                    # After save, reflect what was persisted.
                    "projects_layout": saved.get("layout", "table"),
                    "progress_overlay_color": saved.get("color", "#2ecc71"),
                    "progress_overlay_alpha": saved.get("alpha", 70),
                    "check_for_updates": saved.get("updates", True),
                    "default_clone_dir": "~/Projects",
                }
            }

        @staticmethod
        def get_default_clone_dir():
            return {"expanded": "/tmp/projects", "stored": "~/Projects"}

        @staticmethod
        def get_paths():
            return {"config_toml": "/tmp/config.toml", "cache_db": "/tmp/cache.db"}

        @staticmethod
        def set_default_clone_dir(path):
            saved["clone"] = path

        @staticmethod
        def set_theme(theme):
            saved["theme"] = theme

        @staticmethod
        def set_ui_shell(shell):
            saved["shell"] = shell

        @staticmethod
        def set_projects_layout(layout):
            saved["layout"] = layout

        @staticmethod
        def set_progress_overlay(color, alpha):
            saved["color"] = color
            saved["alpha"] = alpha

        @staticmethod
        def set_check_for_updates(enabled):
            saved["updates"] = enabled

    class Ctx:
        def __init__(self):
            self.detail = ""
            self.shell_calls = 0

        def set_status(self, text: str) -> None:
            pass

        def set_detail(self, text: str) -> None:
            self.detail = text

        def open_repo_window(self, path: str, title: str | None = None) -> None:
            pass

        def show_connect_dialog(self, *, mode: str | None = None) -> None:
            pass

        def refresh_connection_banner(self) -> None:
            pass

        def switch_view(self, view_id: str, *, persist: bool = True) -> None:
            pass

        def set_ui_shell(self, shell: str, *, persist: bool = True) -> None:
            # Mimic MainWindow: re-activating Settings reloads from disk.
            # At this point layout is not yet written, so load still returns table.
            self.shell_calls += 1
            assert saved.get("layout") is None
            view._load()
            assert view.projects_layout.itemData(view.projects_layout.currentIndex()) == "table"

        def view_widget(self, view_id: str):
            return None

    import sys
    import types

    fake = types.ModuleType("labdesk_core")
    for name in dir(FakeCore):
        if not name.startswith("_"):
            setattr(fake, name, getattr(FakeCore, name))
    monkeypatch.setitem(sys.modules, "labdesk_core", fake)
    monkeypatch.setattr(
        "labdesk_ui.utils.theme.apply_theme", lambda theme: None, raising=False
    )

    ctx = Ctx()
    view = SettingsView(None, ctx)
    process_events()
    view.clone_dir.setText("/tmp/projects")
    view.projects_layout.blockSignals(True)
    view.projects_layout.setCurrentIndex(view.projects_layout.findData("cards"))
    view.projects_layout.blockSignals(False)
    assert view.projects_layout.itemData(view.projects_layout.currentIndex()) == "cards"

    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: None)
    )
    view._save()
    process_events()

    assert ctx.shell_calls >= 1
    assert saved.get("layout") == "cards", saved
    assert view.projects_layout.itemData(view.projects_layout.currentIndex()) == "cards"
    view.close()
    process_events(20)


def test_filter_still_works_with_cards_data():
    projects = [
        {"name": "a", "path_with_namespace": "ns/a", "name_with_namespace": "ns / a"},
        {"name": "b", "path_with_namespace": "ns/b", "name_with_namespace": "ns / b"},
    ]
    assert len(filter_projects(projects, "ns/a")) == 1
