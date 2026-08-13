//! Config TOML load/save with unknown-key preservation (`toml_edit`).

use std::fs;
use std::path::Path;

use toml_edit::{DocumentMut, Item, Table, Value};
use uuid::Uuid;

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::paths::AppPaths;

const SAAS_HOSTS: &[&str] = &[
    "gitlab.com",
    "www.gitlab.com",
    "github.com",
    "www.github.com",
];

#[derive(Debug, Clone)]
pub struct GeneralConfig {
    pub theme: String,
    pub default_clone_dir: String,
    pub check_for_updates: bool,
    pub active_instance_id: Option<String>,
    pub active_account_id: Option<String>,
    /// Registered UI view id (e.g. `projects`, `settings`).
    pub active_ui_view: String,
    /// Main window shell: `classic` (top nav) or `sidebar`.
    pub ui_shell: String,
}

/// GitLab host (machine).
#[derive(Debug, Clone)]
pub struct InstanceConfig {
    pub id: String,
    pub name: String,
    pub base_url: String,
    pub api_version: String,
    pub ssl_mode: String,
    pub created_at: String,
}

/// GitLab account (user/PAT) on a host.
#[derive(Debug, Clone)]
pub struct AccountConfig {
    pub id: String,
    pub instance_id: String,
    pub name: String,
    pub username: Option<String>,
    pub api_auth: String,
    pub keyring_account: String,
    pub git_https_auth: String,
    pub created_at: String,
    pub last_connected: Option<String>,
    pub gitlab_version: Option<String>,
    pub gitlab_revision: Option<String>,
}

#[derive(Debug)]
pub struct AppConfig {
    pub general: GeneralConfig,
    pub instances: Vec<InstanceConfig>,
    pub accounts: Vec<AccountConfig>,
    /// Full document so unknown top-level / `[general]` keys survive round-trips.
    pub document: DocumentMut,
}

impl Default for GeneralConfig {
    fn default() -> Self {
        Self {
            theme: "system".into(),
            default_clone_dir: "~/Projects".into(),
            check_for_updates: true,
            active_instance_id: None,
            active_account_id: None,
            active_ui_view: "projects".into(),
            ui_shell: "classic".into(),
        }
    }
}

impl AppConfig {
    #[allow(dead_code)]
    pub fn active_instance(&self) -> Option<&InstanceConfig> {
        let id = self.general.active_instance_id.as_deref()?;
        self.instances.iter().find(|i| i.id == id)
    }

    pub fn active_account(&self) -> Option<&AccountConfig> {
        let id = self.general.active_account_id.as_deref()?;
        self.accounts.iter().find(|a| a.id == id)
    }

    pub fn active_account_mut(&mut self) -> Option<&mut AccountConfig> {
        let id = self.general.active_account_id.clone()?;
        self.accounts.iter_mut().find(|a| a.id == id)
    }

    /// Active account plus its host (API auth follows the account).
    pub fn active_connection(&self) -> Option<(&AccountConfig, &InstanceConfig)> {
        let acc = self.active_account()?;
        let inst = self.instances.iter().find(|i| i.id == acc.instance_id)?;
        Some((acc, inst))
    }

    #[allow(dead_code)]
    pub fn accounts_for_instance(&self, instance_id: &str) -> Vec<&AccountConfig> {
        self.accounts
            .iter()
            .filter(|a| a.instance_id == instance_id)
            .collect()
    }
}

pub fn validate_base_url(base_url: &str) -> Result<()> {
    let parsed = url::Url::parse(base_url).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CFG-003", "Config value invalid: base_url").with_detail(e.to_string()),
        )
    })?;
    let host = parsed.host_str().unwrap_or("").to_ascii_lowercase();
    if SAAS_HOSTS.iter().any(|h| host == *h) {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-004",
            "LabDesk supports self-hosted GitLab only.",
        )));
    }
    let scheme = parsed.scheme();
    match scheme {
        "https" => Ok(()),
        "http" => {
            if host_allows_plain_http(&host) {
                Ok(())
            } else {
                Err(LabDeskError::App(
                    ErrorInfo::new("LD-CFG-003", "Config value invalid: base_url").with_detail(
                        "http:// is only allowed for loopback or RFC1918 private hosts; use https for public names",
                    ),
                ))
            }
        }
        _ => Err(LabDeskError::App(
            ErrorInfo::new("LD-CFG-003", "Config value invalid: base_url")
                .with_detail("API base URL must use https (or http for LAN/loopback)"),
        )),
    }
}

