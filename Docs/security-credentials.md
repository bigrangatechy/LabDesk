# Security & Credentials — LabDesk

**Status:** Draft (docs stage)  
**Related:** ADR-001, ADR-004, ADR-008, Technical Specification §4 / §6 / §7

## 1. Goals

- Never store secrets (API PATs or git passwords) in plaintext in
  LabDesk config files.
- **API PAT** → OS keyring.
- **Git HTTPS** credentials → **Git credential helper** (often the same
  Secret Service backend on Linux).
- Keep TLS behaviour explicit for self-hosted / LAN GitLab.
- Reject unsupported SaaS hosts at setup time.

## 2. What is stored where

| Data | Location | Notes |
|------|----------|--------|
| Instance URL, name, preferences | `config.toml` | No raw secrets |
| Keyring lookup id | `config.toml` → `keyring_account` | API PAT reference only |
| API PAT | **OS keyring** | Required for API (ADR-008) |
| Git HTTPS username/password | **Git credential helper** | When instance allows password git auth |
| Git HTTPS with PAT-as-password | **Git credential helper** | Optional alternative to account password |
| SSH keys | User agent / `~/.ssh` (outside LabDesk store) | Transport only |
| Trusted CA files | `trusted_certs/` under config dir | When `ssl_mode = "imported_ca"` |
| Project / MR / branch cache | SQLite `cache.db` | Not a secret store |
| Logs | `logs/` under data dir | Must not log secrets or auth headers |

If the keyring is unavailable, LabDesk **must not** fall back to
writing the API PAT into `config.toml`. Show an error and block saving
API credentials (Technical Specification §6).

## 3. API PAT handling

### 3.1 Lifecycle

1. User pastes PAT in Instance Config (password-style field; not echoed
   in full after save).
2. On successful validation (`GET /user` with **`PRIVATE-TOKEN`**),
   store the PAT in the keyring under `keyring_account`.
3. Config writes only non-secret fields + `keyring_account`.
4. On auth failure, clear the keyring entry for that account and prompt
   for a new PAT.
5. On instance remove, delete the matching keyring entry.

### 3.2 Keyring identity

V1 uses one active instance in the UI. Suggested account id:

```text
labdesk:<base_url>
```

Example: `labdesk:https://gitlab.bigrangatech.com`

Service/application name in the keyring should be `LabDesk` (or the
Flatpak app id `com.bigrangatech.LabDesk` where the portal requires it).

On Linux, LabDesk uses the **FreeDesktop Secret Service** backend (not
the kernel keyutils store) so the same path works unpackaged and under
Flatpak (`--talk-name=org.freedesktop.secrets`).

### 3.3 API header

All GitLab API v4 requests use:

```http
PRIVATE-TOKEN: <pat>
```

V1 does **not** use `Authorization: Bearer` (ADR-008).

### 3.4 PAT scopes (guidance)

Exact minimum scopes depend on GitLab version and whether git uses SSH
or HTTPS. Many operators enable broad scopes on personal instances to
avoid surprises.

**User-facing guidance:**

- For API features (projects, MRs): ensure the PAT can use the API
  (commonly the `api` scope).
- If unsure on a personal self-hosted instance, enabling the scopes you
  need for API + repository access (or a full-access PAT) is acceptable;
  LabDesk will not invent a fragile “minimum matrix” until tested
  against documented target versions.
- Prefer least privilege on shared / production instances.

## 4. Git HTTP(S) via credential helper

Per ADR-008:

- libgit2 (or the git ops layer) must use the **Git credential helper**
  for HTTP(S) clone / fetch / pull / push.
- Supported when the instance allows it: **username + password**
  (common on self-hosted GitLab, including older `http://` remotes on
  a LAN).
- Also supported: **username + PAT as password** (common GitLab HTTPS
  pattern).
- LabDesk must not write git passwords into `config.toml` or remote URLs
  on disk when the helper can supply them instead.
- **Existing clones** from the same instance keep their remotes as-is
  (e.g. `http://git.example/…` with helper-stored username/password).
  Adopting them does not rewrite the remote to HTTPS or inject the API
  PAT into the URL. Push/pull still asks the credential helper first;
  the API PAT is only a fallback when the helper has nothing.

### 4.1 2FA

If password git auth fails because of 2FA, show a clear message to use
**SSH** or **HTTPS with a PAT** through the credential helper.

### 4.2 SSH

SSH transport uses the user’s existing agent/keys. No LabDesk-managed
password store for SSH.

## 5. TLS / certificates

### 5.0 Base URL scheme

- **HTTPS** required for public hostnames.
- **`http://`** only for **loopback** and **RFC1918** private addresses
  (LAN GitLab). Flatpak already has `--share=network`.
- Over plain HTTP, the API **PAT is sent in cleartext** — warn the user;
  only use on trusted networks.

Per-instance `ssl_mode` (HTTPS):

| Mode | Behaviour |
|------|-----------|
| `strict` | System trust store only (default) |
| `allow_self_signed` | User explicitly opts in; warn in UI |
| `imported_ca` | Trust additional PEMs from `trusted_certs/` |

- Default for new instances: **`strict`**.
- `allow_self_signed` must be an explicit user action, not silent.

### 5.1 Imported CA (`ssl_mode = imported_ca`)

- Store user-selected PEMs as files under
  `{config_dir}/trusted_certs/` (extensions `.pem` / `.crt` / `.cer`).
- Connect dialog **Import CA…** copies into that folder; filenames are
  listed in the dialog.
- **API (reqwest):** each imported PEM is added as an extra root
  certificate (system roots remain).
- **Git HTTPS (libgit2):** LabDesk writes a concatenated bundle
  `trusted_certs/labdesk-ca-bundle.pem` and sets `GIT_SSL_CAINFO` for
  the duration of clone/fetch/push (serialized).
- Empty `trusted_certs/` with this mode → **`LD-NET-010`**.

## 6. SaaS rejection

At instance setup, reject known public SaaS hosts (at least
`gitlab.com` and `github.com`, including common `www.` variants).
Do not store URL or credentials for rejected hosts (ADR-001).

## 7. Logging & redaction

Never log:

- Raw PAT or password values
- `PRIVATE-TOKEN` header values
- Credential helper / keyring secret payloads

Prefer logging instance **name**, host (without credentials), HTTP
status codes, and redacted error bodies.

## 8. Flatpak considerations

- Request access to the secrets service (e.g. talk to
  `org.freedesktop.secrets`) for both LabDesk’s API PAT keyring use and
  typical credential-helper backends.
- Use portals for opening external editors / URLs where required.
- Filesystem access for clone directories is user-selected via portal /
  documented permissions — details in `flatpak-manifest-spec.md`.

## 9. Out of scope (V1)

- OAuth / device flow / SSO browser login
- Username/password as a full replacement for the **API** PAT
- Bearer token API auth
- Encrypting secrets inside `config.toml` as a keyring alternative
- Multi-account credentials per instance
- Windows / macOS credential stores (Linux only)
