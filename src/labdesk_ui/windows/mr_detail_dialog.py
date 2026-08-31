"""MR/PR detail, edit, merge, and read-only notes (V2)."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from labdesk_ui.utils.forge_labels import forge_info, open_in_label, pr_label
from labdesk_ui.utils.helpers import format_error
from labdesk_ui.utils.open_external import open_url

_NOTES_PAGE_SIZE = 50


def _format_notes(notes: list) -> str:
    if not notes:
        return "(no notes)"
    lines: list[str] = []
    for n in notes:
        author = (n or {}).get("author") or "?"
        when = (n or {}).get("created_at") or ""
        body = ((n or {}).get("body") or "").strip()
        lines.append(f"— {author}  {when}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


class MRDetailDialog(QDialog):
    def __init__(
        self,
        *,
        project_id: int,
        mr_iid: int,
        parent=None,
        kind_label: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_id = int(project_id)
        self.mr_iid = int(mr_iid)
        self._info = forge_info()
        self._kind = kind_label or pr_label(self._info)
        self.setWindowTitle(f"{self._kind} !{self.mr_iid}")
        self.resize(640, 720)
        self._notes_page = 1
        self._notes: list = []
        self._notes_may_have_more = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.target_edit = QLineEdit()
        self.meta = QLabel("")
        self.meta.setWordWrap(True)
        self.description = QTextEdit()
        form.addRow(tr("Title"), self.title_edit)
        form.addRow(tr("Source branch"), self.source_edit)
        form.addRow(tr("Target branch"), self.target_edit)
        form.addRow(tr("Meta"), self.meta)
        form.addRow(tr("Description"), self.description)
        layout.addLayout(form)

        layout.addWidget(QLabel(tr("Notes (read-only — replies are not posted from LabDesk)")))
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setFont(QFont("monospace"))
        layout.addWidget(self.notes, stretch=1)

        notes_row = QHBoxLayout()
        self.btn_notes = QPushButton(tr("Reload notes"))
        self.btn_notes.clicked.connect(lambda: self._load_notes(reset=True))
        notes_row.addWidget(self.btn_notes)
        self.btn_notes_more = QPushButton(tr("Load more notes"))
        self.btn_notes_more.clicked.connect(self._load_more_notes)
        self.btn_notes_more.setEnabled(False)
        notes_row.addWidget(self.btn_notes_more)
        notes_row.addStretch(1)
        layout.addLayout(notes_row)

        row = QHBoxLayout()
        self.btn_save = QPushButton(tr("Save metadata"))
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_save)
        self.btn_merge = QPushButton(tr("Merge…"))
        self.btn_merge.clicked.connect(self._merge)
        row.addWidget(self.btn_merge)
        self.btn_open = QPushButton(open_in_label(self._info))
        self.btn_open.clicked.connect(self._open_web)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._web_url: str | None = None
        self._apply_capability_ui()
        self._load()

    def _apply_capability_ui(self) -> None:
        info = self._info
        self.btn_save.setEnabled(bool(info.get("supports_mr_update", True)))
        self.btn_merge.setEnabled(bool(info.get("supports_mr_merge", True)))
        notes_ok = bool(info.get("supports_mr_notes", True))
        self.btn_notes.setEnabled(notes_ok)
        self.btn_notes_more.setEnabled(False)
        if not info.get("supports_mr_retarget", True):
            self.target_edit.setReadOnly(True)
            self.target_edit.setToolTip(
                f"{info.get('display_name') or 'This forge'} cannot change "
                "the target branch from LabDesk."
            )
        if not info.get("supports_mr_update", True):
            self.title_edit.setReadOnly(True)
            self.description.setReadOnly(True)
            self.btn_save.setToolTip(
                f"{info.get('display_name') or 'This forge'} cannot update "
                "MR/PR metadata from LabDesk."
            )
        if not info.get("supports_mr_merge", True):
            self.btn_merge.setToolTip(
                f"{info.get('display_name') or 'This forge'} cannot merge "
                "via API from LabDesk."
            )
        if not notes_ok:
            self.notes.setPlainText(
                f"{info.get('display_name') or 'This forge'} does not expose "
                "MR/PR notes to LabDesk."
            )

    def _load(self) -> None:
        try:
            import labdesk_core

            d = dict(labdesk_core.get_merge_request(self.project_id, self.mr_iid) or {})
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")
            return
        self.title_edit.setText(d.get("title") or "")
        self.source_edit.setText(d.get("source_branch") or "")
        self.target_edit.setText(d.get("target_branch") or "")
        self.description.setPlainText(d.get("description") or "")
        self._web_url = d.get("web_url") or None
        draft = "yes" if d.get("draft") else "no"
        state = (d.get("state") or "?").lower()
        self.meta.setText(
            f"State: {d.get('state') or '?'} · Author: {d.get('author') or '?'} · "
            f"Draft: {draft}"
        )
        # Merged / closed items should not offer merge again.
        can_merge = bool(self._info.get("supports_mr_merge", True)) and state in {
            "opened",
            "open",
        }
        self.btn_merge.setEnabled(can_merge)
        if self._info.get("supports_mr_notes", True):
            self._load_notes(reset=True)

    def _load_notes(self, *, reset: bool = True) -> None:
        if not self._info.get("supports_mr_notes", True):
            return
        if reset:
            self._notes_page = 1
            self._notes = []
        try:
            import labdesk_core

            batch = list(
                labdesk_core.list_merge_request_notes(
                    self.project_id, self.mr_iid, self._notes_page
                )
                or []
            )
        except Exception as exc:
            code, msg = format_error(exc)
            self.notes.setPlainText(f"[{code}] {msg}\n{exc}")
            self.btn_notes_more.setEnabled(False)
            return
        if reset:
            self._notes = batch
        else:
            self._notes.extend(batch)
        self._notes_may_have_more = len(batch) >= _NOTES_PAGE_SIZE
        self.btn_notes_more.setEnabled(self._notes_may_have_more)
        self.notes.setPlainText(_format_notes(self._notes))

    def _load_more_notes(self) -> None:
        if not self._notes_may_have_more:
            return
        self._notes_page += 1
        self._load_notes(reset=False)

    def _save(self) -> None:
        try:
            import labdesk_core

            labdesk_core.update_merge_request(
                self.project_id,
                self.mr_iid,
                self.title_edit.text().strip() or None,
                self.description.toPlainText(),
                self.target_edit.text().strip() or None,
            )
            self._load()
            QMessageBox.information(self, tr("Saved"), f"{self._kind} metadata updated.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _choose_merge_method(self) -> str | None:
        """Return ``\"default\"``, ``\"squash\"``, or ``None`` if cancelled."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(f"Merge {self._kind.lower()}")
        box.setText(f"Merge !{self.mr_iid} via the forge API?")
        box.setInformativeText(
            tr("Default uses the forge’s normal merge. Squash is the alternate "
            "safe option where the forge supports it "
            "(failures report as LD-API-MR-003).")
        )
        default_btn = box.addButton(
            tr("Merge (default)"), QMessageBox.ButtonRole.AcceptRole
        )
        squash_btn = box.addButton(tr("Squash…"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(default_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is default_btn:
            return "default"
        if clicked is squash_btn:
            return "squash"
        return None

    def _merge(self) -> None:
        choice = self._choose_merge_method()
        if choice is None:
            return
        method = None if choice == "default" else "squash"
        try:
            import labdesk_core

            labdesk_core.merge_merge_request(self.project_id, self.mr_iid, method)
            self._load()
            QMessageBox.information(self, tr("Merged"), f"!{self.mr_iid} merged.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _open_web(self) -> None:
        if not self._web_url:
            QMessageBox.information(self, open_in_label(self._info), tr("No web URL."))
            return
        try:
            open_url(self._web_url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")