/// Back-compat alias — prefer [`validate_base_url`].
pub fn reject_saas_url(base_url: &str) -> Result<()> {
    validate_base_url(base_url)
}

fn host_allows_plain_http(host: &str) -> bool {
    if host == "localhost" || host.ends_with(".localhost") {
        return true;
    }
    match host.parse::<std::net::IpAddr>() {
        Ok(std::net::IpAddr::V4(v4)) => v4.is_loopback() || v4.is_private(),
        Ok(std::net::IpAddr::V6(v6)) => v6.is_loopback(),
        Err(_) => false,
    }
}

pub fn normalize_base_url(base_url: &str) -> String {
    base_url.trim().trim_end_matches('/').to_string()
}

pub fn keyring_account_for(base_url: &str, account_id: &str) -> String {
    format!("labdesk:{}:{}", normalize_base_url(base_url), account_id)
}

/// Legacy V1 keyring id (URL only) — kept on migrate so existing PATs still load.
pub fn legacy_keyring_account_for(base_url: &str) -> String {
    format!("labdesk:{}", normalize_base_url(base_url))
}

pub fn load_or_default(paths: &AppPaths) -> Result<AppConfig> {
    paths.ensure_dirs().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CFG-012", "Could not save settings.").with_detail(e.to_string()),
        )
    })?;

    let path = paths.config_toml();
    if !path.exists() {
        let mut cfg = default_config();
        save(paths, &mut cfg)?;
        return Ok(cfg);
    }

    let text = fs::read_to_string(&path).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new(
                "LD-CFG-002",
                "Config file is invalid and could not be read.",
            )
            .with_detail(e.to_string()),
        )
    })?;

    let mut cfg = parse_document(&text)?;
    // Persist host/account split when we migrated legacy instance keyring fields.
    let legacy_in_file = text.contains("keyring_account")
        && text
            .lines()
            .any(|l| l.trim_start().starts_with("[[instances]]"))
        && !text.contains("[[accounts]]");
    if legacy_in_file && !cfg.accounts.is_empty() {
        save(paths, &mut cfg)?;
    }
    Ok(cfg)
}

pub fn parse_document(text: &str) -> Result<AppConfig> {
    let document: DocumentMut = text.parse().map_err(|e: toml_edit::TomlError| {
        LabDeskError::App(
            ErrorInfo::new(
                "LD-CFG-002",
                "Config file is invalid and could not be read.",
            )
            .with_detail(e.to_string()),
        )
    })?;

    let general = read_general(&document)?;
    let (instances, accounts, general) = read_instances_and_accounts(&document, general)?;
    Ok(AppConfig {
        general,
        instances,
        accounts,
        document,
    })
}

fn default_config() -> AppConfig {
    let mut document = DocumentMut::new();
    let mut general = Table::new();
    general["theme"] = value("system");
    general["default_clone_dir"] = value("~/Projects");
    general["check_for_updates"] = Item::Value(Value::from(true));
    general["active_ui_view"] = value("projects");
    general["ui_shell"] = value("classic");
    document["general"] = Item::Table(general);
    document["instances"] = Item::ArrayOfTables(toml_edit::ArrayOfTables::new());
    document["accounts"] = Item::ArrayOfTables(toml_edit::ArrayOfTables::new());

    AppConfig {
        general: GeneralConfig::default(),
        instances: Vec::new(),
        accounts: Vec::new(),
        document,
    }
}

