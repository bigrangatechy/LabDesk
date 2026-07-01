# Architecture Decision Records — LabDesk

## ADR-001: Self-Hosted GitLab Only Policy
**Status:** Accepted  
**Date:** 2026-07-01

### Context
Existing Git GUI clients with forge integration (e.g., GitHub Desktop) are
tightly coupled to specific SaaS providers (`github.com`, `gitlab.com`).
While generic Git clients exist, they lack the workflow automation
(MR creation, pipeline status, branch tracking) that makes the desktop
experience valuable. There is currently no open-source, native Linux GUI
client specifically designed for self-hosted GitLab instances that offers
this level of integration.

### Decision
The application will support **only user-configured self-hosted GitLab
instances**.

- No hardcoded support for `gitlab.com` or `github.com`.
- Authentication will rely exclusively on Personal Access Tokens (PAT).
- All API endpoints will be constructed dynamically based on the
  user-provided base URL.
- Instance type detection or automatic routing to public SaaS endpoints
  will not be implemented.

### Consequences
- **Positive:** Drastically reduced complexity (no OAuth flows, no
  multi-provider abstraction layers). Focus remains entirely on the
  self-hosted use case. Stability is anchored to the version the
  administrator controls, not a remote SaaS release cycle.
- **Negative:** Users of GitLab.com SaaS cannot use this tool; they
  must use existing alternatives. The total addressable market is
  smaller, but highly targeted.
- **Maintenance:** Easier to test and verify compatibility since the
  target environment is always a user-controlled instance.

---

## ADR-002: Qt + Python/Rust Hybrid Stack
**Status:** Accepted  
**Date:** 2026-07-01

### Context
The goal is to build a native Linux desktop application that is
performant, secure, and designed to outlast its original author. Pure
web-based approaches (Electron/Tauri) introduce significant bloat and
dependency churn. Pure C++ requires high maintenance overhead for UI
development.

### Decision
We will use a hybrid architecture:

- **UI Layer:** Python with **PySide6** (Qt for Python, LGPL licensed).
  This provides rapid development, accessibility tools, and a mature
  ecosystem.
- **Core Logic Layer:** Rust (compiled via **Maturin**/PyO3). This
  handles Git operations (`libgit2`), network requests, data caching,
  and heavy computations.
- **Diff/Code Viewer:** **QScintilla** (Apache 2.0 / GPL v3 dual
  licensed) for syntax-highlighted diffs and file content viewing.
- **Interoperability:** The Rust backend is exposed as a Python module,
  allowing the UI to call high-performance functions without GIL
  contention where possible.

### Consequences
- **Performance:** Critical operations (diffing, large repo scanning)
  run at native speeds.
- **Longevity:** Rust ensures memory safety and longevity of the core
  logic. Python allows for easier UI iteration.
- **Complexity:** Developers need familiarity with both languages and
  the PyO3 bridge, increasing the learning curve for new contributors.
- **Licensing:** PySide6 (LGPL) and QScintilla (Apache 2.0) are both
  compatible with the project's GPLv2+ license.

---

## ADR-003: GPLv2+ Licensing
**Status:** Accepted  
**Date:** 2026-07-01

### Context
The creator intends for this software to remain free and open source
indefinitely, ensuring it can be maintained by the community even if
the original author moves on. The project is designed with a "built to
outlast me" philosophy. Proprietary forks or closed-source derivatives
are contrary to this vision.

### Decision
The project will be licensed under the **GNU General Public License
version 2 or later (GPLv2+)**.

- All source code, documentation, and configuration templates will
  include the GPL header.
- The `COPYING` file will contain the full GPLv2 license text.
- Contributions from third parties are assumed to be licensed under
  these terms unless explicitly agreed otherwise in writing.
- A `CONTRIBUTING.md` will clarify that all submissions are accepted
  under GPLv2+.

### Consequences
- **Protection:** Any derivative work distributed must also be open
  source under compatible terms.
- **Compatibility:** Compatible with PySide6 (LGPL), Rust crates
  (MIT/Apache), QScintilla (Apache 2.0), and libgit2 (GPLv2 with
  linking exception).
- **Constraint:** Prevents commercial entities from incorporating
  the code into proprietary products without releasing their changes.
- **Flexibility:** The "+" allows future adoption of GPLv3 if patent
  protections or anti-DRM clauses become necessary.

---

