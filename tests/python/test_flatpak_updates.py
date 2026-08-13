"""Flatpak update-check helpers (unpackaged path)."""

from __future__ import annotations

from labdesk_ui.utils.flatpak_updates import check_for_labdesk_updates, is_flatpak


def test_unpackaged_skips_host_flatpak_cli():
    # Pytest / run-labdesk.sh are not inside the Flatpak sandbox.
    assert is_flatpak() is False
    result = check_for_labdesk_updates()
    assert result["available"] is False
    assert result.get("skipped") is True
    assert "Not running as Flatpak" in (result.get("detail") or "")