fn read_general(doc: &DocumentMut) -> Result<GeneralConfig> {
    let Some(table) = doc.get("general").and_then(|i| i.as_table()) else {
        return Ok(GeneralConfig::default());
    };

    Ok(GeneralConfig {
        theme: table
            .get("theme")
            .and_then(|v| v.as_str())
            .unwrap_or("system")
            .to_string(),
        default_clone_dir: table
            .get("default_clone_dir")
            .and_then(|v| v.as_str())
            .unwrap_or("~/Projects")
            .to_string(),
        check_for_updates: table
            .get("check_for_updates")
            .and_then(|v| v.as_bool())
            .unwrap_or(true),
        active_instance_id: table
            .get("active_instance_id")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string()),
        active_account_id: table
            .get("active_account_id")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string()),
        active_ui_view: table
            .get("active_ui_view")
            .and_then(|v| v.as_str())
            .unwrap_or("projects")
            .to_string(),
        ui_shell: table
            .get("ui_shell")
            .and_then(|v| v.as_str())
            .unwrap_or("classic")
            .to_string(),
    })
}

/// Read hosts + accounts; migrate legacy instance rows that still carry keyring fields.
fn read_instances_and_accounts(
    doc: &DocumentMut,
    mut general: GeneralConfig,
) -> Result<(Vec<InstanceConfig>, Vec<AccountConfig>, GeneralConfig)> {
    let mut instances = Vec::new();
    let mut accounts = read_accounts(doc)?;

    let Some(array) = doc.get("instances").and_then(|i| i.as_array_of_tables()) else {
        return Ok((instances, accounts, general));
    };

    for table in array.iter() {
        let id = required_str(table, "id")?;
        let name = required_str(table, "name")?;
        let base_url = normalize_base_url(&required_str(table, "base_url")?);
        reject_saas_url(&base_url)?;
        let created_at = table
            .get("created_at")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let ssl_mode = table
            .get("ssl_mode")
            .and_then(|v| v.as_str())
            .unwrap_or("strict")
            .to_string();
        let api_version = table
            .get("api_version")
            .and_then(|v| v.as_str())
            .unwrap_or("v4")
            .to_string();

        // Legacy: keyring lived on the instance row.
        let legacy_keyring = table
            .get("keyring_account")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
        if let Some(keyring_account) = legacy_keyring {
            let already = accounts.iter().any(|a| a.instance_id == id);
            if !already {
                let acc_id = Uuid::new_v4().to_string();
                // Prefer existing keyring string so the PAT still resolves.
                let keyring = if keyring_account.is_empty() {
                    legacy_keyring_account_for(&base_url)
                } else {
                    keyring_account
                };
                accounts.push(AccountConfig {
                    id: acc_id.clone(),
                    instance_id: id.clone(),
                    name: name.clone(),
                    username: None,
                    api_auth: table
                        .get("api_auth")
                        .and_then(|v| v.as_str())
                        .unwrap_or("PAT")
                        .to_string(),
                    keyring_account: keyring,
                    git_https_auth: table
                        .get("git_https_auth")
                        .and_then(|v| v.as_str())
                        .unwrap_or("credential_helper")
                        .to_string(),
                    created_at: created_at.clone(),
                    last_connected: table
                        .get("last_connected")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string()),
                    gitlab_version: table
                        .get("gitlab_version")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string()),
                    gitlab_revision: table
                        .get("gitlab_revision")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string()),
                });
                if general.active_account_id.is_none()
                    && general.active_instance_id.as_deref() == Some(id.as_str())
                {
                    general.active_account_id = Some(acc_id);
                }
            }
        }

        instances.push(InstanceConfig {
            id,
            name,
            base_url,
            api_version,
            ssl_mode,
            created_at,
        });
    }

    // If we migrated accounts but active_account_id still unset, pick first.
    if general.active_account_id.is_none() {
        if let Some(first) = accounts.first() {
            general.active_account_id = Some(first.id.clone());
            general.active_instance_id = Some(first.instance_id.clone());
        }
    } else if let Some(acc_id) = general.active_account_id.clone() {
        if let Some(acc) = accounts.iter().find(|a| a.id == acc_id) {
            general.active_instance_id = Some(acc.instance_id.clone());
        }
    }

    Ok((instances, accounts, general))
}

