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
    /// Registered UI view id (e.g. `projects`, `settings`).
    pub active_ui_view: String,
    /// Main window shell: `classic` (top nav) or `sidebar`.
    pub ui_shell: String,
}

#[derive(Debug, Clone)]
pub struct InstanceConfig {
    pub id: String,
    pub name: String,
    pub base_url: String,
    pub api_version: String,
    pub api_auth: String,
    pub keyring_account: String,
    pub git_https_auth: String,
    pub ssl_mode: String,
    pub created_at: String,
    pub last_connected: Option<String>,
    pub gitlab_version: Option<String>,
    pub gitlab_revision: Option<String>,
}

#[derive(Debug)]
pub struct AppConfig {
    pub general: GeneralConfig,
    pub instances: Vec<InstanceConfig>,
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
            active_ui_view: "projects".into(),
            ui_shell: "classic".into(),
        }
    }
}

impl AppConfig {
    pub fn active_instance(&self) -> Option<&InstanceConfig> {
        let id = self.general.active_instance_id.as_deref()?;
        self.instances.iter().find(|i| i.id == id)
    }

    pub fn active_instance_mut(&mut self) -> Option<&mut InstanceConfig> {
        let id = self.general.active_instance_id.clone()?;
        self.instances.iter_mut().find(|i| i.id == id)
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

pub fn keyring_account_for(base_url: &str) -> String {
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

    parse_document(&text)
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
    let instances = read_instances(&document)?;
    Ok(AppConfig {
        general,
        instances,
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

    AppConfig {
        general: GeneralConfig::default(),
        instances: Vec::new(),
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

fn read_instances(doc: &DocumentMut) -> Result<Vec<InstanceConfig>> {
    let Some(array) = doc.get("instances").and_then(|i| i.as_array_of_tables()) else {
        return Ok(Vec::new());
    };

    let mut out = Vec::new();
    for table in array.iter() {
        let id = required_str(table, "id")?;
        let name = required_str(table, "name")?;
        let base_url = required_str(table, "base_url")?;
        reject_saas_url(&base_url)?;
        out.push(InstanceConfig {
            id,
            name,
            base_url: normalize_base_url(&base_url),
            api_version: table
                .get("api_version")
                .and_then(|v| v.as_str())
                .unwrap_or("v4")
                .to_string(),
            api_auth: table
                .get("api_auth")
                .and_then(|v| v.as_str())
                .unwrap_or("PAT")
                .to_string(),
            keyring_account: table
                .get("keyring_account")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| keyring_account_for(&base_url)),
            git_https_auth: table
                .get("git_https_auth")
                .and_then(|v| v.as_str())
                .unwrap_or("credential_helper")
                .to_string(),
            ssl_mode: table
                .get("ssl_mode")
                .and_then(|v| v.as_str())
                .unwrap_or("strict")
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
    general["active_ui_view"] = value(&cfg.general.active_ui_view);
    general["ui_shell"] = value(&cfg.general.ui_shell);

    let mut array = toml_edit::ArrayOfTables::new();
    for inst in &cfg.instances {
        let mut t = Table::new();
        t["id"] = value(&inst.id);
        t["name"] = value(&inst.name);
        t["base_url"] = value(&inst.base_url);
        t["api_version"] = value(&inst.api_version);
        t["api_auth"] = value(&inst.api_auth);
        t["keyring_account"] = value(&inst.keyring_account);
        t["git_https_auth"] = value(&inst.git_https_auth);
        t["ssl_mode"] = value(&inst.ssl_mode);
        t["created_at"] = value(&inst.created_at);
        if let Some(v) = &inst.last_connected {
            t["last_connected"] = value(v);
        }
        if let Some(v) = &inst.gitlab_version {
            t["gitlab_version"] = value(v);
        }
        if let Some(v) = &inst.gitlab_revision {
            t["gitlab_revision"] = value(v);
        }
        array.push(t);
    }
    cfg.document["instances"] = Item::ArrayOfTables(array);
}

pub fn upsert_instance(
    cfg: &mut AppConfig,
    name: String,
    base_url: String,
    ssl_mode: String,
) -> Result<InstanceConfig> {
    let base_url = normalize_base_url(&base_url);
    reject_saas_url(&base_url)?;

    let now = iso8601_now();
    let keyring_account = keyring_account_for(&base_url);

    if let Some(existing) = cfg.instances.iter_mut().find(|i| i.base_url == base_url) {
        existing.name = name;
        existing.ssl_mode = ssl_mode;
        existing.keyring_account = keyring_account;
        cfg.general.active_instance_id = Some(existing.id.clone());
        return Ok(existing.clone());
    }

    let inst = InstanceConfig {
        id: Uuid::new_v4().to_string(),
        name,
        base_url,
        api_version: "v4".into(),
        api_auth: "PAT".into(),
        keyring_account,
        git_https_auth: "credential_helper".into(),
        ssl_mode,
        created_at: now,
        last_connected: None,
        gitlab_version: None,
        gitlab_revision: None,
    };
    cfg.general.active_instance_id = Some(inst.id.clone());
    // V1 UI: one active instance in the list.
    cfg.instances.clear();
    cfg.instances.push(inst.clone());
    Ok(inst)
}

pub fn touch_last_connected(inst: &mut InstanceConfig) {
    inst.last_connected = Some(iso8601_now());
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
}
