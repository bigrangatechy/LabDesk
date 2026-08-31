"""Shared pytest fixtures for LabDesk UI tests (offscreen Qt)."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Must be set before QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parents[2]
_SRC = (_ROOT / "src").resolve()
_CRATE = (_SRC / "labdesk_core").resolve()


class _MissingCoreLoader(importlib.abc.Loader):
    def create_module(self, spec):  # noqa: ANN001
        return None

    def exec_module(self, module):  # noqa: ANN001
        raise ImportError(
            "labdesk_core PyO3 extension is not built "
            "(src/labdesk_core on PYTHONPATH is the Rust crate, not the module)"
        )


class _PreferBuiltLabdeskCore(importlib.abc.MetaPathFinder):
    """Stop the Rust crate directory from registering as a namespace package.

    With ``PYTHONPATH=src``, PathFinder treats ``src/labdesk_core/`` as an
    empty namespace named ``labdesk_core``, which makes ``importorskip`` succeed
    in CI even though maturin never ran. Prefer a real extension from
    site-packages (or elsewhere); otherwise fail the import so tests skip.
    """

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001
        if fullname != "labdesk_core":
            return None
        for entry in list(sys.path):
            if not entry or entry == ".":
                continue
            try:
                resolved = Path(entry).resolve()
            except OSError:
                continue
            if resolved == _SRC or resolved == _CRATE:
                continue
            # Built extension (maturin): labdesk_core*.so / *.pyd next to site-packages.
            for suffix in importlib.machinery.EXTENSION_SUFFIXES:
                candidate = resolved / f"labdesk_core{suffix}"
                if candidate.is_file():
                    return importlib.util.spec_from_file_location(
                        "labdesk_core", candidate
                    )
            # Editable / package dir with a real __init__ (not the Rust crate).
            init = resolved / "labdesk_core" / "__init__.py"
            if init.is_file():
                return importlib.util.spec_from_file_location(
                    "labdesk_core",
                    init,
                    submodule_search_locations=[str(resolved / "labdesk_core")],
                )
        return importlib.machinery.ModuleSpec(
            fullname,
            _MissingCoreLoader(),
            origin="labdesk_core-extension-missing",
        )


def _install_labdesk_core_import_guard() -> None:
    mod = sys.modules.get("labdesk_core")
    if mod is not None:
        is_ns = getattr(mod, "__file__", None) is None and hasattr(mod, "__path__")
        built = hasattr(mod, "__version__") or hasattr(mod, "forge_feature_matrix")
        if is_ns or not built:
            paths = []
            for p in getattr(mod, "__path__", []) or []:
                try:
                    paths.append(Path(p).resolve())
                except OSError:
                    continue
            if is_ns or _CRATE in paths:
                del sys.modules["labdesk_core"]
    if not any(isinstance(f, _PreferBuiltLabdeskCore) for f in sys.meta_path):
        sys.meta_path.insert(0, _PreferBuiltLabdeskCore())


_install_labdesk_core_import_guard()


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