fn read_accounts(doc: &DocumentMut) -> Result<Vec<AccountConfig>> {
    let Some(array) = doc.get("accounts").and_then(|i| i.as_array_of_tables()) else {
        return Ok(Vec::new());
    };
    let mut out = Vec::new();
    for table in array.iter() {
        out.push(AccountConfig {
            id: required_str(table, "id")?,
            instance_id: required_str(table, "instance_id")?,
            name: required_str(table, "name")?,
            username: table
                .get("username")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
            api_auth: table
                .get("api_auth")
                .and_then(|v| v.as_str())
                .unwrap_or("PAT")
                .to_string(),
            keyring_account: required_str(table, "keyring_account")?,
            git_https_auth: table
                .get("git_https_auth")
                .and_then(|v| v.as_str())
                .unwrap_or("credential_helper")
                .to_string(),
            created_at: table
                .get("created_at")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            last_connected: table
                .get("last_connected")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
            gitlab_version: table
                .get("gitlab_version")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
            gitlab_revision: table
                .get("gitlab_revision")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
        });
    }
    Ok(out)
}

fn required_str(table: &Table, key: &str) -> Result<String> {
    table
        .get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| {
            LabDeskError::App(ErrorInfo::new(
                "LD-CFG-003",
                format!("Config value invalid: {key}"),
            ))
        })
}

fn value(s: &str) -> Item {
    Item::Value(Value::from(s))
}

pub fn save(paths: &AppPaths, cfg: &mut AppConfig) -> Result<()> {
    sync_document(cfg);
    paths.ensure_dirs().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CFG-012", "Could not save settings.").with_detail(e.to_string()),
        )
    })?;

    let text = cfg.document.to_string();
    fs::write(paths.config_toml(), text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CFG-012", "Could not save settings.").with_detail(e.to_string()),
        )
    })?;
    Ok(())
}

pub fn save_known_good(paths: &AppPaths) -> Result<()> {
    let src = paths.config_toml();
    let dst = paths.known_good_toml();
    if src.exists() {
        fs::copy(&src, &dst).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-CFG-012", "Could not save settings.")
                    .with_detail(format!("known-good snapshot: {e}")),
            )
        })?;
    }
    Ok(())
}

pub fn revert_to_known_good(paths: &AppPaths) -> Result<()> {
    let src = paths.known_good_toml();
    let dst = paths.config_toml();
    if !src.exists() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-011",
            "Startup failed and no good config backup was found.",
        )));
    }
    fs::copy(&src, &dst).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CFG-012", "Could not save settings.").with_detail(e.to_string()),
        )
    })?;
    Ok(())
}

