"""Forge picker + SaaS reject coverage for multi-forge connect."""

from __future__ import annotations

import pytest

from labdesk_ui.windows.instance_config import InstanceConfigDialog


def test_connect_dialog_lists_all_forges(qapp):
    dlg = InstanceConfigDialog()
    forges = [
        dlg.forge.itemData(i) for i in range(dlg.forge.count())
    ]
    assert forges == ["gitlab", "gitea", "forgejo", "onedev"]
    dlg.close()


def test_connect_dialog_values_include_forge(qapp):
    dlg = InstanceConfigDialog()
    dlg.host_name.setText("LAN OneDev")
    dlg.base_url.setText("http://192.168.0.50:6610")
    dlg.account_name.setText("me")
    dlg.pat.setText("token-value")
    idx = dlg.forge.findData("onedev")
    assert idx >= 0
    dlg.forge.setCurrentIndex(idx)
    vals = dlg.values()
    assert vals["forge"] == "onedev"
    assert vals["base_url"].startswith("http://192.168.0.50")
    dlg.close()


labdesk_core = pytest.importorskip("labdesk_core")
if not hasattr(labdesk_core, "validate_base_url"):
    pytest.skip(
        "labdesk_core extension module not built",
        allow_module_level=True,
    )


def _code(exc: BaseException) -> str:
    return (labdesk_core.parse_error_message(str(exc)).get("code") or "")


@pytest.mark.parametrize(
    "url",
    [
        "https://gitea.com",
        "https://codeberg.org",
        "https://code.onedev.io",
        "https://gitlab.com",
    ],
)
def test_saas_forges_rejected(url):
    with pytest.raises(Exception) as ei:
        labdesk_core.validate_base_url(url)
    assert _code(ei.value) == "LD-CFG-004"
