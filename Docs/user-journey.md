# User Journeys — LabDesk

**Status:** Draft (docs stage)  
**Audience:** Product / UX reference; feeds the future **user guide**  
**Platform:** Linux only (Flatpak primary)

These journeys describe what a person does with LabDesk today. They are
not UI mock pixel specs.

---

## Journey A — First run: connect a self-hosted forge

**Goal:** Point LabDesk at a self-hosted GitLab, Gitea, Forgejo, or
OneDev host and prove the API token works.

1. Launch LabDesk (Flatpak or unpackaged dev build).
2. Open **Add / connect** (first-run empty state prompts this).
3. Choose **Forge**, display name, base URL, and **API PAT** (or
   OneDev access token).
4. Choose TLS mode if needed (`strict` default; self-signed / imported
   CA only when the user opts in — see security-credentials).
5. Save → LabDesk validates with the forge’s current-user endpoint
   (GitLab: `GET /user` + **`PRIVATE-TOKEN`**).
6. On success: token stored in **system keyring**; non-secret settings
   in `config.toml` (including `[[instances]].forge`).
7. On failure: clear message (bad token, unreachable host, bad cert);
   no silent plaintext fallback.

**Reject path:** If the URL is a known public SaaS host (`gitlab.com`,
`github.com`, `gitea.com`, `codeberg.org`, `code.onedev.io`, …), show
that LabDesk is self-hosted only and **do not** save (`LD-CFG-004`).

**Git HTTPS later:** username/password (or PAT-as-password) is supplied
through the **Git credential helper** when cloning/pushing over HTTPS
(ADR-008) — not as a substitute for the API PAT.

**V1 note:** UI is built around **one** instance. Storage may still use
an `[[instances]]` array for a later multi-instance UI.

---

## Journey B — Find a project and clone it

**Goal:** Get a local working copy.

1. With a valid instance, open the project list.
2. LabDesk loads **owned**, **membership**, and **group** projects
   (cached after first fetch; show staleness if offline).
3. User picks a project and clone destination (default clone dir from
   preferences).
4. Clone via libgit2 (**HTTPS via credential helper**, or **SSH**).
   Progress shows as a translucent fill on the project’s table row or
   card (colour configurable in Settings).
5. Open the repo in the main RepoView (**Changes** / **History**;
   Branches later). History lists local commits (newest first) with
   patch vs parent.

**Existing clones:** If the project is already checked out under the
default clone folder (`{clone_dir}/{path_with_namespace}`), **Open
local** / Clone will adopt it. Otherwise use **Add existing…** or
**File → Open repository…** to point at any git working tree. Clones
authenticated earlier with **username/password** (credential helper)
on the same self-hosted server are first-class — LabDesk keeps the
remote URL and uses the helper for git; the instance **PAT** is only
for the API (project list, MRs, etc.).

If HTTPS git auth fails (including 2FA blocking passwords), show guidance
to fix credential-helper credentials, use a PAT-as-password, or switch
to SSH.

---

## Journey C — Daily local work (offline-friendly)

**Goal:** See changes, commit, without needing the forge up.

1. Open an already cloned repo (**Open local**, **Add existing…**, or
   **File → Open repository…**).
2. **Changes:** view status; **stage / unstage**; read-only **diff** in
   `QTextEdit`.
3. To edit files: open with an **external** editor (`xdg-open` /
   portal). No in-app editor in V1.
4. Enter commit message → **commit** locally (libgit2; uses git
   `user.name` / `user.email`).
5. Create / switch branches locally (**Branches** tab).
6. Optional: local **merge** when clean. On conflict, LabDesk opens the
   **conflict resolve** panel (ours / theirs / open external / mark
   resolved; continue or abort). You may still resolve entirely outside
   LabDesk.

Network is not required for this journey. Use **Open in editor** to
edit a selected file outside LabDesk.

---

## Journey D — Push, force push, and open a merge / pull request

**Goal:** Publish a branch and create an MR/PR on the self-hosted forge.

1. From RepoView, **Push** (SSH agent/keys, or HTTPS via credential
   helper).
2. If push is rejected (e.g. non-fast-forward), offer **pull** /
   guidance. **Force push is not the default** recovery path.
3. **Force push** (V1): available as an explicit action; show a
   confirmation dialog that includes the **branch name** before
   proceeding.
4. **Create merge / pull request:** fill title, description,
   source/target branch → forge create API (GitLab uses
   **`PRIVATE-TOKEN`**; other forges use their token header). Dialog
   and button labels follow the active forge.
5. On success, offer **Open in …** (forge name) in the browser.

Requires network. If offline, disable push / force push / create
actions with a clear reason.

---

## Journey E — Working while the instance is down

**Goal:** Keep coding when the forge is unreachable.

1. LabDesk detects unreachable API / git remote.
2. Banner or status: working offline; cached project list may be shown
   with a staleness hint.
3. Local git workflows (Journey C) remain available.
4. Push, project refresh, and MR/PR creation stay disabled until
   connectivity returns.

---

## Journey F — Update LabDesk

**Goal:** Get a newer Flatpak build from the self-hosted remote.

1. Preference `check_for_updates` means checking the **LabDesk Flatpak
   remote** backed by `Ranga/flatpaks` (ADR-004) — not a custom
   sideloaded updater and not “any Flathub package”.
2. Until the in-app check is UI-wired, use
   `flatpak update com.bigrangatech.LabDesk` (see `user-guide.md` §2).
3. New versions appear only after **labdesk CI** has pushed a build into
   `http://git.bigrangatech.com/Ranga/flatpaks.git`.
4. After update, relaunch and confirm connect / projects / repo still
   work (beta smoke checklist in the user guide).

---

## Journey G — Pipeline status (post-V1)

Show latest pipeline status for the current branch and play manual jobs
(see `api-contract.md` §6). Offline: disable play/refresh; header may
still show last-known status when available.

---

## Journey summary (V1)

| Journey | Network | V1 |
|---------|---------|----|
| A Connect instance | Yes | Required |
| B Clone project | Yes | Required |
| C Local commit / branch / diff | No | Required |
| D Push / force push + create MR | Yes | Required |
| E Offline local work | No | Required |
| F Flatpak updates | Yes | Required (mechanism) |
| G Pipelines | Yes | Post-V1 |
