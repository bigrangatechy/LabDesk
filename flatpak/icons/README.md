# LabDesk icons

Canonical assets live in `src/labdesk_ui/assets/`:

**Raster (hicolor sizes)**

- `com.bigrangatech.LabDesk-64x64.png`
- `com.bigrangatech.LabDesk-128x128.png`
- `com.bigrangatech.LabDesk-256x256.png`
- `com.bigrangatech.LabDesk-512x512.png`

**SVG**

- `LabDesk-logo.svg` — app icon (window / tray / start menu)
- `LabDesk-logo-with-text.svg` — wordmark for About and similar UI

The Flatpak build installs PNGs into
`/app/share/icons/hicolor/{size}/apps/com.bigrangatech.LabDesk.png`
and installs `LabDesk-logo.svg` as
`/app/share/icons/hicolor/scalable/apps/com.bigrangatech.LabDesk.svg`
so the `.desktop` `Icon=com.bigrangatech.LabDesk` key resolves.
