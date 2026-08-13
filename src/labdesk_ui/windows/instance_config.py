"""Connect dialog — new GitLab host or add account on an existing host."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class InstanceConfigDialog(QDialog):
    """Modes: new host (URL + TLS + account) or add account to existing host."""

    MODE_NEW_HOST = "new_host"
    MODE_ADD_ACCOUNT = "add_account"

    def __init__(self, parent=None, *, mode: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect self-hosted GitLab")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem("New host", self.MODE_NEW_HOST)
        self.mode.addItem("Add account to existing host", self.MODE_ADD_ACCOUNT)
        form.addRow("Mode", self.mode)

        self.host_pick = QComboBox()
        form.addRow("Host", self.host_pick)

        self.host_name = QLineEdit()
        self.host_name.setPlaceholderText("My GitLab")
        form.addRow("Host display name", self.host_name)

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

        self.account_name = QLineEdit()
        self.account_name.setPlaceholderText("Work / Personal / username")
        form.addRow("Account label", self.account_name)

        self.pat = QLineEdit()
        self.pat.setEchoMode(QLineEdit.EchoMode.Password)
        self.pat.setPlaceholderText("Personal access token")
        form.addRow("API PAT", self.pat)

        self.ssl_mode = QComboBox()
        self.ssl_mode.addItem("Strict (system trust)", "strict")
        self.ssl_mode.addItem("Allow self-signed", "allow_self_signed")
        self.ssl_mode.addItem("Imported CA", "imported_ca")
        form.addRow("TLS mode", self.ssl_mode)

        ca_row = QWidget()
        ca_layout = QHBoxLayout(ca_row)
        ca_layout.setContentsMargins(0, 0, 0, 0)
        self.ca_status = QLabel()
        self.ca_status.setWordWrap(True)
        self.ca_import = QPushButton("Import CA…")
        self.ca_import.setToolTip(
            "Copy a PEM/CRT into LabDesk’s trusted_certs/ folder "
            "(used for API and git HTTPS when TLS mode is Imported CA)."
        )
        self.ca_import.clicked.connect(self._on_import_ca)
        ca_layout.addWidget(self.ca_status, stretch=1)
        ca_layout.addWidget(self.ca_import)
        form.addRow("Trusted CAs", ca_row)
        self._ca_row = ca_row

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._instances: list[dict] = []
        self._load_instances()
        self.mode.currentIndexChanged.connect(self._sync_mode_ui)
        self.host_pick.currentIndexChanged.connect(self._on_host_picked)
        self.ssl_mode.currentIndexChanged.connect(self._sync_ca_ui)

        if mode == self.MODE_ADD_ACCOUNT:
            idx = self.mode.findData(self.MODE_ADD_ACCOUNT)
            if idx >= 0:
                self.mode.setCurrentIndex(idx)
        self._sync_mode_ui()

    def _load_instances(self) -> None:
        self.host_pick.clear()
        self._instances = []
        try:
            import labdesk_core

            self._instances = list(labdesk_core.list_instances() or [])
        except Exception:
            self._instances = []
        for inst in self._instances:
            label = f"{inst.get('name') or 'GitLab'} — {inst.get('base_url') or ''}"
            self.host_pick.addItem(label, inst.get("id"))
        if not self._instances:
            # Disable add-account mode when no hosts exist.
            add_idx = self.mode.findData(self.MODE_ADD_ACCOUNT)
            if add_idx >= 0:
                try:
                    self.mode.model().item(add_idx).setEnabled(False)
                except Exception:
                    pass

    def _current_mode(self) -> str:
        return str(self.mode.currentData() or self.MODE_NEW_HOST)

    def _sync_mode_ui(self) -> None:
        add = self._current_mode() == self.MODE_ADD_ACCOUNT and bool(self._instances)
        self.host_pick.setVisible(add)
        self.host_pick.setEnabled(add)
        # Form labels stay; hide URL/TLS/host name when adding to existing.
        self.host_name.setVisible(not add)
        self.host_name.setEnabled(not add)
        self.base_url.setVisible(not add)
        self.base_url.setEnabled(not add)
        self.ssl_mode.setVisible(not add)
        self.ssl_mode.setEnabled(not add)
        if add:
            self._on_host_picked()
        self._sync_ca_ui()

    def _sync_ca_ui(self) -> None:
        add = self._current_mode() == self.MODE_ADD_ACCOUNT and bool(self._instances)
        show = (not add) and str(self.ssl_mode.currentData()) == "imported_ca"
        self._ca_row.setVisible(show)
        if show:
            self._refresh_ca_status()

    def _list_certs(self) -> list[str]:
        try:
            import labdesk_core

            return list(labdesk_core.list_trusted_certs() or [])
        except Exception:
            return []

    def _refresh_ca_status(self) -> None:
        names = self._list_certs()
        if names:
            self.ca_status.setText(f"{len(names)} file(s): {', '.join(names)}")
        else:
            self.ca_status.setText("No CA files yet — import a PEM or CRT.")

    def _on_import_ca(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CA certificate",
            "",
            "Certificates (*.pem *.crt *.cer);;All files (*)",
        )
        if not path:
            return
        try:
            import labdesk_core

            result = labdesk_core.import_trusted_cert(path)
            name = (result or {}).get("name") or path
            QMessageBox.information(
                self,
                "CA imported",
                f"Imported {name}.\n"
                f"Stored under {(result or {}).get('trusted_certs_dir') or 'trusted_certs/'}.",
            )
            self._refresh_ca_status()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import failed",
                f"Could not import certificate.\n\n{exc}",
            )

    def _on_host_picked(self) -> None:
        iid = self.host_pick.currentData()
        inst = next((i for i in self._instances if i.get("id") == iid), None)
        if inst:
            self.base_url.setText(inst.get("base_url") or "")
            ssl = inst.get("ssl_mode") or "strict"
            idx = self.ssl_mode.findData(ssl)
            if idx >= 0:
                self.ssl_mode.setCurrentIndex(idx)

    def _on_accept(self) -> None:
        if (
            self._current_mode() == self.MODE_NEW_HOST
            and str(self.ssl_mode.currentData()) == "imported_ca"
            and not self._list_certs()
        ):
            QMessageBox.warning(
                self,
                "Import a CA first",
                "TLS mode is Imported CA, but no certificates are in "
                "trusted_certs/ yet.\n\nImport a PEM or CRT, then try again.",
            )
            return
        self.accept()

    def values(self) -> dict:
        """Return a dict describing the connect action."""
        mode = self._current_mode()
        if mode == self.MODE_ADD_ACCOUNT and self._instances:
            return {
                "mode": self.MODE_ADD_ACCOUNT,
                "instance_id": str(self.host_pick.currentData() or ""),
                "account_name": self.account_name.text().strip()
                or self.host_name.text().strip()
                or "Account",
                "pat": self.pat.text().strip(),
            }
        host = self.host_name.text().strip() or "GitLab"
        account = self.account_name.text().strip() or host
        return {
            "mode": self.MODE_NEW_HOST,
            "host_name": host,
            "account_name": account,
            "base_url": self.base_url.text().strip().rstrip("/"),
            "pat": self.pat.text().strip(),
            "ssl_mode": str(self.ssl_mode.currentData()),
        }
