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
tests/          pytest suite (see §8); `tests/python/`
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
  repo Changes (stage/commit/diff) + History + Branches, create MR,
  open in external editor, offline banner, 45s startup hang recovery,
  push/pull, pluggable UI shells, Settings for confirmed prefs only.

---

## 6. Flatpak

- Manifest: `flatpak/com.bigrangatech.LabDesk.yml`.
- CI builds the Flatpak and **pushes** into
  `http://git.bigrangatech.com/Ranga/flatpaks.git` (see `.gitlab-ci.yml`).
- **Docker runner requirements** for `flatpak_build_publish`:
  prefer `privileged = true`. CI uses `--disable-rofiles-fuse` so
  `/dev/fuse` is not required. openh264 `apply_extra` / bwrap
  warnings are often non-fatal. See `flatpak-manifest-spec.md` §5.
- End-user install/update wording lives only in `user-guide.md`
  (signed `.flatpakrepo`; updates via Discover / Software / Flatpak).
  Do not put CI, unsigned remotes, or unpackaged paths in the user
  guide — keep those here.
- Prefer GPG-signed remotes for publish
  (`FLATPAK_GPG_PRIVATE_KEY` in CI; `./scripts/flatpak-gpg-create.sh`).
- Secrets portal / `org.freedesktop.secrets`; finish args in
  `flatpak-manifest-spec.md`.
- Preference `check_for_updates` means checking **this** Flatpak remote
  (data-model / ADR-004). New builds appear for users only after CI on
  `labdesk` has published to `Ranga/flatpaks`.
- Runtime must stay self-contained: ship UI + `labdesk_core` (vendored
  libgit2/OpenSSL via crate features) inside the Flatpak — do not add
  features that require host system libraries at runtime.

---

## 7. Data & API

- Implement against `data-model.md` and `api-contract.md`.
- **Hosts** (`[[instances]]`) vs **accounts** (`[[accounts]]`); API and
  SQLite cache follow `active_account_id` (`account_id` columns).
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

Run from the repo root (offscreen Qt; no display needed):

```bash
./scripts/run-tests.sh
# or: ./scripts/run-tests.sh -v tests/python/test_async_jobs.py
```

Installs `requirements-dev.txt` (pytest) if missing, builds `labdesk_core`
when needed, then runs `tests/python/`.

**What is covered today**

| Area | File | Catches |
|------|------|---------|
| Async UI bridge | `test_async_jobs.py` | Worker-thread widget updates (Qt Gui SIGSEGV) |
| Repo reopen | `test_repo_windows.py` | “Internal C++ object already deleted” after close |
| Large-repo Changes tab | `test_big_repo_tracked_cap.py` | Tracked + changes list caps; core `limit` arity |
| Forge-aware UI labels | `test_forge_labels.py` | MR/PR / Open in … / host combo helpers |
| Host ↔ LAN remotes | `test_host_switch_remotes.py` | Host switch retarget feedback |
| Multi-forge connect | `test_multi_forge.py` | Forge picker + SaaS reject list |
| LAN / SaaS URLs | `test_config_urls.py` | HTTP allowlist + gitlab.com reject |
| Version / errors | `test_version_and_helpers.py` | `APP_VERSION`, `format_error` |
| Packaging | `test_packaging_sanity.py` | CI YAML / Flatpak manifest basics |
| Pipeline jobs UI | `test_pipeline_jobs.py` | Playable heuristics + sort / row format |
| In-app Help | `test_help_dialog.py` | Bundled `user-guide.md` path resolution |

Keep `src/labdesk_ui/docs/user-guide.md` in sync with `Docs/user-guide.md`
when editing the guide (Help dialog reads the packaged copy first).

CI job `python_pytest` runs the UI suite (no Rust toolchain in that
image). Full suite including `labdesk_core` URL tests: local
`./scripts/run-tests.sh`.

Rust: `cd src/labdesk_core && cargo test`.
Beta smoke checklist: `user-guide.md` (install + update).

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
