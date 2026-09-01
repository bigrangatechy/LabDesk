#!/usr/bin/env python3
"""LabDesk application entrypoint."""

from __future__ import annotations

from labdesk_ui.i18n import tr

import sys


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PySide6.QtGui import QAction

    from labdesk_ui import startup as startup_mod
    from labdesk_ui.utils.branding import app_icon
    from labdesk_ui.version import APP_VERSION
    from labdesk_ui.windows.main_window import MainWindow

    recovery = startup_mod.consume_recovery_marker()
    startup_mod.arm_watchdog()
    startup_mod.set_step("qapplication")

    app = QApplication(sys.argv)
    app.setApplicationName("LabDesk")
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName("com.bigrangatech.LabDesk")
    app.setOrganizationName("BigRanga Tech")
    app.setOrganizationDomain("bigrangatech.com")
    from labdesk_ui.utils.crash_report import install_crash_reporting

    install_crash_reporting()
    from labdesk_ui.i18n import install_translators

    install_translators(app)
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    startup_mod.set_step("main_window")
    window = MainWindow()
    window._startup_recovery = recovery
    if not icon.isNull():
        window.setWindowIcon(icon)

    def _drain_on_quit() -> None:
        from labdesk_ui.utils.async_jobs import drain_async_jobs

        def _views(owner) -> list:
            widgets = getattr(owner, "_view_widgets", None)
            if isinstance(widgets, dict):
                return list(widgets.values())
            if isinstance(widgets, (list, tuple)):
                return list(widgets)
            return []

        try:
            drain_async_jobs(window)
            for win in list(getattr(window, "_repo_windows", None) or []):
                try:
                    drain_async_jobs(win)
                except Exception:
                    pass
            for view in _views(window):
                try:
                    drain_async_jobs(view)
                except Exception:
                    pass
        except Exception:
            # Never block / abort quit because of drain bookkeeping.
            pass

    app.aboutToQuit.connect(_drain_on_quit)

    tray: QSystemTrayIcon | None = None
    if not icon.isNull() and QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(icon, app)
        tray.setToolTip(tr("LabDesk"))
        menu = QMenu()
        act_show = QAction(tr("Show LabDesk"), menu)
        act_show.triggered.connect(window.showNormal)
        act_show.triggered.connect(window.raise_)
        act_show.triggered.connect(window.activateWindow)
        menu.addAction(act_show)
        act_quit = QAction(tr("Quit"), menu)
        act_quit.triggered.connect(app.quit)
        menu.addAction(act_quit)
        tray.setContextMenu(menu)

        def _on_tray(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            ):
                window.showNormal()
                window.raise_()
                window.activateWindow()

        tray.activated.connect(_on_tray)
        tray.show()
        window._tray_icon = tray  # keep alive on the window

    window.show()
    startup_mod.mark_ready()
    if recovery:
        QTimer.singleShot(0, window.show_startup_recovery_if_needed)
    QTimer.singleShot(0, window.prompt_first_run_if_needed)
    QTimer.singleShot(1500, window.check_updates_on_startup_if_enabled)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
