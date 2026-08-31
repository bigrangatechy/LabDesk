# LabDesk V2 Roadmap

**Status:** Living  
**Audience:** Contributors / agents  
**Related:** ADR-006, Technical Specification, user-guide, CHANGELOG

V2 deepens sync/merge (including structured in-app conflict resolution),
completes the MR/PR surface across forges, improves large-repo UX beyond
hard caps, closes V1 completeness gaps, then extends into editor/diff,
admin, localization, review, and git-extension surfaces. Delivery is
**sliced**; a dedicated **UI/UX pass** lands after the feature slices.

## Locked decisions (current)

- Structured **conflict resolve UI** (ours / theirs / open external /
  mark resolved) lands in Slice D — not a general IDE.
- Full MR/PR surface (Slices E–F): detail, edit metadata, merge via API,
  create from Compare, read-only notes (forge-aware labels).
- Sync banner / fetch-on-focus, stash, rebase, SSH host-switch, richer
  diffs, lightweight notifications, large-repo virtualization (A–C, G–H).
- Slices **I–N** promote work previously deferred; each may need ADR /
  tech-spec updates when implementation starts. **Slice I** editor
  stack is locked: from-scratch on PySide6/Qt (no QScintilla).

## Slices

| Slice | Theme | Status |
|-------|--------|--------|
| A | Sync awareness (fetch-on-focus, remote-changed banner) | Done |
| B | Large-repo UX (dirty-only Changes, virtualized browse, paged history) | Done |
| C | Stash + rebase + safer pull | Done |
| D | In-app conflict resolution | Done |
| E | MR detail / edit / create-from-Compare | Done |
| F | MR merge via API + read-only notes | Done |
| G | SSH host-switch + richer diffs | Done |
| H | Notifications + V1 completeness pack | Done |
| I | Full in-app code editor (from scratch on Qt; no QScintilla) | Done |
| J | Admin / runner management | Done |
| K | Side-by-side fancy diff editor | Next |
| L | Localization | — |
| M | MR comment replies / full review workflows | — |
| N | Submodule / LFS management UIs | — |
| UX | UI/UX polish pass (after I–N) | — |

### Slice notes (I–N + UX)

- **I — In-app editor:** Full in-app code editor built **from scratch**
  on PySide6/Qt (`QPlainTextEdit` / `QTextEdit` + highlighters and
  chrome). Riverbank **QScintilla remains rejected** (ADR-002, ADR-003).
  Shipped subset: open/save, undo/redo, find/replace, line numbers,
  basic language highlight, large/binary file policy; **Open external**
  remains available. Not Scintilla feature parity.
- **J — Admin/runners:** Instance **Admin** view (runners/agents + users)
  and repo **Runners** tab. Forge-aware: GitLab runners, Gitea/Forgejo
  Actions runners, OneDev agents (list + open; pause/delete via API on
  GitLab/Gitea/Forgejo). Capability-gated like play-job.
- **K — Fancy diff:** Side-by-side (and related) diff product beyond
  read-only unified `QTextEdit` views; may reuse highlighter /
  chrome patterns from Slice I; still no QScintilla.
- **L — Localization:** Non-English UI strings / packaging; English
  remains default until this slice.
- **M — Review workflows:** Post MR/PR comment replies and fuller review
  flows (beyond read-only notes in F).
- **N — Submodule/LFS:** Management UIs for submodules and Git LFS
  (status, sync, common operations — not a full LFS server).
- **UX — Polish pass:** After feature slices A–N, one pass for layout,
  density, keyboard/focus, empty states, and consistency — not new
  product features.

## Still deferred (not in slice list)

- **OAuth / SSO** browser login (API stays PAT / forge token headers)
- **Windows / macOS** targets (Linux-only / Flatpak-first)
