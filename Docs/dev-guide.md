# LabDesk Developer Guide

**Status:** Shell (docs stage)  
**Audience:** Human and AI contributors maintaining LabDesk  
**Related:** `AGENTS.md`, `CONTRIBUTING.md`, `Docs/adr/`, Technical
Specification, `data-model.md`, `api-contract.md`,
`security-credentials.md`

This guide holds **build, layout, testing, Flatpak, and maintenance**
detail. End-user how-tos belong in `user-guide.md`.

Until sections are filled, treat undecided tooling pins as open — ask
before inventing them (`AGENTS.md`).

---

## 1. Repository layout

```text
Docs/           documentation (source of truth while docs-first)
src/
  labdesk_ui/   PySide6 UI (placeholder until docs for area are ready)
  labdesk_core/ Rust / PyO3 core (placeholder)
flatpak/        Flatpak manifest
tests/          tests (placeholder)
```

Expand with module responsibilities when implementation starts.

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
| `user-guide.md` | End-user help |
| `flatpak-manifest-spec.md` | Manifest details (stub) |
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
- First slice exposes: add instance (URL + PAT), `GET /user`, project
  list refresh into SQLite cache, clone into configured folder (HTTPS or
  SSH), status + project table in the main window, `LD-…` error codes.
- Still placeholder: push/pull UI, diffs, hang watchdog (known-good
  snapshot is written on successful connect; `revert_config_to_known_good`
  is available for recovery).

---

## 6. Flatpak

- Manifest location: `flatpak/`.
- Secrets portal / `org.freedesktop.secrets`.
- Finish args and filesystem portals.
- Full detail: `flatpak-manifest-spec.md` (to be filled).

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
- May absorb `testing-strategy.md`.

---

## 9. Release & maintenance

- Versioning / changelog discipline.
- Flatpak runtime upgrade path (ADR-004).
- May absorb `maintenance-guide.md`.

---

## 10. Working with agents

Follow `AGENTS.md`: docs-first, ask when undecided, update
`CHANGELOG.md`.

---

## Document history

Shell created during documentation-first phase. Body content TBD.
