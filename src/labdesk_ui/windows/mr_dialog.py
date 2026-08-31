"""Create merge / pull request dialog (forge-aware title)."""

from __future__ import annotations

from labdesk_ui.i18n import tr

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from labdesk_ui.utils.forge_labels import forge_info, pr_label


class MRDialog(QDialog):
    def __init__(
        self,
        *,
        source_branch: str,
        target_branch: str,
        project_label: str = "",
        parent=None,
        kind_label: str | None = None,
        title_prefill: str = "",
        description_prefill: str = "",
    ) -> None:
        super().__init__(parent)
        label = kind_label or pr_label(forge_info())
        self.setWindowTitle(f"Create {label.lower()}")
        self.resize(480, 400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        if project_label:
            form.addRow(tr("Project"), QLabel(project_label))

        self.source = QLineEdit(source_branch)
        self.target = QLineEdit(target_branch or "main")
        self.title = QLineEdit(title_prefill)
        self.title.setPlaceholderText(tr("Short title (required)"))
        self.description = QTextEdit()
        self.description.setPlaceholderText(tr("Optional description"))
        if description_prefill:
            self.description.setPlainText(description_prefill)
        self.draft = QCheckBox(tr("Create as draft (where supported)"))

        form.addRow(tr("Source branch"), self.source)
        form.addRow(tr("Target branch"), self.target)
        form.addRow(tr("Title"), self.title)
        form.addRow(tr("Description"), self.description)
        form.addRow("", self.draft)
        layout.addLayout(form)

        # Hide draft when the active forge cannot create drafts.
        info = forge_info()
        self.draft.setVisible(bool(info.get("supports_draft_mr", True)))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.title.setFocus()

    def values(self) -> tuple[str, str, str, str, bool]:
        return (
            self.source.text().strip(),
            self.target.text().strip(),
            self.title.text().strip(),
            self.description.toPlainText().strip(),
            self.draft.isChecked(),
        )
