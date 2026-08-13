"""Shared pytest fixtures for LabDesk UI tests (offscreen Qt)."""

from __future__ import annotations

import os

import pytest

# Must be set before QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def process_events(qapp):
    """Pump the Qt event loop briefly (queued signals, deleteLater, etc.)."""

    def _pump(rounds: int = 20) -> None:
        for _ in range(rounds):
            qapp.processEvents()

    return _pump
