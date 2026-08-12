# ADR-006: Local-First Git Operations

**Status:** Accepted  
**Date:** 2026-07-01  
**Updated:** 2026-08-07 (credential helper; force push; pipeline deferral)

## Context

Self-hosted instances may experience downtime, network issues, or
maintenance windows. A desktop client should remain functional during
these periods for all local operations.

## Decision

All Git operations (status, staging, committing, branching, diffing,
merging) will use `libgit2` locally. The GitLab API is only contacted
for forge-integrated features such as:

- Initial project listing and cloning metadata
- Merge request creation
- Branch existence verification on remote
- (Post-V1 / nice-to-have) Pipeline status polling

### Git transport (V1)

- **HTTPS:** authenticate via the **Git credential helper** (username /
  password when the instance allows it, or username + PAT as password).
  See ADR-008.
- **SSH:** existing SSH agent / keys.

### Force push (V1)

Force push is **in scope**. It must never be the silent default when a
normal push is rejected. The user must choose force push explicitly and
confirm a dialog that shows the branch name.

### Local merge (V1)

Local merge without conflicts is in scope. There is **no** in-app
conflict-resolution UI; on conflict, detect and direct the user to
resolve externally.

### Pipeline status

**Post-V1:** show latest pipeline status for the **current branch** and
allow **Play** on manual jobs (API contract §6). Not a full CI browser.

## Consequences

- **Offline Capable:** Users can commit, branch, and diff without
  network access.
- **Performance:** Local operations are instant; no API round-trips
  for routine work.
- **Sync Complexity:** The app must handle divergence between local
  state and remote state gracefully (behind/ahead tracking, stale
  cache indicators).
- **Safety:** Force push is available but gated behind confirmation.
