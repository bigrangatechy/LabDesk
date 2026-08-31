#!/usr/bin/env python3
"""Build Qt Linguist .ts / .qm files from JSON catalogs.

Usage (from repo root):
  .venv/bin/python scripts/build_translations.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.sax.saxutils as sax
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "src" / "labdesk_ui" / "i18n"
QM_DIR = I18N / "qm"
EN_LIST = I18N / "_extracted_en.json"
CATALOG_DIR = I18N / "catalogs"


def _ts_escape(s: str) -> str:
    return sax.escape(s)


def write_ts(locale: str, catalog: dict[str, str], sources: list[str]) -> Path:
    QM_DIR.mkdir(parents=True, exist_ok=True)
    path = QM_DIR / f"labdesk_{locale}.ts"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE TS>",
        f'<TS version="2.1" language="{locale}">',
        "<context>",
        "    <name>labdesk</name>",
    ]
    for src in sources:
        tr = catalog.get(src, "")
        lines.append("    <message>")
        lines.append(f"        <source>{_ts_escape(src)}</source>")
        if tr:
            lines.append(f"        <translation>{_ts_escape(tr)}</translation>")
        else:
            lines.append('        <translation type="unfinished"></translation>')
        lines.append("    </message>")
    lines.append("</context>")
    lines.append("</TS>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    sources = json.loads(EN_LIST.read_text(encoding="utf-8"))
    lrelease = ROOT / ".venv" / "bin" / "pyside6-lrelease"
    if not lrelease.is_file():
        lrelease = Path("pyside6-lrelease")

    for cat_path in sorted(CATALOG_DIR.glob("*.json")):
        locale = cat_path.stem
        catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        ts = write_ts(locale, catalog, sources)
        qm = QM_DIR / f"labdesk_{locale}.qm"
        cmd = [str(lrelease), str(ts), "-qm", str(qm)]
        print(" ".join(cmd))
        subprocess.check_call(cmd)
        print(f"Wrote {qm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