fn sync_document(cfg: &mut AppConfig) {
    let general = cfg
        .document
        .entry("general")
        .or_insert(Item::Table(Table::new()))
        .as_table_mut()
        .expect("general table");

    general["theme"] = value(&cfg.general.theme);
    general["default_clone_dir"] = value(&cfg.general.default_clone_dir);
    general["check_for_updates"] = Item::Value(Value::from(cfg.general.check_for_updates));
    match &cfg.general.active_instance_id {
        Some(id) => general["active_instance_id"] = value(id),
        None => {
            general.remove("active_instance_id");
        }
    }
    match &cfg.general.active_account_id {
        Some(id) => general["active_account_id"] = value(id),
        None => {
            general.remove("active_account_id");
        }
    }
    general["active_ui_view"] = value(&cfg.general.active_ui_view);
    general["ui_shell"] = value(&cfg.general.ui_shell);

    let mut inst_array = toml_edit::ArrayOfTables::new();
    for inst in &cfg.instances {
        let mut t = Table::new();
        t["id"] = value(&inst.id);
        t["name"] = value(&inst.name);
        t["base_url"] = value(&inst.base_url);
        t["api_version"] = value(&inst.api_version);
        t["ssl_mode"] = value(&inst.ssl_mode);
        t["created_at"] = value(&inst.created_at);
        inst_array.push(t);
    }
    cfg.document["instances"] = Item::ArrayOfTables(inst_array);

    let mut acc_array = toml_edit::ArrayOfTables::new();
    for acc in &cfg.accounts {
        let mut t = Table::new();
        t["id"] = value(&acc.id);
        t["instance_id"] = value(&acc.instance_id);
        t["name"] = value(&acc.name);
        if let Some(u) = &acc.username {
            t["username"] = value(u);
        }
        t["api_auth"] = value(&acc.api_auth);
        t["keyring_account"] = value(&acc.keyring_account);
        t["git_https_auth"] = value(&acc.git_https_auth);
        t["created_at"] = value(&acc.created_at);
        if let Some(v) = &acc.last_connected {
            t["last_connected"] = value(v);
        }
        if let Some(v) = &acc.gitlab_version {
            t["gitlab_version"] = value(v);
        }
        if let Some(v) = &acc.gitlab_revision {
            t["gitlab_revision"] = value(v);
        }
        acc_array.push(t);
    }
    cfg.document["accounts"] = Item::ArrayOfTables(acc_array);
}

/// Find or create a host by normalized base_url (does not clear other hosts).
pub fn upsert_instance(
    cfg: &mut AppConfig,
    name: String,
    base_url: String,
    ssl_mode: String,
) -> Result<InstanceConfig> {
    let base_url = normalize_base_url(&base_url);
    reject_saas_url(&base_url)?;
    let now = iso8601_now();

    if let Some(existing) = cfg.instances.iter_mut().find(|i| i.base_url == base_url) {
        existing.name = name;
        existing.ssl_mode = ssl_mode;
        return Ok(existing.clone());
    }

    let inst = InstanceConfig {
        id: Uuid::new_v4().to_string(),
        name,
        base_url,
        api_version: "v4".into(),
        ssl_mode,
        created_at: now,
    };
    cfg.instances.push(inst.clone());
    Ok(inst)
}

/// Add a new account on an existing host and make it active.
pub fn add_account(
    cfg: &mut AppConfig,
    instance_id: &str,
    name: String,
) -> Result<AccountConfig> {
    let inst = cfg
        .instances
        .iter()
        .find(|i| i.id == instance_id)
        .cloned()
        .ok_or_else(|| {
            LabDeskError::App(ErrorInfo::new(
                "LD-CFG-003",
                "Config value invalid: instance_id",
            ))
        })?;
    let now = iso8601_now();
    let id = Uuid::new_v4().to_string();
    let keyring_account = keyring_account_for(&inst.base_url, &id);
    let acc = AccountConfig {
        id: id.clone(),
        instance_id: inst.id.clone(),
        name,
        username: None,
        api_auth: "PAT".into(),
        keyring_account,
        git_https_auth: "credential_helper".into(),
        created_at: now,
        last_connected: None,
        gitlab_version: None,
        gitlab_revision: None,
    };
    cfg.accounts.push(acc.clone());
    set_active_account(cfg, &id)?;
    Ok(acc)
}

/// Create/find host, add account, activate (connect flow).
pub fn connect_account(
    cfg: &mut AppConfig,
    host_name: String,
    account_name: String,
    base_url: String,
    ssl_mode: String,
) -> Result<(InstanceConfig, AccountConfig)> {
    let inst = upsert_instance(cfg, host_name, base_url, ssl_mode)?;
    let acc = add_account(cfg, &inst.id, account_name)?;
    Ok((inst, acc))
}

pub fn set_active_account(cfg: &mut AppConfig, account_id: &str) -> Result<()> {
    let acc = cfg
        .accounts
        .iter()
        .find(|a| a.id == account_id)
        .ok_or_else(|| {
            LabDeskError::App(ErrorInfo::new(
                "LD-CFG-003",
                "Config value invalid: active_account_id",
            ))
        })?;
    cfg.general.active_account_id = Some(acc.id.clone());
    cfg.general.active_instance_id = Some(acc.instance_id.clone());
    Ok(())
}

