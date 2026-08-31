"""LabDesk i18n — Qt Linguist (QTranslator + .qm).

Source strings stay English in code via ``tr("…")``. Locale catalogs live
under ``labdesk_ui/i18n/qm/``. Rebuild with ``scripts/build_translations.py``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

# (config value, Qt language, display name in English)
AVAILABLE_LOCALES: list[tuple[str, str, str]] = [
    ("system", "", "System default"),
    ("en", "en_US", "English"),
    ("es", "es_ES", "Español"),
    ("de", "de_DE", "Deutsch"),
    ("fr", "fr_FR", "Français"),
    ("pt_BR", "pt_BR", "Português (Brasil)"),
]

_CONTEXT = "labdesk"
_installed: list[QTranslator] = []


def tr(source: str) -> str:
    """Translate a UI source string (English msgid)."""
    return QCoreApplication.translate(_CONTEXT, source)


def translations_dir() -> Path:
    return Path(__file__).resolve().parent / "qm"


def resolve_locale(pref: str | None) -> str:
    """Return concrete language code for loading (``en`` means no .qm)."""
    pref = (pref or "system").strip() or "system"
    if pref == "system":
        sys_name = QLocale.system().name()  # e.g. es_ES
        for code, qt_name, _label in AVAILABLE_LOCALES:
            if code in ("system", "en"):
                continue
            if sys_name == qt_name or sys_name.startswith(code + "_") or sys_name == code:
                return code
        # pt_BR special
        if sys_name.startswith("pt"):
            return "pt_BR"
        return "en"
    if pref == "pt-BR":
        return "pt_BR"
    return pref


def install_translators(app: QApplication | None = None, locale_pref: str | None = None) -> str:
    """Install/replace LabDesk translators. Returns the effective language code."""
    global _installed
    app = app or QApplication.instance()
    if app is None:
        return "en"

    for t in _installed:
        app.removeTranslator(t)
    _installed = []

    if locale_pref is None:
        locale_pref = "system"
        try:
            import labdesk_core

            general = (labdesk_core.load_config() or {}).get("general") or {}
            locale_pref = str(general.get("locale") or "system")
        except Exception:
            locale_pref = "system"

    effective = resolve_locale(locale_pref)
    if effective == "en":
        return effective

    qm = translations_dir() / f"labdesk_{effective}.qm"
    if not qm.is_file():
        return "en"

    translator = QTranslator(app)
    if translator.load(str(qm)):
        app.installTranslator(translator)
        _installed.append(translator)
        return effective
    return "en"


def locale_display_choices() -> list[tuple[str, str]]:
    """Return ``(config_value, label)`` for Settings combo."""
    return [(code, label) for code, _qt, label in AVAILABLE_LOCALES]
