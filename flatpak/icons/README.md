# LabDesk icons

Canonical PNGs (window, tray, Flatpak start-menu) live in:

- `src/labdesk_ui/assets/com.bigrangatech.LabDesk-64x64.png`
- `src/labdesk_ui/assets/com.bigrangatech.LabDesk-128x128.png`
- `src/labdesk_ui/assets/com.bigrangatech.LabDesk-256x256.png`
- `src/labdesk_ui/assets/com.bigrangatech.LabDesk-512x512.png`

Optional scalable:

- `src/labdesk_ui/assets/com.bigrangatech.LabDesk.svg`

The Flatpak build installs these into
`/app/share/icons/hicolor/{size}/apps/com.bigrangatech.LabDesk.png`
so the `.desktop` `Icon=com.bigrangatech.LabDesk` key resolves.