## ADR-004: Flatpak-First Distribution Strategy
**Status:** Accepted  
**Date:** 2026-07-01

### Context
Linux distribution fragmentation creates significant challenges for
desktop applications: dependency hell, library mismatches, and update
delays across distros. The goal is a "build once, run anywhere"
experience that guarantees the app runs regardless of the host distro's
version. This aligns with the "outlast me" philosophy by ensuring the
binary remains functional even as host systems evolve.

### Decision
The application will be distributed **exclusively as a Flatpak**.

- The source repository will include a `flatpak-manifest.yml` for
  building.
- The app will bundle all necessary runtime dependencies (Qt libraries,
  libgit2, OpenSSL, etc.) within the Flatpak sandbox or pin them to a
  specific SDK runtime (KDE Platform).
- No DEB, RPM, or AppImage targets will be provided in V1.
- Runtime version will be pinned with documented upgrade path.

### Consequences
- **Stability:** The app runs in an isolated environment, immune to
  host system library updates breaking the app.
- **User Base:** Requires users to have Flatpak/Flathub enabled. This
  filters for users comfortable with modern Linux package management,
  which aligns with the self-hosted target audience.
- **Sandboxing:** Requires careful handling of filesystem permissions
  and portal usage for file dialogs.
- **Maintenance:** Runtime version upgrades must be tested before
  pushing; document the known-compatible range.

---

## ADR-005: Project Identity — LabDesk
**Status:** Accepted  
**Date:** 2026-07-01

### Context
The project needs a distinctive identity that communicates its purpose
(self-hosted GitLab desktop client) while avoiding trademark
infringement on "GitLab" as a registered trademark. The name should be
discoverable by users searching for a GitLab desktop client.

### Decision
- **Display Name:** LabDesk
- **Icon:** Anvil (symbolizing craftsmanship, self-reliance, and the
  forge/workshop metaphor for self-hosted infrastructure)
- **Domain:** `labdesk.bigrangatech.com`
- **Flatpak App ID:** `com.bigrangatech.LabDesk`
- **Executable:** `labdesk`
- **Repository Name:** `labdesk-client`

The combination gives us searchability (LabDesk clearly relates to
GitLab + desktop) while the Anvil icon provides a unique visual
identity separate from GitLab's own branding.

### Consequences
- **Discoverability:** "LabDesk" is immediately understood by the
  target audience.
- **Trademarks:** "Lab" references GitLab conceptually but does not
  use the full trademarked name. The Anvil icon has no resemblance
  to GitLab's fox logo.
- **Expansion:** If the project ever supports other self-hosted forges
  (Gitea, Forgejo), the name "LabDesk" may feel restrictive. This is
  acceptable for V1; a rename can happen if the scope expands.

---

## ADR-006: Local-First Git Operations
**Status:** Accepted  
**Date:** 2026-07-01

### Context
Self-hosted instances may experience downtime, network issues, or
maintenance windows. A desktop client should remain functional during
these periods for all local operations.

### Decision
All Git operations (status, staging, committing, branching, diffing,
merging) will use `libgit2` locally. The GitLab API is only contacted
for:

- Initial project listing and cloning
- Merge request creation
- Pipeline status polling
- Branch existence verification on remote

### Consequences
- **Offline Capable:** Users can commit, branch, and diff without
  network access.
- **Performance:** Local operations are instant; no API round-trips
  for routine work.
- **Sync Complexity:** The app must handle divergence between local
  state and remote state gracefully (behind/ahead tracking, stale
  cache indicators).

---

## ADR-007: Documentation-First Development
**Status:** Accepted  
**Date:** 2026-07-01

### Context
The project is designed to outlast its original author. Undocumented
decisions become unmaintainable technical debt. Writing documentation
before code ensures architectural flaws are caught when they're cheap
to fix — in a text file — rather than expensive — in a refactor.

### Decision
All architectural decisions, data models, API contracts, user journeys,
security policies, and build configurations will be documented **before**
implementation begins. An `AGENTS.md` file will guide AI-assisted
contributions.

### Consequences
- **Slower Start:** Initial velocity is lower due to documentation
  overhead.
- **Higher Quality:** Fewer mid-development architectural pivots.
- **Onboarding:** New contributors (human or AI) can understand the
  project without tribal knowledge.
- **Maintenance:** Every decision has a recorded rationale, preventing
  "why was it done this way?" archaeology.