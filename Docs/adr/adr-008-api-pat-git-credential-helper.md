# ADR-008: API PAT + Git Credential Helper

**Status:** Accepted  
**Date:** 2026-08-07

## Context

LabDesk must call the GitLab REST API and perform git clone/fetch/push
over HTTPS or SSH. Self-hosted instances often still allow **username
and password** for Git over HTTP(S), which matches how some operators
(including the project author) actually authenticate for git traffic.

The API, however, is expected to use a **Personal Access Token**. Mixing
these incorrectly causes confusing failures. Storing git passwords in an
ad-hoc LabDesk-only scheme duplicates what Git already solves with
**credential helpers** (commonly backed by the FreeDesktop Secret
Service on Linux).

## Decision

### API authentication

- **Required:** Personal Access Token (PAT).
- Send the PAT with the **`PRIVATE-TOKEN`** HTTP header on all GitLab
  API v4 requests.
- Store the PAT in the **OS keyring** (see `security-credentials.md`).
  Never write it into `config.toml`.

### Git HTTPS authentication

- Use the **Git credential helper** (via libgit2’s credential helper
  integration / equivalent) for HTTPS clone, fetch, pull, and push.
- Supported credential forms when the instance allows them:
  - **Username + password** (Git HTTP password auth enabled on the
    instance).
  - **Username + PAT as password** (common GitLab pattern), if the user
    prefers that over a separate account password.
- LabDesk must not invent a second plaintext store for git passwords.

### Git SSH authentication

- Use the user’s existing **SSH agent / keys**. No PAT required for
  transport; API PAT is still required for forge features.

### Two-factor authentication (2FA)

- If the instance has 2FA and rejects password git auth, show a clear
  message to use **SSH** or **HTTPS with a PAT** (via the credential
  helper), not an obscure auth failure.

### Out of scope (V1)

- OAuth / device flow / SSO browser login.
- Using username/password as a full replacement for the API PAT.
- Bearer-token API auth (`Authorization: Bearer …`) — V1 standardizes
  on `PRIVATE-TOKEN`.

## Consequences

- **Positive:** Matches common self-hosted workflows; reuses Git’s
  credential helper instead of parallel secret logic for git.
- **Positive:** API auth stays explicit and consistent (`PRIVATE-TOKEN`).
- **Negative:** Users need both a working credential helper setup for
  HTTPS git and a PAT for API features.
- **Flatpak:** Manifest must allow talking to the secrets service used
  by the credential helper / keyring.
- **Docs:** ADR-001 no longer means “PAT for everything”; it means
  self-hosted-only. This ADR owns auth mechanics.