pub fn touch_last_connected(acc: &mut AccountConfig) {
    acc.last_connected = Some(iso8601_now());
}

pub(crate) fn iso8601_now_public() -> String {
    iso8601_now()
}

fn iso8601_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = secs / 86400;
    let tod = secs % 86400;
    let hours = tod / 3600;
    let mins = (tod % 3600) / 60;
    let s = tod % 60;
    let (y, m, d) = civil_from_days(days as i64);
    format!("{y:04}-{m:02}-{d:02}T{hours:02}:{mins:02}:{s:02}Z")
}

fn civil_from_days(days: i64) -> (i32, u32, u32) {
    let z = days + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = (yoe as i64) + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y as i32, m as u32, d as u32)
}

pub fn config_path_display(paths: &AppPaths) -> String {
    paths.config_toml().display().to_string()
}

/// Expand `~` / `$HOME` for clone destinations.
pub fn expand_user_path(path: &str) -> String {
    let path = path.trim();
    if path == "~" {
        return dirs_home().unwrap_or_else(|| path.to_string());
    }
    if let Some(rest) = path.strip_prefix("~/") {
        if let Some(home) = dirs_home() {
            return format!(
                "{}/{}",
                home.trim_end_matches('/'),
                rest.trim_start_matches('/')
            );
        }
    }
    path.to_string()
}

fn dirs_home() -> Option<String> {
    std::env::var_os("HOME")
        .map(|h| h.to_string_lossy().into_owned())
        .or_else(|| {
            directories::BaseDirs::new().map(|b| b.home_dir().display().to_string())
        })
}

pub fn set_default_clone_dir(paths: &AppPaths, dir: &str) -> Result<String> {
    let trimmed = dir.trim();
    if trimmed.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-003",
            "Config value invalid: default_clone_dir",
        )));
    }
    let expanded = expand_user_path(trimmed);
    // Store the path the user chose (prefer absolute expanded form for clarity).
    let mut cfg = load_or_default(paths)?;
    cfg.general.default_clone_dir = expanded.clone();
    save(paths, &mut cfg)?;
    // Preference change after a good launch — refresh known-good so hang
    // recovery keeps the new clone dir.
    let _ = save_known_good(paths);
    Ok(expanded)
}

pub fn get_default_clone_dir(paths: &AppPaths) -> Result<(String, String)> {
    let cfg = load_or_default(paths)?;
    let stored = cfg.general.default_clone_dir.clone();
    let expanded = expand_user_path(&stored);
    Ok((stored, expanded))
}

/// Persist `general.theme` only (does not touch config-only prefs).
pub fn set_theme(paths: &AppPaths, theme: &str) -> Result<()> {
    let theme = theme.trim();
    if !matches!(theme, "system" | "light" | "dark") {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-003",
            "Config value invalid: theme",
        )));
    }
    let mut cfg = load_or_default(paths)?;
    cfg.general.theme = theme.to_string();
    save(paths, &mut cfg)?;
    let _ = save_known_good(paths);
    Ok(())
}

/// Persist theme + Flatpak update-check preference (clone dir is separate).
/// Prefer `set_theme` from UI; this remains for scripts / full writes.
#[allow(dead_code)]
pub fn set_general_preferences(
    paths: &AppPaths,
    theme: &str,
    check_for_updates: bool,
) -> Result<()> {
    set_theme(paths, theme)?;
    let mut cfg = load_or_default(paths)?;
    cfg.general.check_for_updates = check_for_updates;
    save(paths, &mut cfg)?;
    let _ = save_known_good(paths);
    Ok(())
}

/// Persist which pluggable main-window view is active.
pub fn set_active_ui_view(paths: &AppPaths, view_id: &str) -> Result<()> {
    let view_id = view_id.trim();
    if view_id.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-003",
            "Config value invalid: active_ui_view",
        )));
    }
    let mut cfg = load_or_default(paths)?;
    cfg.general.active_ui_view = view_id.to_string();
    save(paths, &mut cfg)?;
    let _ = save_known_good(paths);
    Ok(())
}

