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

- TBD: Rust toolchain, Python version, Maturin, system libs (libgit2,
  Qt), keyring/Secret Service for local runs.
- TBD: how to run unpackaged vs Flatpak nightlies.

---

## 5. Build & run

- TBD: `maturin develop`, UI entrypoint, env vars.
- TBD: lint/format commands.

---

## 6. Flatpak

- Manifest location: `flatpak/`.
- Secrets portal / `org.freedesktop.secrets`.
- Finish args and filesystem portals.
- Full detail: `flatpak-manifest-spec.md` (to be filled).

---

## 7. Data & API

- Implement against `data-model.md` and `api-contract.md`.
- No plaintext PAT in config; no Bearer API auth in V1.

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
