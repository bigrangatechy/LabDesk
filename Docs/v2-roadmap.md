# LabDesk V2 Roadmap

**Status:** Living  
**Audience:** Contributors / agents  
**Related:** ADR-006, Technical Specification, user-guide, CHANGELOG

V2 deepens sync/merge (including structured in-app conflict resolution),
completes the MR/PR surface across forges, improves large-repo UX beyond
hard caps, and closes V1 completeness gaps. Delivery is **sliced** (A–H).

## Locked decisions

- Structured **conflict resolve UI** (ours / theirs / open external /
  mark resolved). Still **no** general in-app editor and **no** QScintilla.
- Full MR/PR surface: detail, edit metadata, merge via API, create from
  Compare, read-only notes (forge-aware labels).
- Sync banner / fetch-on-focus, stash, rebase, SSH host-switch, richer
  diffs, lightweight notifications, large-repo virtualization.

## Slices

| Slice | Theme | Status |
|-------|--------|--------|
| A | Sync awareness (fetch-on-focus, remote-changed banner) | Done |
| B | Large-repo UX (dirty-only Changes, virtualized browse, paged history) | Done |
| C | Stash + rebase + safer pull | Done |
| D | In-app conflict resolution | Next |
| E | MR detail / edit / create-from-Compare | — |
| F | MR merge via API + read-only notes | — |
| G | SSH host-switch + richer diffs | — |
| H | Notifications + V1 completeness pack | — |

## Out of V2

Full in-app editor, admin/runners, OAuth/SSO, Windows/macOS, localization,
MR reply posting, submodule/LFS management UIs.