/// Persist main-window shell layout (`classic` | `sidebar`).
pub fn set_ui_shell(paths: &AppPaths, shell: &str) -> Result<()> {
    let shell = shell.trim();
    if !matches!(shell, "classic" | "sidebar") {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-CFG-003",
            "Config value invalid: ui_shell",
        )));
    }
    let mut cfg = load_or_default(paths)?;
    cfg.general.ui_shell = shell.to_string();
    save(paths, &mut cfg)?;
    let _ = save_known_good(paths);
    Ok(())
}

#[allow(dead_code)]
pub fn path_exists(path: &Path) -> bool {
    path.exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn https_public_ok() {
        assert!(validate_base_url("https://gitlab.example.com").is_ok());
    }

    #[test]
    fn http_rfc1918_ok() {
        assert!(validate_base_url("http://192.168.0.214:8929").is_ok());
        assert!(validate_base_url("http://10.1.2.3").is_ok());
        assert!(validate_base_url("http://172.16.0.1").is_ok());
        assert!(validate_base_url("http://127.0.0.1").is_ok());
        assert!(validate_base_url("http://localhost:8080").is_ok());
    }

    #[test]
    fn http_public_rejected() {
        assert!(validate_base_url("http://gitlab.example.com").is_err());
    }

    #[test]
    fn saas_rejected() {
        assert!(validate_base_url("https://gitlab.com").is_err());
    }

    #[test]
    fn migrate_legacy_instance_to_account() {
        let toml = r#"
[general]
active_instance_id = "inst-1"
theme = "system"
default_clone_dir = "~/Projects"
check_for_updates = true

[[instances]]
id = "inst-1"
name = "Lab"
base_url = "https://gitlab.example.com"
api_version = "v4"
api_auth = "PAT"
keyring_account = "labdesk:https://gitlab.example.com"
git_https_auth = "credential_helper"
ssl_mode = "strict"
created_at = "2026-01-01T00:00:00Z"
"#;
        let cfg = parse_document(toml).expect("parse");
        assert_eq!(cfg.instances.len(), 1);
        assert_eq!(cfg.accounts.len(), 1);
        assert_eq!(cfg.accounts[0].instance_id, "inst-1");
        assert_eq!(
            cfg.accounts[0].keyring_account,
            "labdesk:https://gitlab.example.com"
        );
        assert_eq!(
            cfg.general.active_account_id.as_deref(),
            Some(cfg.accounts[0].id.as_str())
        );
        assert!(cfg.instances[0].base_url.contains("gitlab.example.com"));
    }

    #[test]
    fn two_accounts_same_host_distinct_keyring() {
        let mut cfg = default_config();
        let inst = upsert_instance(
            &mut cfg,
            "Lab".into(),
            "https://gitlab.example.com".into(),
            "strict".into(),
        )
        .unwrap();
        let a1 = add_account(&mut cfg, &inst.id, "Work".into()).unwrap();
        let a2 = add_account(&mut cfg, &inst.id, "Personal".into()).unwrap();
        assert_ne!(a1.keyring_account, a2.keyring_account);
        assert!(a1.keyring_account.contains(&a1.id));
        assert!(a2.keyring_account.contains(&a2.id));
        assert_eq!(cfg.instances.len(), 1);
        assert_eq!(cfg.accounts.len(), 2);
    }

    #[test]
    fn upsert_instance_keeps_other_hosts() {
        let mut cfg = default_config();
        upsert_instance(
            &mut cfg,
            "A".into(),
            "https://a.example.com".into(),
            "strict".into(),
        )
        .unwrap();
        upsert_instance(
            &mut cfg,
            "B".into(),
            "https://b.example.com".into(),
            "strict".into(),
        )
        .unwrap();
        assert_eq!(cfg.instances.len(), 2);
    }
}
