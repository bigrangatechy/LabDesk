# LabDesk Developer Guide

**Status:** Living  
**Audience:** Human and AI contributors maintaining LabDesk  
**Related:** `AGENTS.md`, `CONTRIBUTING.md`, `Docs/adr/`, Technical
Specification, `data-model.md`, `api-contract.md`,
`security-credentials.md`, `flatpak-manifest-spec.md`

This guide holds **build, layout, testing, Flatpak, and maintenance**
detail. End-user how-tos belong in `user-guide.md`.

Until sections are filled, treat undecided tooling pins as open — ask
before inventing them (`AGENTS.md`).

---

## 1. Repository layout

```text
Docs/           documentation (source of truth while docs-first)
src/
  labdesk_ui/   PySide6 UI
  labdesk_core/ Rust / PyO3 core
flatpak/        Flatpak manifest only (no build artifacts)
scripts/        helper scripts (e.g. run-labdesk.sh)
tests/          tests (placeholder)
```

### 1.1 Remotes and Flatpak hosting

| Repo | Role | Mirrored to GitHub? | Large binaries / LFS |
|------|------|---------------------|----------------------|
| **labdesk** (this repo) | App source + Flatpak *manifest* + CI that *builds* | Yes (read-only visibility mirror) | **No** — keep lean |
| **Ranga/flatpaks** (`http://git.bigrangatech.com/Ranga/flatpaks.git`) | Hosts Flatpak remote / ostree / published builds | **No** | **Yes** — LFS OK on the instance |
| GitHub `labdesk` mirror | Visibility only; updated *from* GitLab | n/a | Same tree as GitLab `labdesk` (no LFS objects) |

**Rules:**

- All development happens on **GitLab `labdesk`**. Do not push feature
  work to GitHub.
- Do **not** commit `.flatpak`, ostree repos, or `.flatpak-builder/` into
  `labdesk`. CI builds and **pushes** results into `Ranga/flatpaks`.
- You cannot use a different `.gitignore` for GitHub vs GitLab on the
  same commits; keeping binaries out of `labdesk` keeps the GitHub
  mirror clean.
- App id: `com.bigrangatech.LabDesk`. Details: `flatpak-manifest-spec.md`,
  ADR-004.

---

## 2. Architecture snapshot

- UI: Python + PySide6; read-only diffs via `QTextEdit` (ADR-002).
- Core: Rust via Maturin/PyO3 — git (libgit2), API client, cache, config.
- Auth: API PAT + `PRIVATE-TOKEN`; git HTTPS via credential helper
  (ADR-008).
- License: GPLv2+ (ADR-003).

Point to ADRs rather than restating them.

---

## 3. Documentation map

| Doc | Role |
|-----|------|
| `Technical-Specification.md` | Product/tech contract |
| `Architecture-Decision-Records.md` | ADR index |
| `adr/*` | Individual decisions |
| `data-model.md` | Config + SQLite + secrets layout |
| `api-contract.md` | GitLab REST usage |
| `security-credentials.md` | PAT / helper / TLS |
| `user-journey.md` | UX flows |
| `user-guide.md` | End-user help (install / update) |
| `flatpak-manifest-spec.md` | Manifest + CI publish into `flatpaks` |
| `testing-strategy.md` | May fold into this guide |
| `maintenance-guide.md` | May fold into this guide |
| `CHANGELOG.md` | Trace of changes |

---

## 4. Development environment

- **Python:** 3.10+ (developed against 3.14 with PyO3 0.25).
- **Rust:** stable (1.97+ tested).
- **Tooling:** [uv](https://github.com/astral-sh/uv) recommended for the
  venv; `maturin` builds `labdesk_core`.
- **UI:** PySide6.
- **System:** Linux; Secret Service / keyring for API PATs.

```bash
# from repo root (preferred)
./scripts/run-labdesk.sh
```

That script activates `.venv`, runs `maturin develop --uv`, then launches
the UI with the correct `PYTHONPATH`.

Manual equivalent:

```bash
# from repo root
source .venv/bin/activate
uv pip install maturin PySide6   # first time / when deps change
cd src/labdesk_core && maturin develop --uv && cd ../..
PYTHONPATH=src python -m labdesk_ui.main
```

Config (unpackaged): `~/.config/labdesk/config.toml`  
Known-good snapshot: `~/.config/labdesk/config.known-good.toml`

**Notes:**
- Prefer `./scripts/run-labdesk.sh` for day-to-day runs.
- Use `maturin develop --uv` when the venv was created with uv (no
  `pip` on PATH).
- Always launch from the **repo root** so `PYTHONPATH=src` finds
  `labdesk_ui` (the script does this for you).

---

## 5. Build & run

- **Preferred:** `./scripts/run-labdesk.sh` from the repo root.
- `maturin develop --uv` — editable install of `labdesk_core` into the
  active uv venv (plain `maturin develop` needs `pip`).
- Manual launch from **repo root**: `PYTHONPATH=src python -m labdesk_ui.main`
- Current slice: instance connect, projects, clone / add existing,
  repo Changes (stage/commit/diff) + History, push/pull, pluggable UI
  shells, Settings for confirmed prefs only.

---

## 6. Flatpak

- Manifest: `flatpak/com.bigrangatech.LabDesk.yml`.
- CI builds the Flatpak and **pushes** into
  `http://git.bigrangatech.com/Ranga/flatpaks.git` (see `.gitlab-ci.yml`).
- Users add that Flatpak remote and install/update
  `com.bigrangatech.LabDesk` (user-guide).
- Secrets portal / `org.freedesktop.secrets`; finish args in
  `flatpak-manifest-spec.md`.
- Preference `check_for_updates` means checking **this** Flatpak remote
  (data-model / ADR-004) — still config-only until the in-app check
  ships.

---

## 7. Data & API

- Implement against `data-model.md` and `api-contract.md`.
- Map failures to `error-codes.md` (`LD-…`) at the core → UI boundary.
- No plaintext PAT in config; no Bearer API auth in V1.
- **Config file first:** `config.toml` is authoritative and should
  expose as many options as practical. **Settings** UI only for
  confirmed-working / deliberately user-facing options. Config-only
  keys are valid for testing before UI exists. Persist changes from
  UI or file; Settings saves preserve unknown keys and only touch
  fields they own. Startup hang → revert last known good config,
  relaunch, show `LD-CFG-010` (data-model §3.0).

---

## 8. Testing

- TBD: unit (Rust), UI smoke, contract tests against a self-hosted
  fixture or recorded responses.
- Beta smoke checklist: `user-guide.md` (install + update).

---

## 9. Release & maintenance

- Versioning / changelog discipline (`HH:MM:SS  DD/MM/YYYY` stamps).
- Flatpak runtime upgrades: test before publishing to `Ranga/flatpaks`
  (ADR-004).
- May absorb `maintenance-guide.md`.

---

## 10. Working with agents

Follow `AGENTS.md`: docs-first, ask when undecided, update
`CHANGELOG.md`.

---

## Document history

Shell created during documentation-first phase. Remotes / Flatpak host
policy filled for beta packaging.
