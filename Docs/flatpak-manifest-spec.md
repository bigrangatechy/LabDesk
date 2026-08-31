# Flatpak Manifest Spec — LabDesk

**Status:** Living (beta)  
**App id:** `com.bigrangatech.LabDesk`  
**Related:** ADR-004, `dev-guide.md` §1.1 / §6, `user-guide.md` §2

## 1. Goals

- Ship LabDesk as a Flatpak from the self-hosted remote backed by
  [`Ranga/flatpaks`](http://git.bigrangatech.com/Ranga/flatpaks.git).
- Keep **build artifacts out of the `labdesk` git tree** (CI publishes
  into `flatpaks`).
- Document finish args so keyring, network, and clone directories work
  under the sandbox.

## 2. Files in `labdesk`

| Path | Role |
|------|------|
| `flatpak/com.bigrangatech.LabDesk.yml` | Manifest |
| `flatpak/com.bigrangatech.LabDesk.desktop` | Start-menu / launcher entry |
| `flatpak/com.bigrangatech.LabDesk.metainfo.xml` | AppStream metadata |
| `flatpak/icons/` | Notes for icon layout; PNGs + `LabDesk-logo*.svg` in `src/labdesk_ui/assets/` |
| `.gitlab-ci.yml` | Build + push job into `Ranga/flatpaks` |

**Never commit:** `.flatpak-builder/`, `repo/`, `*.flatpak`, ostree
checkouts (see root `.gitignore`).

## 3. Runtime

- Prefer **Freedesktop** or **KDE** Platform/Sdk with Qt 6 suitable for
  PySide6 (pin exact runtime versions in the manifest; bump only after
  testing).
- Bundle / build: Rust `labdesk_core` (maturin/cargo), Python UI, PySide6,
  libgit2 (via crates or system in module). Beta builds use
  `build-args: [--share=network]` so crates.io/PyPI work; vendor
  crates for stricter/offline Flathub-style builds later.

## 4. Finish args (required for V1 behaviour)

| Finish arg / permission | Why |
|-------------------------|-----|
| `--share=network` | GitLab API + git HTTPS/SSH **and LAN** (no extra finish-arg for private IPs) |
| `--socket=wayland` / `--socket=fallback-x11` | UI |
| `--device=dri` | Qt rendering |
| `--socket=session-bus` | D-Bus for Secret Service / tray |
| `--talk-name=org.freedesktop.secrets` | API PAT keyring (Secret Service) |
| `--filesystem=xdg-documents` (and/or home) | Default clone dirs under Documents |
| `--filesystem=xdg-download:ro` | Optional |
| `--talk-name=org.freedesktop.Flatpak` | In-app update checks via `flatpak-spawn --host` |
| `--talk-name=org.kde.StatusNotifierWatcher` | System tray icon |
| `--socket=ssh-auth` | SSH remotes via ssh-agent (libgit2) |
| Bundled `git` + `git-lfs` modules | Slice N LFS status/pull inside the sandbox |

Exact YAML lives in `flatpak/com.bigrangatech.LabDesk.yml` and may grow;
keep this table in sync when permissions change.

### Runtime modules (beyond PySide6 / labdesk_core)

| Module | Why |
|--------|-----|
| `git` 2.49 | Host for `git lfs …` (ordinary git I/O still uses libgit2) |
| `git-lfs` 3.8 | LFS status / pull on the **Git** tab |
| Qt Linguist `.qm` | Rebuilt during packaging when `pyside6-lrelease` is available |

### Build-date version

CI sets `LABDESK_VERSION=$(date -u +%Y.%m.%d)`, writes
`labdesk_ui/_build_version.py`, sed-injects that value into the
manifest `build-options.env` (this image’s `flatpak-builder` has no
`--env` CLI flag), and adds an AppStream `<release version="…">` in
metainfo. Unpackaged dev builds fall back to `dev`.

## 5. CI publish path

1. Job on `labdesk` adds Flathub (user install), installs
   `org.freedesktop.Platform//24.08`, `Sdk//24.08`, and
   `Sdk.Extension.rust-stable//24.08`, then runs `flatpak-builder`
   (`--user --install-deps-from=flathub`).
2. Job authenticates to GitLab (CI job token / deploy token / deploy key
   with **write** to `Ranga/flatpaks` only).
3. Job **pushes** the Flatpak repository / ostree commit / `.flatpak`
   bundle into `Ranga/flatpaks` (LFS allowed there).
4. Users’ Flatpak remote points at the published remote from that repo
   (see `user-guide.md`). Updating `flatpaks` is what makes
   `flatpak update` / `check_for_updates` see new versions.

The Docker runner for `flatpak_build_publish` **must** allow bubblewrap
user namespaces. Without that, module builds fail with
`bwrap: No permissions to creating new namespace`.

Under `[runners.docker]` for the Labdesk runner:

```toml
privileged = true
security_opt = ["seccomp:unconfined", "apparmor:unconfined"]
# optional; CI also uses --disable-rofiles-fuse
# devices = ["/dev/fuse"]
```

On **Ubuntu 24.04+ / 26.04** hosts, AppArmor often blocks nested userns
even in privileged containers. Persistently enable:

```bash
# temporary
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
# permanent
echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee \
  /etc/sysctl.d/99-labdesk-userns.conf
sudo sysctl --system
sudo systemctl restart gitlab-runner
```

openh264 `apply_extra` / bwrap warnings during `flatpak install` are
often non-fatal; the hard failure is when **module build** hits bwrap.

CI uses **`flatpak-builder --disable-rofiles-fuse`** so `/dev/fuse` is
not required.

CI variables (set in GitLab `labdesk` project settings, not in git):

| Variable | Purpose |
|----------|---------|
| `FLATPAKS_REPO_URL` | Git remote for publish. Prefer **HTTPS** on the public hostname. For CI behind Cloudflare Tunnel / 100 MB limits, use the **direct LAN** origin (e.g. `http://192.168.0.214:8929/Ranga/flatpaks.git`) so the ostree push bypasses Cloudflare. |
| `FLATPAKS_DEPLOY_TOKEN` | Project/group access token on **`flatpaks`** with `write_repository` (password). Username defaults to `oauth2`. |
| `FLATPAKS_DEPLOY_USER` | Optional. Set if using a **deploy token** (its username) instead of `oauth2`. |
| `FLATPAK_GPG_PRIVATE_KEY` | **Recommended.** Signing secret for the ostree repo. For **Masked** GitLab variables use **single-line base64** of the armored secret (`*.gpg.b64` from `./scripts/flatpak-gpg-create.sh`) — Masked values cannot contain whitespace/newlines. Or Type **File** with the armored key and leave Masked off. Never commit. |
| `FLATPAK_GPG_KEY_ID` | Optional fingerprint; CI auto-detects after import. |

Token CI variable flags: **Masked**; uncheck **Protected** unless the job only runs on protected branches/tags.

**GPG:** Without `FLATPAK_GPG_PRIVATE_KEY`, CI still publishes an unsigned
`labdesk/repo`. Flatpak **system** installs will then fail with
`Can't pull from untrusted non-gpg verified remote` — use
`--user --no-gpg-verify` only as a temporary workaround
(`user-guide.md` §2.1). With the key set, CI also publishes
`labdesk/labdesk.flatpakrepo` and `labdesk/bigrangatech-flatpak.gpg`.

**HTTP 413 on publish:** the ostree tree (especially with PySide6) often
exceeds upload limits on the path to GitLab. Common causes, in order:

1. **Cloudflare proxy / Tunnel** — Free/Pro allow only ~**100 MB**
   request bodies; Tunnel hostnames must stay **orange (proxied)**
   (grey-cloud breaks them). For CI, bypass Cloudflare:
   - Runner `clone_url = "http://192.168.0.214:8929"` (LAN GitLab)
   - CI variable `FLATPAKS_REPO_URL=http://192.168.0.214:8929/Ranga/flatpaks.git`
   - Keep public `git.bigrangatech.com` on the tunnel for humans
2. **GitLab Omnibus nginx** — raise body size if pushing to the
   public URL without Cloudflare:

```ruby
# /etc/gitlab/gitlab.rb (Omnibus)
nginx['client_max_body_size'] = '0'   # unlimited
```

```bash
sudo gitlab-ctl reconfigure
```

3. **Any other reverse proxy** in front of GitLab — raise its
   `client_max_body_size` (or equivalent) too.
4. **GitLab Admin → Settings → General → Account and limit** —
   raise Maximum push size (and attachment size if needed).

Do **not** store ostree objects in Git LFS while serving the Flatpak
remote via `/-/raw/…` — clients would get LFS pointer files, not
content. LFS remains fine for unrelated large binaries in `flatpaks`
if they are not part of the HTTP Flatpak remote path.

## 6. Local build (optional)

```bash
# from labdesk repo root — outputs stay untracked
flatpak remote-add --if-not-exists --user flathub \
  https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --user \
  org.freedesktop.Platform//24.08 \
  org.freedesktop.Sdk//24.08 \
  org.freedesktop.Sdk.Extension.rust-stable//24.08
flatpak-builder --user --force-clean --install-deps-from=flathub \
  --repo=repo flatpak-build \
  flatpak/com.bigrangatech.LabDesk.yml
# do not git-add repo/ or flatpak-build/
```

Publishing to users still goes through CI → `Ranga/flatpaks`.

## Document history

Filled for beta packaging (self-hosted `flatpaks` host, no artifacts in
source).
