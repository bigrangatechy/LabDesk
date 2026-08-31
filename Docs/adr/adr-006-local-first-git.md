# ADR-006: Local-First Git Operations

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-31 (V2: structured in-app conflict resolve; sync/MR depth)

## Context

Self-hosted instances may experience downtime, network issues, or
maintenance windows. A desktop client should remain functional during
these periods for all local operations. V2 also needs graceful handling
when local and remote history diverge (including merge/rebase conflicts).

## Decision

All Git operations (status, staging, committing, branching, diffing,
merging, rebase, stash) will use `libgit2` locally. Forge APIs are only
contacted for forge-integrated features such as:

- Project listing and cloning metadata
- Merge / pull request create, update, merge, and notes
- Branch existence verification on remote
- Pipeline / CI status and play (where supported)

### Git transport

- **HTTPS:** authenticate via the **Git credential helper** (username /
  password when the instance allows it, or username + PAT as password).
  See ADR-008.
- **SSH:** existing SSH agent / keys. Host switch may retarget SSH
  remotes when the same project path exists on the newly active host.

### Force push

Force push is **in scope**. It must never be the silent default when a
normal push is rejected. The user must choose force push explicitly and
confirm a dialog that shows the branch name.

### Local merge, rebase, and conflicts (V2)

Clean local merges and rebases are in scope. On conflict, LabDesk
provides a **structured conflict-resolution UI** (list conflicted paths;
accept ours / theirs; open in external editor; mark resolved; continue
or abort). This is **not** a general in-app code editor and must not
introduce Riverbank QScintilla (ADR-002, ADR-003). Users may still
resolve entirely externally if they prefer.

### Pipeline status

Show latest pipeline / CI status for the **current branch** and allow
**Play** on manual jobs where the forge supports it. Not a full CI
browser.

## Consequences

- **Offline Capable:** Users can commit, branch, and diff without
  network access.
- **Performance:** Local operations stay local; large repos need
  virtualized lists and dirty-only defaults (V2 Slice B).
- **Sync Complexity:** Ahead/behind/diverged must be visible; fetch on
  focus is configurable.
- **Safety:** Force push and merge-via-API remain confirmation-gated.
- **Conflict UX:** Mid-merge/rebase state must always offer Continue or
  Abort so the repo is never abandoned without recovery.
