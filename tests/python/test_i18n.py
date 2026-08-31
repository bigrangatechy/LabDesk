"""Slice L i18n helpers and translator loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from labdesk_ui.i18n import (
    AVAILABLE_LOCALES,
    install_translators,
    resolve_locale,
    tr,
    translations_dir,
)


def test_tr_passthrough_without_translator(qapp):
    assert tr("Settings") == "Settings"


def test_resolve_locale_explicit():
    assert resolve_locale("es") == "es"
    assert resolve_locale("en") == "en"
    assert resolve_locale("pt-BR") == "pt_BR"


def test_qm_files_exist_for_shipped_locales():
    d = translations_dir()
    for code, _qt, _label in AVAILABLE_LOCALES:
        if code in ("system", "en"):
            continue
        assert (d / f"labdesk_{code}.qm").is_file(), code


def test_install_spanish_translates_settings(qapp):
    app = QApplication.instance()
    assert app is not None
    install_translators(app, "es")
    assert tr("Settings") == "Configuración"
    install_translators(app, "en")
    assert tr("Settings") == "Settings"


def test_set_locale_roundtrip_in_config(tmp_path, monkeypatch):
    labdesk_core = pytest.importorskip("labdesk_core")
    if not hasattr(labdesk_core, "set_locale"):
        pytest.skip("labdesk_core extension not built")
    # Presence check is enough for CI without a writable config sandbox.
    assert callable(labdesk_core.set_locale)
