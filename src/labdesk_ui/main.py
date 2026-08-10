#!/usr/bin/env python3
"""LabDesk application entrypoint — first vertical slice."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from labdesk_ui.windows.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("LabDesk")
    app.setOrganizationName("BigRanga Tech")
    app.setOrganizationDomain("bigrangatech.com")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
