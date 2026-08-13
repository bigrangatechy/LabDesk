"""Theme palette completeness (dark mode secondary text)."""

from __future__ import annotations

from PySide6.QtGui import QPalette

from labdesk_ui.utils.theme import _dark_palette, apply_theme


def test_dark_palette_mid_is_light_enough_for_secondary_text(qapp):
    """``palette(mid)`` labels must not stay near-black after switching dark."""
    apply_theme("dark")
    mid = qapp.palette().color(QPalette.ColorRole.Mid)
    window = qapp.palette().color(QPalette.ColorRole.Window)
    text = qapp.palette().color(QPalette.ColorRole.WindowText)
    assert text.lightness() > window.lightness()
    assert mid.lightness() > 100
    assert mid.lightness() < text.lightness()


def test_dark_palette_helper_sets_stylesheet_roles():
    p = _dark_palette()
    for role in (
        QPalette.ColorRole.Mid,
        QPalette.ColorRole.Light,
        QPalette.ColorRole.Dark,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        assert p.color(role).isValid()


def test_apply_theme_light_then_dark_updates_app_palette(qapp):
    apply_theme("light")
    light_mid = qapp.palette().color(QPalette.ColorRole.Mid).lightness()
    apply_theme("dark")
    dark_window = qapp.palette().color(QPalette.ColorRole.Window).lightness()
    dark_text = qapp.palette().color(QPalette.ColorRole.WindowText).lightness()
    assert dark_window < 80
    assert dark_text > 180
    # Mid must move with the theme (not stuck on the prior light value alone).
    dark_mid = qapp.palette().color(QPalette.ColorRole.Mid).lightness()
    assert dark_mid != light_mid or dark_mid > 100
