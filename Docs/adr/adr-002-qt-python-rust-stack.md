# ADR-002: Qt + Python/Rust Hybrid Stack

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (diff viewer: QTextEdit; drop Riverbank QScintilla)

## Context

The goal is to build a native Linux desktop application that is
performant, secure, and designed to outlast its original author. Pure
web-based approaches (Electron/Tauri) introduce significant bloat and
dependency churn. Pure C++ requires high maintenance overhead for UI
development.

Riverbank **QScintilla** was considered for the diff viewer, but it is
licensed **GPLv3 or commercial** (not Apache 2.0 as earlier drafts
stated) and targets PyQt. Including it would push a combined LabDesk
distribution toward GPLv3 and conflict with the goal of staying as close
to **GPLv2+** as practical (see ADR-003).

V1 needs a **read-only** diff/file view only. There is no in-app code
editor; any future editor would be built from scratch (see Technical
Specification constraints).

## Decision

We will use a hybrid architecture:

- **UI Layer:** Python with **PySide6** (Qt for Python). PySide6 is
  available under `LGPL-3.0 OR GPL-2.0 OR GPL-3.0`; LabDesk will use it
  under terms compatible with the project’s GPLv2+ license.
- **Core Logic Layer:** Rust (compiled via **Maturin**/PyO3). This
  handles Git operations (`libgit2`), network requests, data caching,
  and heavy computations.
- **Diff / file viewer:** Qt **`QTextEdit`** (read-only), with
  `QSyntaxHighlighter` / `QTextCharFormat` (or equivalent) for
  add/delete/context line styling and light syntax highlighting.
  Sufficient for V1 read-only diffs without an extra copyleft dependency.
- **Interoperability:** The Rust backend is exposed as a Python module,
  allowing the UI to call high-performance functions without GIL
  contention where possible.

### QTextEdit fitness (V1)

`QTextEdit` can present unified diffs with colored lines, monospace
fonts, and optional language highlighting. It will not match a full
Scintilla feature set; that is acceptable because V1 viewing is
read-only and editing is external.

## Consequences

- **Performance:** Critical operations (diffing, large repo scanning)
  run at native speeds in Rust; the UI remains a thin Qt shell.
- **Longevity:** Rust keeps core logic memory-safe; Python keeps UI
  iteration cheap.
- **Complexity:** Contributors need Python, Rust, and PyO3 familiarity.
- **Licensing:** Avoids Riverbank QScintilla’s GPLv3-or-commercial
  terms. Diff UI stays inside PySide6/Qt.
- **Trade-off:** Richer editor widgets are deferred; a from-scratch
  in-app editor remains a possible later project, not a V1 dependency.
