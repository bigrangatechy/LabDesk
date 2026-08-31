# Translation catalogs

JSON objects mapping English UI source strings to translations.

These files are the **source** for `scripts/build_translations.py`, which
generates Qt Linguist `.ts` / `.qm` under `labdesk_ui/i18n/qm/`.

Edit catalogs here; rebuild `.qm` with:

```bash
.venv/bin/python scripts/build_translations.py
```

Locales: `es`, `de`, `fr`, `pt_BR`.
