# ADR-002: Qt + Python/Rust Hybrid Stack

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-09-01 (Slice I: from-scratch in-app editor; QScintilla stays rejected)

## Context

The goal is to build a native Linux desktop application that is
performant, secure, and designed to outlast its original author. Pure
web-based approaches (Electron/Tauri) introduce significant bloat and
dependency churn. Pure C++ requires high maintenance overhead for UI
development.

Riverbank **QScintilla** was considered for the diff viewer and later
for a full in-app editor, but it is licensed **GPLv3 or commercial**
(not Apache 2.0 as earlier drafts stated) and targets PyQt. Including
it would push a combined LabDesk distribution toward GPLv3 and conflict
with the goal of staying as close to **GPLv2+** as practical (see
ADR-003).

V1 / early V2 need a **read-only** diff/file view and structured
conflict UI only. A full in-app editor is planned as **Slice I**; the
product decision is to **build it from scratch** on the existing Qt /
PySide6 stack rather than adopt QScintilla.

## Decision

We will use a hybrid architecture:

- **UI Layer:** Python with **PySide6** (Qt for Python). PySide6 is
  available under `LGPL-3.0 OR GPL-2.0 OR GPL-3.0`; LabDesk will use it
  under terms compatible with the project’s GPLv2+ license.
- **Core Logic Layer:** Rust (compiled via **Maturin**/PyO3). This
  handles Git operations (`libgit2`), network requests, data caching,
  and heavy computations.
- **Diff / file viewer (through Slice H):** Qt **`QTextEdit`**
  (read-only), with `QSyntaxHighlighter` / `QTextCharFormat` (or
  equivalent) for add/delete/context line styling and light syntax
  highlighting — no Riverbank QScintilla.
- **In-app code editor (Slice I):** Built **from scratch** on PySide6 /
  Qt primitives (e.g. `QPlainTextEdit` / `QTextEdit` + highlighters,
  line numbers, find/replace, and related chrome as needed). Do **not**
  add QScintilla or other GPLv3-only editor widgets. Share styling /
  highlighter patterns with the read-only diff viewer where practical.
- **Interoperability:** The Rust backend is exposed as a Python module,
  allowing the UI to call high-performance functions without GIL
  contention where possible.

### QTextEdit fitness (V1 / early V2)

`QTextEdit` can present unified diffs with colored lines, monospace
fonts, and optional language highlighting. It will not match a full
Scintilla feature set; that is acceptable for read-only viewing and as
the base for an incremental from-scratch editor.

## Consequences

- **Performance:** Critical operations (diffing, large repo scanning)
  run at native speeds in Rust; the UI remains a thin Qt shell.
- **Longevity:** Rust keeps core logic memory-safe; Python keeps UI
  iteration cheap. A first-party editor avoids upstream Scintilla /
  Riverbank churn and license traps.
- **Complexity:** Contributors need Python, Rust, and PyO3 familiarity;
  Slice I also means owning editor UX (undo, search, large-file
  policy) rather than inheriting Scintilla’s.
- **Licensing:** Avoids Riverbank QScintilla’s GPLv3-or-commercial
  terms. Diff and editor UI stay inside PySide6/Qt (ADR-003).
- **Trade-off:** Feature parity with Scintilla is gradual; prefer a
  solid subset over a dependency that forces a license upgrade.
