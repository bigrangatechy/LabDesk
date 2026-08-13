"""YAML / packaging sanity checks (no Qt)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_gitlab_ci_yaml_parses():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    assert "stages" in data
    assert "flatpak_build_publish" in data


def test_flatpak_manifest_has_labdesk_version_env():
    text = (ROOT / "flatpak/com.bigrangatech.LabDesk.yml").read_text()
    assert "LABDESK_VERSION:" in text
    assert "--share=network" in text


def test_metainfo_has_release_placeholder():
    text = (ROOT / "flatpak/com.bigrangatech.LabDesk.metainfo.xml").read_text()
    assert "LABDESK_RELEASE_PLACEHOLDER" in text or "<release " in text
