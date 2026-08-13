"""Branding asset helpers."""

from __future__ import annotations

from labdesk_ui.utils.branding import app_icon, logo_svg_path, wordmark_svg_path


def test_logo_svg_present():
    path = logo_svg_path()
    assert path is not None
    assert path.name == "LabDesk-logo.svg"
    assert path.is_file()


def test_wordmark_svg_present():
    path = wordmark_svg_path()
    assert path is not None
    assert path.name == "LabDesk-logo-with-text.svg"
    assert path.is_file()


def test_app_icon_not_null(qapp):
    icon = app_icon()
    assert icon is not None
    assert not icon.isNull()
