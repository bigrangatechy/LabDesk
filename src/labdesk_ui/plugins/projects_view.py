"""Projects browser view plugin."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from labdesk_ui.plugins import AppContext, register_view
from labdesk_ui.utils.helpers import format_error


def filter_projects(projects: list, query: str) -> list:
    """Case-insensitive filter on name / namespace path fields."""
    q = (query or "").strip().lower()
    if not q:
        return list(projects)
    out = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        hay = " ".join(
            str(p.get(k) or "")
            for k in ("name", "name_with_namespace", "path_with_namespace")
        ).lower()
        if q in hay:
            out.append(p)
    return out


def pipeline_status_glyph(status: str | None) -> tuple[str, str]:
    """Return (glyph, tooltip) for a GitLab pipeline status string."""
    s = (status or "").strip().lower()
    if not s:
        return ("·", tr("No pipeline on default branch"))
    mapping = {
        "success": ("✓", "success"),
        "failed": ("✗", "failed"),
        "canceled": ("⊘", "canceled"),
        "cancelled": ("⊘", "canceled"),
        "running": ("●", "running"),
        "pending": ("○", "pending"),
        "created": ("○", "created"),
        "waiting_for_resource": ("○", "waiting for resource"),
        "preparing": ("○", "preparing"),
        "scheduled": ("○", "scheduled"),
        "manual": ("▶", "manual"),
        "skipped": ("–", "skipped"),
    }
    glyph, tip = mapping.get(s, ("?", s))
    return glyph, tip


def pipeline_status_color(status: str | None, *, dark: bool) -> QColor | None:
    """Foreground colour for the pipeline glyph (None = theme default)."""
    s = (status or "").strip().lower()
    if not s:
        return QColor(140, 140, 140) if dark else QColor(120, 120, 120)
    if s == "success":
        return QColor("#6bcf6b" if dark else "#0a7a0a")
    if s == "failed":
        return QColor("#f08080" if dark else "#a10a0a")
    if s in ("running", "pending", "created", "waiting_for_resource", "preparing", "scheduled"):
        return QColor("#7ec8e3" if dark else "#0a4a8a")
    if s == "manual":
        return QColor("#e0a040" if dark else "#8a5a00")
    if s in ("canceled", "cancelled", "skipped"):
        return QColor(160, 160, 160) if dark else QColor(110, 110, 110)
    return None


def parse_overlay_color(hex_color: str, alpha: int) -> QColor:
    """Build a QColor from `#RRGGBB` + alpha 0–255 (clamped)."""
    raw = (hex_color or "").strip()
    if not raw.startswith("#"):
        raw = f"#{raw}"
    color = QColor(raw)
    if not color.isValid():
        color = QColor("#2ecc71")
    color.setAlpha(max(0, min(255, int(alpha))))
    return color


def progress_fraction_from_snapshot(snap: dict | None) -> float:
    """Clamp progress fraction from core snapshot; 0 when inactive."""
    if not isinstance(snap, dict) or not snap.get("active"):
        return 0.0
    try:
        return max(0.0, min(1.0, float(snap.get("fraction") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


class _ProjectsTableModel(QAbstractTableModel):
    _HEADERS = (tr("CI"), tr("Project"), tr("Default branch"), tr("Visibility"), tr("Last activity"))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []
        self.progress_project_id: int | None = None
        self.progress_fraction: float = 0.0
        self.overlay_color = QColor(46, 204, 113, 70)

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def set_progress(
        self,
        project_id: int | None,
        fraction: float,
        overlay: QColor,
    ) -> None:
        self.progress_project_id = project_id
        self.progress_fraction = max(0.0, min(1.0, fraction))
        self.overlay_color = QColor(overlay)
        if self._rows:
            top = self.index(0, 0)
            bottom = self.index(len(self._rows) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom, [])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        p = self._rows[index.row()]
        col = index.column()
        status = p.get("pipeline_status") if isinstance(p, dict) else None
        glyph, tip = pipeline_status_glyph(status if isinstance(status, str) else None)

        if col == 0:
            if role == Qt.ItemDataRole.DisplayRole:
                return glyph
            if role == Qt.ItemDataRole.ToolTipRole:
                return tip
            if role == Qt.ItemDataRole.ForegroundRole:
                dark = False
                try:
                    from PySide6.QtGui import QPalette
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
                    if app is not None:
                        dark = (
                            app.palette().color(QPalette.ColorRole.Window).lightness()
                            < 128
                        )
                except Exception:
                    dark = False
                return pipeline_status_color(
                    status if isinstance(status, str) else None, dark=dark
                )
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                return p.get("name_with_namespace") or p.get("name") or ""
            if col == 2:
                return p.get("default_branch") or ""
            if col == 3:
                return p.get("visibility") or ""
            if col == 4:
                return p.get("last_activity_at") or ""
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._HEADERS[section]
        return str(section + 1)

    def project_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._rows):
            p = self._rows[row]
            return p if isinstance(p, dict) else None
        return None


class _ProgressRowDelegate(QStyledItemDelegate):
    """Paint a translucent left→right fill behind the active clone/push row."""

    def __init__(self, model: _ProjectsTableModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        project = self._model.project_at(index.row())
        pid = project.get("project_id") if isinstance(project, dict) else None
        if (
            pid is not None
            and self._model.progress_project_id is not None
            and int(pid) == int(self._model.progress_project_id)
            and self._model.progress_fraction > 0
            and index.column() == 0
        ):
            view = option.widget
            if isinstance(view, QTableView):
                left = view.visualRect(self._model.index(index.row(), 0)).left()
                right = view.visualRect(
                    self._model.index(index.row(), self._model.columnCount() - 1)
                ).right()
                row_rect = QRect(
                    left,
                    option.rect.top(),
                    max(1, right - left + 1),
                    option.rect.height(),
                )
                fill_w = int(row_rect.width() * self._model.progress_fraction)
                painter.save()
                painter.fillRect(
                    QRect(row_rect.left(), row_rect.top(), fill_w, row_rect.height()),
                    self._model.overlay_color,
                )
                painter.restore()
        super().paint(painter, option, index)


class _ProjectCard(QFrame):
    clicked = Signal(object)
    double_clicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(88)
        self._project: dict | None = None
        self._fraction = 0.0
        self._overlay = QColor(46, 204, 113, 70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        top = QHBoxLayout()
        self.ci = QLabel(tr("·"))
        self.ci.setFixedWidth(20)
        top.addWidget(self.ci)
        self.title = QLabel("")
        self.title.setWordWrap(True)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        top.addWidget(self.title, stretch=1)
        layout.addLayout(top)
        self.path = QLabel("")
        self.path.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.path)
        self.branch = QLabel("")
        self.branch.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.branch)
        self.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 6px; }")

    def set_project(self, project: dict) -> None:
        self._project = project
        status = project.get("pipeline_status")
        glyph, tip = pipeline_status_glyph(status if isinstance(status, str) else None)
        self.ci.setText(glyph)
        self.ci.setToolTip(tip)
        self.title.setText(str(project.get("name") or project.get("path_with_namespace") or ""))
        self.path.setText(str(project.get("path_with_namespace") or ""))
        branch = project.get("default_branch") or ""
        self.branch.setText(f"default: {branch}" if branch else "")

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(
                "QFrame { border: 2px solid palette(highlight); border-radius: 6px; }"
            )
        else:
            self.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 6px; }")
        self.update()

    def set_progress(self, fraction: float, overlay: QColor) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._overlay = QColor(overlay)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._fraction > 0:
            painter = QPainter(self)
            w = int(self.width() * self._fraction)
            painter.fillRect(0, 0, w, self.height(), self._overlay)
            painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._project is not None:
            self.clicked.emit(self._project)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._project is not None:
            self.double_clicked.emit(self._project)
        super().mouseDoubleClickEvent(event)


class ProjectsView(QWidget):
    def __init__(self, parent: QWidget, ctx: AppContext) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._all_projects: list = []
        self._layout_mode = "table"
        self._overlay_color = QColor(46, 204, 113, 70)
        self._selected_project_id: int | None = None
        self._cards: list[_ProjectCard] = []
        self._git_busy = False

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._poll_git_progress)

        layout = QVBoxLayout(self)

        self.projects_meta = QLabel(tr("Projects"))
        layout.addWidget(self.projects_meta)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("Filter projects…"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._on_filter_text_changed)
        layout.addWidget(self.filter_edit)

        self._stack_host = QStackedWidget()
        self._layout_stack = self._stack_host

        self._model = _ProjectsTableModel(self)
        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setItemDelegate(_ProgressRowDelegate(self._model, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 180)
        self.table.doubleClicked.connect(lambda _idx: self._open_local_repo())
        self.table.selectionModel().selectionChanged.connect(self._on_table_selection)
        self._layout_stack.addWidget(self.table)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(4, 4, 4, 4)
        self.cards_grid.setSpacing(8)
        self.cards_scroll.setWidget(self.cards_host)
        self._layout_stack.addWidget(self.cards_scroll)

        layout.addWidget(self._layout_stack, stretch=1)

        row = QHBoxLayout()
        self.btn_connect = QPushButton(tr("Add host / account…"))
        self.btn_connect.clicked.connect(self._ctx.show_connect_dialog)
        row.addWidget(self.btn_connect)

        self.btn_refresh_user = QPushButton(tr("Refresh user"))
        self.btn_refresh_user.clicked.connect(self._ctx.refresh_connection_banner)
        row.addWidget(self.btn_refresh_user)

        self.btn_refresh_projects = QPushButton(tr("Refresh projects"))
        self.btn_refresh_projects.clicked.connect(self._refresh_projects)
        row.addWidget(self.btn_refresh_projects)

        self.btn_open_local = QPushButton(tr("Open local"))
        self.btn_open_local.clicked.connect(self._open_local_repo)
        row.addWidget(self.btn_open_local)

        self.btn_add_existing = QPushButton(tr("Add existing…"))
        self.btn_add_existing.clicked.connect(self._add_existing_clone)
        row.addWidget(self.btn_add_existing)

        self.btn_open = QPushButton(tr("Open in browser"))
        self.btn_open.clicked.connect(self._open_in_browser)
        row.addWidget(self.btn_open)

        self.btn_clone = QPushButton(tr("Clone"))
        self.btn_clone.clicked.connect(lambda: self._clone_with_transport("https"))
        row.addWidget(self.btn_clone)

        self.btn_clone_ssh = QPushButton(tr("Clone (SSH)"))
        self.btn_clone_ssh.clicked.connect(lambda: self._clone_with_transport("ssh"))
        row.addWidget(self.btn_clone_ssh)

        layout.addLayout(row)
        self.apply_prefs()

    def on_activated(self) -> None:
        self.apply_prefs()
        self._load_cached_projects()
        if hasattr(self._ctx, "is_network_available"):
            self.set_network_available(self._ctx.is_network_available())
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    def on_deactivated(self) -> None:
        if not self._git_busy:
            self._progress_timer.stop()

    def apply_prefs(self) -> None:
        """Reload layout + overlay colour from config (Settings save / activate)."""
        layout_mode = "table"
        color = "#2ecc71"
        alpha = 70
        try:
            import labdesk_core

            general = (labdesk_core.load_config() or {}).get("general") or {}
            layout_mode = str(general.get("projects_layout") or "table")
            color = str(general.get("progress_overlay_color") or "#2ecc71")
            alpha = int(general.get("progress_overlay_alpha") or 70)
        except Exception:
            pass
        self._overlay_color = parse_overlay_color(color, alpha)
        self._set_layout_mode(layout_mode)
        self._model.set_progress(
            self._model.progress_project_id,
            self._model.progress_fraction,
            self._overlay_color,
        )
        self._sync_card_progress()

    def _set_layout_mode(self, mode: str) -> None:
        mode = mode if mode in ("table", "cards") else "table"
        self._layout_mode = mode
        show_cards = mode == "cards"
        self._layout_stack.setCurrentWidget(
            self.cards_scroll if show_cards else self.table
        )
        if show_cards:
            self._rebuild_cards(filter_projects(self._all_projects, self.filter_edit.text()))

    def set_network_available(self, available: bool) -> None:
        self.btn_refresh_projects.setEnabled(available)
        self.btn_refresh_user.setEnabled(True)
        self.btn_clone.setEnabled(available and not self._git_busy)
        self.btn_clone_ssh.setEnabled(available and not self._git_busy)
        tip = tr("Working offline — refresh disabled.") if not available else ""
        self.btn_refresh_projects.setToolTip(tip)
        self.btn_clone.setToolTip(tip)
        self.btn_clone_ssh.setToolTip(tip)
        if not available:
            text = self.projects_meta.text()
            if "offline" not in text.lower():
                self.projects_meta.setText(f"{text} · offline (cached)")

    def _selected_project(self) -> dict | None:
        if self._layout_mode == "cards":
            if self._selected_project_id is None:
                return None
            for p in self._all_projects:
                if isinstance(p, dict) and p.get("project_id") == self._selected_project_id:
                    return p
            return None
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._model.project_at(indexes[0].row())

    def _on_table_selection(self, *_args) -> None:
        project = None
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            project = self._model.project_at(indexes[0].row())
        pid = project.get("project_id") if isinstance(project, dict) else None
        self._selected_project_id = int(pid) if pid is not None else None

    def _on_card_clicked(self, project: dict) -> None:
        pid = project.get("project_id")
        self._selected_project_id = int(pid) if pid is not None else None
        for card in self._cards:
            selected = (
                card._project is not None
                and card._project.get("project_id") == self._selected_project_id
            )
            card.set_selected(selected)

    def _on_filter_text_changed(self, _text: str = "") -> None:
        self._filter_timer.start()

    def _load_cached_projects(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            cfg = labdesk_core.load_config()
            if not (cfg.get("accounts") or cfg.get("instances")):
                return {"projects": [], "empty": True}
            projects = labdesk_core.list_projects()
            return {
                "projects": [dict(p) if hasattr(p, "items") else p for p in (projects or [])],
                "empty": False,
            }

        def on_ok(data) -> None:
            if (data or {}).get("empty"):
                self._all_projects = []
                self._model.set_rows([])
                self._rebuild_cards([])
                self.projects_meta.setText(tr("Projects (none — connect a host/account)"))
                return
            self._all_projects = (data or {}).get("projects") or []
            self._apply_filter()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self.projects_meta.setText(f"Projects — [{code}] {msg}")
            self._all_projects = []
            self._model.set_rows([])
            self._rebuild_cards([])

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            status=self._ctx.set_detail,
            working_message=tr("Loading projects…"),
        )

    def _apply_filter(self, _text: str = "") -> None:
        filtered = filter_projects(self._all_projects, self.filter_edit.text())
        self._model.set_rows(filtered)
        if self._layout_mode == "cards":
            self._rebuild_cards(filtered)
        total = len(self._all_projects)
        shown = len(filtered)
        fetched = None
        if self._all_projects:
            fetched = self._all_projects[0].get("fetched_at")
        q = self.filter_edit.text().strip()
        if q:
            meta = f"Projects (showing {shown} of {total}"
        else:
            meta = f"Projects ({total} cached"
        if fetched:
            meta += f", fetched_at {fetched}"
        meta += ")"
        if hasattr(self._ctx, "is_network_available") and not self._ctx.is_network_available():
            if "offline" not in meta.lower():
                meta += " · offline (cached)"
        self.projects_meta.setText(meta)

    def _rebuild_cards(self, projects: list) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = []
        cols = max(1, self.cards_scroll.viewport().width() // 260) if self.cards_scroll.width() else 2
        for i, project in enumerate(projects):
            if not isinstance(project, dict):
                continue
            card = _ProjectCard(self.cards_host)
            card.set_project(project)
            pid = project.get("project_id")
            card.set_selected(
                pid is not None
                and self._selected_project_id is not None
                and int(pid) == self._selected_project_id
            )
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(lambda _p: self._open_local_repo())
            if (
                self._model.progress_project_id is not None
                and pid is not None
                and int(pid) == int(self._model.progress_project_id)
            ):
                card.set_progress(self._model.progress_fraction, self._overlay_color)
            else:
                card.set_progress(0.0, self._overlay_color)
            r, c = divmod(i, cols)
            self.cards_grid.addWidget(card, r, c)
            self._cards.append(card)
        self.cards_grid.setRowStretch((len(projects) // cols) + 1, 1)

    def _sync_card_progress(self) -> None:
        for card in self._cards:
            project = card._project
            pid = project.get("project_id") if isinstance(project, dict) else None
            if (
                pid is not None
                and self._model.progress_project_id is not None
                and int(pid) == int(self._model.progress_project_id)
            ):
                card.set_progress(self._model.progress_fraction, self._overlay_color)
            else:
                card.set_progress(0.0, self._overlay_color)

    def _start_progress_poll(self) -> None:
        self._git_busy = True
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    def _stop_progress_poll(self) -> None:
        self._git_busy = False
        self._progress_timer.stop()
        self._model.set_progress(None, 0.0, self._overlay_color)
        self._sync_card_progress()
        self.table.viewport().update()

    def _poll_git_progress(self) -> None:
        try:
            import labdesk_core

            snap = labdesk_core.get_git_op_progress() or {}
        except Exception:
            return
        if not snap.get("active"):
            if self._model.progress_project_id is not None and not self._git_busy:
                self._model.set_progress(None, 0.0, self._overlay_color)
                self._sync_card_progress()
                self.table.viewport().update()
            return
        pid = snap.get("project_id")
        frac = progress_fraction_from_snapshot(snap)
        self._model.set_progress(
            int(pid) if pid is not None else None,
            frac,
            self._overlay_color,
        )
        self._sync_card_progress()
        self.table.viewport().update()
        kind = snap.get("kind") or "git"
        pct = int(frac * 100)
        self._ctx.set_detail(f"{kind.capitalize()}… {pct}%")

    def _refresh_projects(self) -> None:
        from labdesk_ui.utils.async_jobs import run_in_background

        def work():
            import labdesk_core

            return labdesk_core.refresh_projects()

        def on_ok(result) -> None:
            count = result.get("count", 0) if isinstance(result, dict) else 0
            self._ctx.set_detail(f"Refreshed {count} projects from API.")
            if hasattr(self._ctx, "set_network_available"):
                self._ctx.set_network_available(True)
            self._load_cached_projects()

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._ctx.set_detail(f"[{code}] {msg} — showing cache if available.")
            self._load_cached_projects()
            if code == "LD-NET-001" or code.startswith("LD-NET"):
                if hasattr(self._ctx, "set_network_available"):
                    self._ctx.set_network_available(False, detail=str(exc))
                return
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_refresh_projects, self.btn_clone, self.btn_clone_ssh],
            status=self._ctx.set_detail,
            working_message=tr("Refreshing projects (and pipeline status)…"),
        )

    def _open_in_browser(self) -> None:
        project = self._selected_project()
        if not project:
            return
        web = project.get("web_url")
        if not web:
            QMessageBox.information(self, tr("Open"), tr("No web URL for this project."))
            return
        QDesktopServices.openUrl(QUrl(web))

    def _open_local_repo(self) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, tr("Open"), tr("Select a project first."))
            return
        project_id = project.get("project_id")
        if project_id is None:
            return
        try:
            import labdesk_core

            info = labdesk_core.find_local_repo(int(project_id))
            if not info.get("found") or not info.get("exists"):
                reply = QMessageBox.question(
                    self,
                    tr("Open local"),
                    tr("No registered clone for this project.\n\n"
                    "Add an existing folder now?"),
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._add_existing_clone()
                return
            path = info.get("path")
            if info.get("source") == "discovered":
                self._ctx.set_detail(f"Found existing clone at {path}")
            title = project.get("path_with_namespace") or path
            self._ctx.open_repo_window(path, title=f"LabDesk — {title}")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _add_existing_clone(self) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, tr("Add existing"), tr("Select a project first."))
            return
        project_id = project.get("project_id")
        if project_id is None:
            return

        start = ""
        try:
            import labdesk_core

            start = (labdesk_core.get_default_clone_dir().get("expanded") or "")
        except Exception:
            start = ""

        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("Select existing clone folder"),
            start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen:
            return

        try:
            import labdesk_core

            result = labdesk_core.register_local_repo(int(project_id), chosen)
            path = result.get("path") or chosen
            self._ctx.set_detail(f"Registered existing clone: {path}")
            title = project.get("path_with_namespace") or path
            reply = QMessageBox.question(
                self,
                tr("Add existing"),
                f"Registered:\n{path}\n\nOpen it now?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._ctx.open_repo_window(path, title=f"LabDesk — {title}")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _clone_with_transport(self, transport: str) -> None:
        project = self._selected_project()
        if not project:
            QMessageBox.information(self, tr("Clone"), tr("Select a project first."))
            return
        project_id = project.get("project_id")
        if project_id is None:
            QMessageBox.warning(self, tr("Clone"), tr("Selected project has no id."))
            return

        name = project.get("path_with_namespace") or project.get("name") or str(project_id)
        reply = QMessageBox.question(
            self,
            tr("Clone"),
            f"Clone {name} via {transport.upper()} into the clone folder?\n"
            "(If a clone already exists there, LabDesk will use it.)",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_clone.setEnabled(False)
        self.btn_clone_ssh.setEnabled(False)
        self._ctx.set_detail(f"Cloning {name} ({transport})…")
        self._start_progress_poll()
        self._model.set_progress(int(project_id), 0.02, self._overlay_color)
        self._sync_card_progress()

        from labdesk_ui.utils.async_jobs import run_in_background

        pid = int(project_id)

        def work():
            import labdesk_core

            return labdesk_core.clone_project(pid, transport)

        def on_ok(result) -> None:
            self._stop_progress_poll()
            path = result.get("path") if isinstance(result, dict) else None
            if isinstance(result, dict) and result.get("adopted_existing"):
                self._ctx.set_detail(f"Using existing clone at {path}")
                QMessageBox.information(
                    self,
                    tr("Existing clone"),
                    f"A git repository was already at:\n{path}\n\n"
                    "It has been registered with this project.",
                )
            else:
                self._ctx.set_detail(f"Cloned to {path}")
                QMessageBox.information(self, tr("Clone"), f"Cloned to:\n{path}")

        def on_err(code: str, msg: str, exc: BaseException) -> None:
            self._stop_progress_poll()
            self._ctx.set_detail(f"[{code}] {msg}")
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

        run_in_background(
            self,
            work,
            on_success=on_ok,
            on_error=on_err,
            busy_widgets=[self.btn_clone, self.btn_clone_ssh, self.btn_refresh_projects],
            status=self._ctx.set_detail,
            working_message=f"Cloning {name} ({transport})…",
        )


def _factory(parent: QWidget, ctx: AppContext) -> QWidget:
    return ProjectsView(parent, ctx)


register_view("projects", tr("Projects"), _factory, order=10)
