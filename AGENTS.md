# AGENTS.md — Guidance for AI-assisted work on LabDesk

This file tells automated coding agents how to work in this repository
without fighting the project’s rules. Humans should read `CONTRIBUTING.md`
as well.

## Project in one paragraph

LabDesk is a **Linux-only**, **Flatpak-distributed** desktop client for
**self-hosted forges** (GitLab, Gitea, Forgejo, OneDev — not public SaaS).
Stack: **PySide6** UI + **Rust** core via **PyO3/Maturin**, local git via
**libgit2**, read-only diffs via **Qt `QTextEdit` / DiffView**, optional
from-scratch in-app editor (`QPlainTextEdit`), API tokens in the **system
keyring**, Git HTTPS via **credential helper**. License: **GPLv2+**.

## Current phase

**Living product + docs.** V1 vertical slice and V2 feature slices **A–N**
are in tree; **UI/UX polish** is in progress (`Docs/v2-roadmap.md`).
Update docs when behaviour changes. Prefer unpackaged
`./scripts/run-labdesk.sh` for day-to-day UI testing before Flatpak
rebuilds.

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
  `github.com` / `gitea.com` / `codeberg.org` / `code.onedev.io` at
  setup (ADR-001).
- **No Riverbank QScintilla** — diffs use `QTextEdit` / DiffView
  (ADR-002, ADR-003). In-app **editor** is from-scratch on Qt
  (`QPlainTextEdit`); external editor via portal / `xdg-open` remains.
- **API tokens in system keyring only** — never plaintext in
  `config.toml`. GitLab uses **`PRIVATE-TOKEN`**; Gitea/Forgejo use
  `Authorization: token …`; OneDev uses its access-token header
  (ADR-008 / forge modules).
- **Git HTTPS** via **credential helper** (username/password when
  enabled on the instance); **SSH** also supported.
- **Force push** only after explicit confirmation (not default).
- **Linux only** — no Windows/macOS targets.
- **Flatpak-first** distribution for releases (ADR-004).
- **One active account at a time** in the UI; schema and UI support
  **multiple hosts and accounts** (selectors + `active_*` ids).
- **Config file first:** `config.toml` is source of truth and should
  **expose as many options as practical** (including tester-only /
  not-yet-polished keys). The **Settings** UI is conservative: only
  controls for options that are **confirmed working** (or deliberately
  ready for end users). Persist changes; preserve unknown keys on
  save. Startup hang → last known good config + relaunch + error
  (data-model §3.0). Unexpected Python failures → **`LD-SYS-001`** +
  `data_dir/logs/last-crash.log`.
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
| Forge REST usage | `Docs/api-contract.md` (+ per-forge companions) |
| Config / SQLite / entities | `Docs/data-model.md` |
| Error codes (`LD-…`) | `Docs/error-codes.md` |
| End-user help | `Docs/user-guide.md` (single copy; Help + Flatpak share) |
| Contributor guide | `Docs/dev-guide.md` |
| UX flows | `Docs/user-journey.md` |
| Slice roadmap | `Docs/v2-roadmap.md` |
| Human contribution rules | `CONTRIBUTING.md` |
| What changed | `CHANGELOG.md` |

Empty or draft stubs mean **not decided yet** — ask before filling gaps
in code. Prefer living docs over inventing behaviour.

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
