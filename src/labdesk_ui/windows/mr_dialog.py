"""Create merge / pull request dialog (forge-aware title)."""

from __future__ import annotations

from PySide6.QtWidgets import (
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
    ) -> None:
        super().__init__(parent)
        label = kind_label or pr_label(forge_info())
        self.setWindowTitle(f"Create {label.lower()}")
        self.resize(480, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        if project_label:
            form.addRow("Project", QLabel(project_label))

        self.source = QLineEdit(source_branch)
        self.target = QLineEdit(target_branch or "main")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Short title (required)")
        self.description = QTextEdit()
        self.description.setPlaceholderText("Optional description")

        form.addRow("Source branch", self.source)
        form.addRow("Target branch", self.target)
        form.addRow("Title", self.title)
        form.addRow("Description", self.description)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.title.setFocus()

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.source.text().strip(),
            self.target.text().strip(),
            self.title.text().strip(),
            self.description.toPlainText().strip(),
        )
