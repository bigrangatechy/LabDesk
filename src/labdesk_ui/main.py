#!/usr/bin/env python3
"""LabDesk application entrypoint."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from labdesk_ui import startup as startup_mod
    from labdesk_ui.windows.main_window import MainWindow

    recovery = startup_mod.consume_recovery_marker()
    startup_mod.arm_watchdog()
    startup_mod.set_step("qapplication")

    app = QApplication(sys.argv)
    app.setApplicationName("LabDesk")
    app.setOrganizationName("BigRanga Tech")
    app.setOrganizationDomain("bigrangatech.com")

    startup_mod.set_step("main_window")
    window = MainWindow()
    window._startup_recovery = recovery
    window.show()
    startup_mod.mark_ready()
    if recovery:
        QTimer.singleShot(0, window.show_startup_recovery_if_needed)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
