"""Instance setup dialog — URL + PAT."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)


class InstanceConfigDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect self-hosted GitLab")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit()
        self.name.setPlaceholderText("My GitLab")
        form.addRow("Display name", self.name)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText(
            "https://gitlab.example.com  or  http://192.168.x.x:port (LAN)"
        )
        self.base_url.setToolTip(
            "HTTPS required for public DNS names.\n"
            "http:// is allowed only for localhost / RFC1918 private IPs.\n"
            "On plain HTTP the API PAT is sent in cleartext — trusted LAN only."
        )
        form.addRow("Base URL", self.base_url)

        self.pat = QLineEdit()
        self.pat.setEchoMode(QLineEdit.EchoMode.Password)
        self.pat.setPlaceholderText("Personal access token")
        form.addRow("API PAT", self.pat)

        self.ssl_mode = QComboBox()
        self.ssl_mode.addItem("Strict (system trust)", "strict")
        self.ssl_mode.addItem("Allow self-signed", "allow_self_signed")
        self.ssl_mode.addItem("Imported CA (system trust for now)", "imported_ca")
        form.addRow("TLS mode", self.ssl_mode)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.name.text().strip() or "GitLab",
            self.base_url.text().strip().rstrip("/"),
            self.pat.text().strip(),
            str(self.ssl_mode.currentData()),
        )
