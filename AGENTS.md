# AGENTS.md — Guidance for AI-assisted work on LabDesk

This file tells automated coding agents how to work in this repository
without fighting the project’s rules. Humans should read `CONTRIBUTING.md`
as well.

## Project in one paragraph

LabDesk is a **Linux-only**, **Flatpak-distributed** desktop client for
**self-hosted GitLab** (not `gitlab.com`). Stack: **PySide6** UI +
**Rust** core via **PyO3/Maturin**, local git via **libgit2**, diffs in
read-only **Qt `QTextEdit`**, API PATs in the **system keyring**, Git
HTTPS via **credential helper**. License: **GPLv2+**.

## Current phase

**Living docs + first implementation slice.** Architecture docs are in
place; `src/` is no longer empty scaffolding for config/auth/API user.
Update docs when behaviour changes. Empty stubs (Flatpak detail, full
guides, git UI) must not block continuing the vertical slice.

## Before you change anything

1. Read the relevant docs under `Docs/` and ADRs under `Docs/adr/`.
2. `Docs/Architecture-Decision-Records.md` is an **index only**; full
   text is in `Docs/adr/*.md`.
3. If requirements conflict or are missing, **ask the user** — do not
   invent product decisions.
4. Record user-visible or architectural changes in `CHANGELOG.md`
   under `[Unreleased]`.

## Hard constraints (do not “helpfully” violate)

- **Self-hosted only** — reject SaaS hosts such as `gitlab.com` /
  `github.com` at setup (ADR-001).
- **No Riverbank QScintilla** — use `QTextEdit` (+ highlighter) for
  read-only diffs (ADR-002, ADR-003).
- **No in-app editor in V1** — external editor via portal / `xdg-open`.
  A future editor would be built from scratch if ever added.
- **PAT in system keyring only** — never plaintext in `config.toml`.
- **Git HTTPS** via **credential helper** (username/password when
  enabled on the instance); **API** uses **`PRIVATE-TOKEN`** (ADR-008).
- **Force push** only after explicit confirmation (not default).
- **Linux only** — no Windows/macOS targets.
- **Flatpak-first** distribution for releases (ADR-004).
- **One instance in V1 UI**; keep storage schema multi-instance-ready.
- **Config file first:** `config.toml` is source of truth and should
  **expose as many options as practical** (including tester-only /
  not-yet-polished keys). The **Settings** UI is conservative: only
  controls for options that are **confirmed working** (or deliberately
  ready for end users). Persist changes; preserve unknown keys on
  save. Startup hang → last known good config + relaunch + error
  (data-model §3.0).
- **Remotes:** develop on GitLab `labdesk` only. GitHub is a read-only
  mirror. Flatpak **builds** go to `Ranga/flatpaks` via CI — never
  commit Flatpak artifacts into `labdesk` (keeps the GitHub mirror
  LFS-free). See `dev-guide.md` §1.1.
- Every user-visible failure should use a catalogued **`LD-…` error
  code** (`Docs/error-codes.md`); do not invent one-off codes in code
  without updating that doc and the changelog.
- **GPLv2+** — avoid dependencies that force GPLv3-only combined works
  when a GPLv2-friendly option exists (ADR-003).

## Where truth lives

| Topic | Doc |
|-------|-----|
| Stack, features, config, errors | `Docs/Technical-Specification.md` |
| Decisions | `Docs/adr/` (+ index) |
| Credentials / TLS / keyring / git helper | `Docs/security-credentials.md` |
| GitLab REST usage | `Docs/api-contract.md` |
| Config / SQLite / entities | `Docs/data-model.md` |
| Error codes (`LD-…`) | `Docs/error-codes.md` |
| End-user help | `Docs/user-guide.md` (single copy; Help + Flatpak share) |
| Contributor guide | `Docs/dev-guide.md` |
| UX flows | `Docs/user-journey.md` |
| Human contribution rules | `CONTRIBUTING.md` |
| What changed | `CHANGELOG.md` |

Empty or draft stubs (`data-model.md`, `api-contract.md`, guides, etc.)
mean **not decided yet** — ask before filling gaps in code.

## Preferred workflow for agents

1. Clarify undecided items with the user.
2. Update the appropriate doc / ADR / changelog.
3. Only then implement, when the user asks for implementation.
4. Keep diffs focused; do not drive-by rewrite unrelated files.
5. Do not commit or push unless the user explicitly asks.

## Changelog discipline

Any meaningful docs or code change should add a short bullet under
`CHANGELOG.md` → `[Unreleased]` (Added / Changed / Fixed /
Security as appropriate). Prefix each new bullet with local wall time
`HH:MM:SS  DD/MM/YYYY` then an em dash (see `CHANGELOG.md` header).
This is the project’s trace when something goes wrong later.
