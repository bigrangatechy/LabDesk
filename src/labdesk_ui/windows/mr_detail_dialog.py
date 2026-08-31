"""MR/PR detail, edit, merge, and read-only notes (V2)."""

from __future__ import annotations

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

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.target_edit = QLineEdit()
        self.meta = QLabel("")
        self.meta.setWordWrap(True)
        self.description = QTextEdit()
        form.addRow("Title", self.title_edit)
        form.addRow("Source branch", self.source_edit)
        form.addRow("Target branch", self.target_edit)
        form.addRow("Meta", self.meta)
        form.addRow("Description", self.description)
        layout.addLayout(form)

        layout.addWidget(QLabel("Notes (read-only)"))
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setFont(QFont("monospace"))
        layout.addWidget(self.notes, stretch=1)

        row = QHBoxLayout()
        self.btn_save = QPushButton("Save metadata")
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_save)
        self.btn_merge = QPushButton("Merge…")
        self.btn_merge.clicked.connect(self._merge)
        row.addWidget(self.btn_merge)
        self.btn_open = QPushButton(open_in_label(self._info))
        self.btn_open.clicked.connect(self._open_web)
        row.addWidget(self.btn_open)
        self.btn_notes = QPushButton("Reload notes")
        self.btn_notes.clicked.connect(self._load_notes)
        row.addWidget(self.btn_notes)
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
        self.btn_notes.setEnabled(bool(info.get("supports_mr_notes", True)))
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
        if not info.get("supports_mr_notes", True):
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
        self.meta.setText(
            f"State: {d.get('state') or '?'} · Author: {d.get('author') or '?'} · "
            f"Draft: {draft}"
        )
        self._load_notes()

    def _load_notes(self) -> None:
        try:
            import labdesk_core

            notes = list(
                labdesk_core.list_merge_request_notes(self.project_id, self.mr_iid, 1)
                or []
            )
        except Exception as exc:
            code, msg = format_error(exc)
            self.notes.setPlainText(f"[{code}] {msg}\n{exc}")
            return
        if not notes:
            self.notes.setPlainText("(no notes)")
            return
        lines: list[str] = []
        for n in notes:
            author = n.get("author") or "?"
            when = n.get("created_at") or ""
            body = (n.get("body") or "").strip()
            lines.append(f"— {author}  {when}")
            lines.append(body)
            lines.append("")
        self.notes.setPlainText("\n".join(lines))

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
            QMessageBox.information(self, "Saved", f"{self._kind} metadata updated.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _merge(self) -> None:
        reply = QMessageBox.question(
            self,
            f"Merge {self._kind.lower()}",
            f"Merge !{self.mr_iid} via the forge API?\n\n"
            "Uses the forge default merge style (squash available as optional).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import labdesk_core

            labdesk_core.merge_merge_request(self.project_id, self.mr_iid, None)
            self._load()
            QMessageBox.information(self, "Merged", f"!{self.mr_iid} merged.")
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.critical(self, f"Error {code}", f"[{code}] {msg}\n\n{exc}")

    def _open_web(self) -> None:
        if not self._web_url:
            QMessageBox.information(self, open_in_label(self._info), "No web URL.")
            return
        try:
            open_url(self._web_url)
        except Exception as exc:
            code, msg = format_error(exc)
            QMessageBox.warning(self, f"Error {code}", f"[{code}] {msg}")
