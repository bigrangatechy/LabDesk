//! LabDesk core — PyO3 module.
//!
//! Slice: config + keyring PAT + GET /user + project list cache.

mod api_client;
mod cache;
mod config;
mod diff_engine;
mod error;
mod git_ops;
mod paths;
mod secrets;

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};

use crate::error::{ErrorInfo, LabDeskError};

/// Return detected config/data paths.
#[pyfunction]
fn get_paths(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let d = PyDict::new(py);
    d.set_item("config_dir", paths.config_dir.display().to_string())?;
    d.set_item("data_dir", paths.data_dir.display().to_string())?;
    d.set_item("config_toml", paths.config_toml().display().to_string())?;
    d.set_item(
        "known_good_toml",
        paths.known_good_toml().display().to_string(),
    )?;
    d.set_item("cache_db", paths.cache_db().display().to_string())?;
    Ok(d.into())
}

/// Load config (creates defaults if missing).
#[pyfunction]
fn load_config(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    match config::load_or_default(&paths) {
        Ok(cfg) => config_to_dict(py, &cfg),
        Err(e) => Err(e.into()),
    }
}

fn config_to_dict(py: Python<'_>, cfg: &config::AppConfig) -> PyResult<PyObject> {
    let root = PyDict::new(py);
    let general = PyDict::new(py);
    general.set_item("theme", &cfg.general.theme)?;
    general.set_item("default_clone_dir", &cfg.general.default_clone_dir)?;
    general.set_item("check_for_updates", cfg.general.check_for_updates)?;
    general.set_item(
        "active_instance_id",
        cfg.general.active_instance_id.as_deref(),
    )?;
    general.set_item(
        "active_account_id",
        cfg.general.active_account_id.as_deref(),
    )?;
    general.set_item("active_ui_view", &cfg.general.active_ui_view)?;
    general.set_item("ui_shell", &cfg.general.ui_shell)?;
    root.set_item("general", general)?;

    let instances = pyo3::types::PyList::empty(py);
    for inst in &cfg.instances {
        let d = PyDict::new(py);
        d.set_item("id", &inst.id)?;
        d.set_item("name", &inst.name)?;
        d.set_item("base_url", &inst.base_url)?;
        d.set_item("api_version", &inst.api_version)?;
        d.set_item("ssl_mode", &inst.ssl_mode)?;
        d.set_item("created_at", &inst.created_at)?;
        instances.append(d)?;
    }
    root.set_item("instances", instances)?;

    let accounts = pyo3::types::PyList::empty(py);
    for acc in &cfg.accounts {
        accounts.append(account_to_dict(py, acc)?)?;
    }
    root.set_item("accounts", accounts)?;
    root.set_item(
        "config_path",
        config::config_path_display(&paths::AppPaths::detect()),
    )?;
    Ok(root.into())
}

fn account_to_dict(py: Python<'_>, acc: &config::AccountConfig) -> PyResult<PyObject> {
    let d = PyDict::new(py);
    d.set_item("id", &acc.id)?;
    d.set_item("instance_id", &acc.instance_id)?;
    d.set_item("name", &acc.name)?;
    d.set_item("username", acc.username.as_deref())?;
    d.set_item("api_auth", &acc.api_auth)?;
    d.set_item("keyring_account", &acc.keyring_account)?;
    d.set_item("git_https_auth", &acc.git_https_auth)?;
    d.set_item("created_at", &acc.created_at)?;
    d.set_item("last_connected", acc.last_connected.as_deref())?;
    d.set_item("gitlab_version", acc.gitlab_version.as_deref())?;
    d.set_item("gitlab_revision", acc.gitlab_revision.as_deref())?;
    Ok(d.into())
}

fn instance_to_dict(py: Python<'_>, inst: &config::InstanceConfig) -> PyResult<PyObject> {
    let d = PyDict::new(py);
    d.set_item("id", &inst.id)?;
    d.set_item("name", &inst.name)?;
    d.set_item("base_url", &inst.base_url)?;
    d.set_item("api_version", &inst.api_version)?;
    d.set_item("ssl_mode", &inst.ssl_mode)?;
    d.set_item("created_at", &inst.created_at)?;
    Ok(d.into())
}

/// Back-compat: same display name for host + account until UI is updated.
#[pyfunction]
#[pyo3(signature = (name, base_url, pat, ssl_mode="strict"))]
fn connect_instance(
    py: Python<'_>,
    name: String,
    base_url: String,
    pat: String,
    ssl_mode: &str,
) -> PyResult<PyObject> {
    connect_account(py, name.clone(), name, base_url, pat, ssl_mode)
}

/// Connect account: find/create host, add account, validate PAT, store + save.
#[pyfunction]
#[pyo3(signature = (host_name, account_name, base_url, pat, ssl_mode="strict"))]
fn connect_account(
    py: Python<'_>,
    host_name: String,
    account_name: String,
    base_url: String,
    pat: String,
    ssl_mode: &str,
) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let mut cfg = config::load_or_default(&paths)?;

    let pat = pat.trim().to_string();
    if pat.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-001",
            "Authentication failed. Check your token.",
        ))
        .into());
    }

    let (inst, acc) = config::connect_account(
        &mut cfg,
        host_name,
        account_name,
        base_url,
        ssl_mode.to_string(),
    )?;
    let account_id = acc.id.clone();
    let keyring = acc.keyring_account.clone();
    let base_url = inst.base_url.clone();
    let instance_id = inst.id.clone();

    let user = match api_client::get_user(&base_url, &pat, ssl_mode) {
        Ok(u) => u,
        Err(e) => {
            if e.info().code == "LD-AUTH-001" {
                let _ = secrets::clear_pat(&keyring);
            }
            return Err(e.into());
        }
    };

    secrets::store_pat(&keyring, &pat)?;

    if let Some(active) = cfg.active_account_mut() {
        active.username = Some(user.username.clone());
        config::touch_last_connected(active);
        if let Ok(Some(ver)) = api_client::get_version(&base_url, &pat, ssl_mode) {
            active.gitlab_version = ver.version;
            active.gitlab_revision = ver.revision;
        }
    }

    config::save(&paths, &mut cfg)?;
    config::save_known_good(&paths)?;

    // Best-effort project refresh after connect (failures don't undo connect).
    let project_count =
        match refresh_projects_inner(&paths, &account_id, &base_url, &pat, ssl_mode) {
            Ok(n) => n,
            Err(_) => 0,
        };

    let out = PyDict::new(py);
    out.set_item("account_id", &account_id)?;
    out.set_item("instance_id", &instance_id)?;
    out.set_item("base_url", &base_url)?;
    out.set_item("keyring_account", &keyring)?;
    let u = PyDict::new(py);
    u.set_item("id", user.id)?;
    u.set_item("username", user.username)?;
    u.set_item("name", user.name)?;
    u.set_item("web_url", user.web_url)?;
    out.set_item("user", u)?;
    out.set_item("config_path", config::config_path_display(&paths))?;
    out.set_item("project_count", project_count)?;
    Ok(out.into())
}

/// Add an account on an existing host, validate PAT, store + activate.
#[pyfunction]
fn add_account(
    py: Python<'_>,
    instance_id: String,
    account_name: String,
    pat: String,
) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let mut cfg = config::load_or_default(&paths)?;

    let pat = pat.trim().to_string();
    if pat.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-001",
            "Authentication failed. Check your token.",
        ))
        .into());
    }

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
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();

    let acc = config::add_account(&mut cfg, &instance_id, account_name)?;
    let account_id = acc.id.clone();
    let keyring = acc.keyring_account.clone();

    let user = match api_client::get_user(&base_url, &pat, &ssl_mode) {
        Ok(u) => u,
        Err(e) => {
            if e.info().code == "LD-AUTH-001" {
                let _ = secrets::clear_pat(&keyring);
            }
            return Err(e.into());
        }
    };

    secrets::store_pat(&keyring, &pat)?;

    if let Some(active) = cfg.active_account_mut() {
        active.username = Some(user.username.clone());
        config::touch_last_connected(active);
        if let Ok(Some(ver)) = api_client::get_version(&base_url, &pat, &ssl_mode) {
            active.gitlab_version = ver.version;
            active.gitlab_revision = ver.revision;
        }
    }

    config::save(&paths, &mut cfg)?;
    config::save_known_good(&paths)?;

    let project_count =
        match refresh_projects_inner(&paths, &account_id, &base_url, &pat, &ssl_mode) {
            Ok(n) => n,
            Err(_) => 0,
        };

    let out = PyDict::new(py);
    out.set_item("account_id", &account_id)?;
    out.set_item("instance_id", &instance_id)?;
    out.set_item("base_url", &base_url)?;
    out.set_item("keyring_account", &keyring)?;
    let u = PyDict::new(py);
    u.set_item("id", user.id)?;
    u.set_item("username", user.username)?;
    u.set_item("name", user.name)?;
    u.set_item("web_url", user.web_url)?;
    out.set_item("user", u)?;
    out.set_item("config_path", config::config_path_display(&paths))?;
    out.set_item("project_count", project_count)?;
    Ok(out.into())
}

/// List configured GitLab hosts.
#[pyfunction]
fn list_instances(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let list = pyo3::types::PyList::empty(py);
    for inst in &cfg.instances {
        list.append(instance_to_dict(py, inst)?)?;
    }
    Ok(list.into())
}

/// List accounts, optionally filtered by host.
#[pyfunction]
#[pyo3(signature = (instance_id=None))]
fn list_accounts(py: Python<'_>, instance_id: Option<String>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let list = pyo3::types::PyList::empty(py);
    for acc in &cfg.accounts {
        if let Some(ref iid) = instance_id {
            if &acc.instance_id != iid {
                continue;
            }
        }
        list.append(account_to_dict(py, acc)?)?;
    }
    Ok(list.into())
}

/// Switch the active account (and its host).
#[pyfunction]
fn set_active_account(account_id: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let mut cfg = config::load_or_default(&paths)?;
    config::set_active_account(&mut cfg, &account_id)?;
    config::save(&paths, &mut cfg)?;
    let _ = config::save_known_good(&paths);
    Ok(())
}

fn refresh_projects_inner(
    paths: &paths::AppPaths,
    account_id: &str,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<usize, LabDeskError> {
    let projects = api_client::list_membership_projects(base_url, pat, ssl_mode)?;
    let conn = cache::open(paths).or_else(|_| cache::rebuild(paths))?;
    if cache::replace_projects(&conn, account_id, &projects).is_err() {
        let conn = cache::rebuild(paths)?;
        cache::replace_projects(&conn, account_id, &projects)?;
    }
    // Best-effort default-branch pipeline status for the Projects list icon.
    let conn = cache::open(paths).or_else(|_| cache::rebuild(paths))?;
    for p in &projects {
        let Some(branch) = p
            .default_branch
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
        else {
            continue;
        };
        match api_client::latest_pipeline(base_url, pat, ssl_mode, p.id as i64, branch) {
            Ok(Some(pipe)) => {
                let _ = cache::set_project_pipeline_status(
                    &conn,
                    account_id,
                    p.id as i64,
                    pipe.status.as_deref(),
                    pipe.web_url.as_deref(),
                );
            }
            Ok(None) => {
                let _ = cache::set_project_pipeline_status(
                    &conn,
                    account_id,
                    p.id as i64,
                    None,
                    None,
                );
            }
            Err(_) => {
                // Skip this project; list refresh still succeeded.
            }
        }
    }
    Ok(projects.len())
}

/// Fetch current user for the active account using the keyring PAT.
#[pyfunction]
fn fetch_current_user(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let instance_name = inst.name.clone();
    let account_name = acc.name.clone();
    let user = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        api_client::get_user(&base_url, &pat, &ssl_mode)
    })?;
    let u = PyDict::new(py);
    u.set_item("id", user.id)?;
    u.set_item("username", user.username)?;
    u.set_item("name", user.name)?;
    u.set_item("web_url", user.web_url)?;
    u.set_item("instance_name", instance_name)?;
    u.set_item("account_name", account_name)?;
    u.set_item("base_url", base_url)?;
    Ok(u.into())
}

/// Refresh projects from API into SQLite; returns count.
#[pyfunction]
fn refresh_projects(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let account_id = acc.id.clone();
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let count = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        refresh_projects_inner(&paths, &account_id, &base_url, &pat, &ssl_mode)
    })?;
    let d = PyDict::new(py);
    d.set_item("count", count)?;
    d.set_item("source", "api")?;
    Ok(d.into())
}

/// List cached projects for the active account (no network).
#[pyfunction]
#[pyo3(signature = (allow_stale=true))]
fn list_projects(py: Python<'_>, allow_stale: bool) -> PyResult<PyObject> {
    let _ = allow_stale;
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };

    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let rows = cache::list_projects(&conn, &acc.id)?;
    let list = pyo3::types::PyList::empty(py);
    for p in rows {
        let d = PyDict::new(py);
        d.set_item("project_id", p.project_id)?;
        d.set_item("name", p.name)?;
        d.set_item("name_with_namespace", p.name_with_namespace)?;
        d.set_item("path_with_namespace", p.path_with_namespace)?;
        d.set_item("http_url_to_repo", p.http_url_to_repo)?;
        d.set_item("ssh_url_to_repo", p.ssh_url_to_repo)?;
        d.set_item("web_url", p.web_url)?;
        d.set_item("default_branch", p.default_branch)?;
        d.set_item("visibility", p.visibility)?;
        d.set_item("last_activity_at", p.last_activity_at)?;
        d.set_item("fetched_at", p.fetched_at)?;
        d.set_item("pipeline_status", p.pipeline_status)?;
        d.set_item("pipeline_web_url", p.pipeline_web_url)?;
        list.append(d)?;
    }
    Ok(list.into())
}

/// Clone a cached project into the default clone directory.
///
/// `transport` is `"https"` (default) or `"ssh"`.
#[pyfunction]
#[pyo3(signature = (project_id, transport="https"))]
fn clone_project(py: Python<'_>, project_id: i64, transport: &str) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let account_id = acc.id.clone();

    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let Some(project) = cache::get_cached_project(&conn, &account_id, project_id)? else {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-404", "Not found or no access.")
                .with_detail(format!("project_id {project_id} not in cache; refresh projects")),
        )
        .into());
    };

    let (_, clone_root) = config::get_default_clone_dir(&paths)?;
    let dest = git_ops::destination_for(
        std::path::Path::new(&clone_root),
        &project.path_with_namespace,
    );

    // Already cloned (by LabDesk or elsewhere) — adopt instead of failing.
    if git_ops::is_git_repository(&dest) {
        let root = git_ops::resolve_repo_root(&dest)?;
        let root_s = root.display().to_string();
        let url = git_ops::remote_url(&root, "origin")?
            .or(project.http_url_to_repo.clone())
            .or(project.ssh_url_to_repo.clone())
            .unwrap_or_default();
        let local_id = cache::upsert_local_repo(
            &conn,
            &account_id,
            Some(project.project_id),
            &root_s,
            &url,
        )?;
        let d = PyDict::new(py);
        d.set_item("path", root_s)?;
        d.set_item("clone_url", url)?;
        d.set_item("transport", "existing")?;
        d.set_item("local_repo_id", local_id)?;
        d.set_item("path_with_namespace", project.path_with_namespace)?;
        d.set_item("adopted_existing", true)?;
        return Ok(d.into());
    }

    let use_ssh = transport.eq_ignore_ascii_case("ssh");
    let (url, tr) = if use_ssh {
        let url = project.ssh_url_to_repo.clone().ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-030", "Clone failed.")
                    .with_detail("no ssh_url_to_repo for project"),
            )
        })?;
        (url, git_ops::CloneTransport::Ssh)
    } else {
        let url = project.http_url_to_repo.clone().ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-030", "Clone failed.")
                    .with_detail("no http_url_to_repo for project"),
            )
        })?;
        (url, git_ops::CloneTransport::Https)
    };

    let pat = if use_ssh {
        None
    } else {
        Some(secrets::load_pat(&acc.keyring_account)?)
    };

    let ssl_insecure = inst.ssl_mode == "allow_self_signed";
    let dest_owned = dest.clone();
    let url_owned = url.clone();
    py.allow_threads(|| {
        git_ops::clone_repository(&git_ops::CloneRequest {
            url: &url_owned,
            destination: &dest_owned,
            transport: tr,
            pat_fallback: pat.as_deref(),
            ssl_insecure,
        })
    })?;

    let local_id = cache::upsert_local_repo(
        &conn,
        &account_id,
        Some(project.project_id),
        &dest.display().to_string(),
        &url,
    )?;

    let d = PyDict::new(py);
    d.set_item("path", dest.display().to_string())?;
    d.set_item("clone_url", url)?;
    d.set_item("transport", if use_ssh { "ssh" } else { "https" })?;
    d.set_item("local_repo_id", local_id)?;
    d.set_item("path_with_namespace", project.path_with_namespace)?;
    Ok(d.into())
}

/// Look up a local clone path for a cached project id.
///
/// Also probes `{default_clone_dir}/{path_with_namespace}` and registers
/// it when an existing clone is found that LabDesk did not create.
#[pyfunction]
fn find_local_repo(py: Python<'_>, project_id: i64) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let account_id = acc.id.clone();
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let d = PyDict::new(py);

    if let Some((id, path)) = cache::find_local_repo_by_project(&conn, &account_id, project_id)? {
        let exists = std::path::Path::new(&path).join(".git").exists()
            || git_ops::is_git_repository(std::path::Path::new(&path));
        if exists {
            d.set_item("found", true)?;
            d.set_item("local_repo_id", id)?;
            d.set_item("path", path)?;
            d.set_item("exists", true)?;
            d.set_item("source", "cache")?;
            return Ok(d.into());
        }
        d.set_item("found", true)?;
        d.set_item("local_repo_id", id)?;
        d.set_item("path", path)?;
        d.set_item("exists", false)?;
        d.set_item("source", "cache")?;
        return Ok(d.into());
    }

    // Probe default clone location for a pre-existing working tree.
    if let Some(project) = cache::get_cached_project(&conn, &account_id, project_id)? {
        let (_, clone_root) = config::get_default_clone_dir(&paths)?;
        let candidate = git_ops::destination_for(
            std::path::Path::new(&clone_root),
            &project.path_with_namespace,
        );
        if git_ops::is_git_repository(&candidate) {
            let root = git_ops::resolve_repo_root(&candidate)?;
            let root_s = root.display().to_string();
            let url = git_ops::remote_url(&root, "origin")?
                .or(project.http_url_to_repo.clone())
                .or(project.ssh_url_to_repo.clone())
                .unwrap_or_default();
            let local_id = cache::upsert_local_repo(
                &conn,
                &account_id,
                Some(project.project_id),
                &root_s,
                &url,
            )?;
            d.set_item("found", true)?;
            d.set_item("local_repo_id", local_id)?;
            d.set_item("path", root_s)?;
            d.set_item("exists", true)?;
            d.set_item("source", "discovered")?;
            return Ok(d.into());
        }
    }

    d.set_item("found", false)?;
    d.set_item("exists", false)?;
    Ok(d.into())
}

/// Register an existing local git working tree against a cached project.
#[pyfunction]
fn register_local_repo(py: Python<'_>, project_id: i64, path: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let Some(project) = cache::get_cached_project(&conn, &acc.id, project_id)? else {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-404", "Not found or no access.")
                .with_detail(format!("project_id {project_id} not in cache; refresh projects")),
        )
        .into());
    };

    let given = std::path::Path::new(&path);
    if !git_ops::is_git_repository(given) {
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-032",
                "Not a git repository.",
            )
            .with_detail(path),
        )
        .into());
    }
    let root = git_ops::resolve_repo_root(given)?;
    let root_s = root.display().to_string();
    let url = git_ops::remote_url(&root, "origin")?
        .or(project.http_url_to_repo.clone())
        .or(project.ssh_url_to_repo.clone())
        .unwrap_or_default();
    let local_id = cache::upsert_local_repo(
        &conn,
        &acc.id,
        Some(project.project_id),
        &root_s,
        &url,
    )?;

    let d = PyDict::new(py);
    d.set_item("local_repo_id", local_id)?;
    d.set_item("path", root_s)?;
    d.set_item("clone_url", url)?;
    d.set_item("path_with_namespace", project.path_with_namespace)?;
    Ok(d.into())
}

/// Validate a path as a git repo and return its resolved root (no project link required).
#[pyfunction]
fn open_repo_path(py: Python<'_>, path: String) -> PyResult<PyObject> {
    let given = std::path::Path::new(&path);
    if !git_ops::is_git_repository(given) {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-032", "Not a git repository.").with_detail(path),
        )
        .into());
    }
    let root = git_ops::resolve_repo_root(given)?;
    let root_s = root.display().to_string();
    let url = git_ops::remote_url(&root, "origin")?.unwrap_or_default();

    // If we have an active account, remember the path for later (project_id unknown).
    let paths = paths::AppPaths::detect();
    if let Ok(cfg) = config::load_or_default(&paths) {
        if let Some((acc, _inst)) = cfg.active_connection() {
            if let Ok(conn) = cache::open(&paths).or_else(|_| cache::rebuild(&paths)) {
                let _ = cache::upsert_local_repo(&conn, &acc.id, None, &root_s, &url);
            }
        }
    }

    let d = PyDict::new(py);
    d.set_item("path", root_s)?;
    d.set_item("clone_url", url)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_status(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let entries = git_ops::repo_status(std::path::Path::new(&repo_path))?;
    let list = pyo3::types::PyList::empty(py);
    for e in entries {
        let d = PyDict::new(py);
        d.set_item("path", e.path)?;
        d.set_item("status", e.status)?;
        d.set_item("staged", e.staged)?;
        d.set_item("unstaged", e.unstaged)?;
        list.append(d)?;
    }
    Ok(list.into())
}

#[pyfunction]
fn repo_stage(repo_path: String, paths: Vec<String>) -> PyResult<usize> {
    Ok(git_ops::stage_paths(
        std::path::Path::new(&repo_path),
        &paths,
    )?)
}

#[pyfunction]
fn repo_unstage(repo_path: String, paths: Vec<String>) -> PyResult<usize> {
    Ok(git_ops::unstage_paths(
        std::path::Path::new(&repo_path),
        &paths,
    )?)
}

#[pyfunction]
fn repo_commit(repo_path: String, message: String) -> PyResult<String> {
    Ok(git_ops::commit_index(
        std::path::Path::new(&repo_path),
        &message,
    )?)
}

#[pyfunction]
fn repo_diff(repo_path: String, rel_path: String) -> PyResult<String> {
    Ok(git_ops::file_diff(
        std::path::Path::new(&repo_path),
        &rel_path,
    )?)
}

#[pyfunction]
fn repo_list_files(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let files = git_ops::list_tracked_files(std::path::Path::new(&repo_path))?;
    let list = pyo3::types::PyList::empty(py);
    for f in files {
        list.append(f)?;
    }
    Ok(list.into())
}

#[pyfunction]
fn repo_show_file(repo_path: String, rel_path: String) -> PyResult<String> {
    Ok(git_ops::show_file(
        std::path::Path::new(&repo_path),
        &rel_path,
    )?)
}

#[pyfunction]
fn repo_head_summary(repo_path: String) -> PyResult<String> {
    Ok(git_ops::head_commit_summary(std::path::Path::new(
        &repo_path,
    ))?)
}

#[pyfunction]
#[pyo3(signature = (repo_path, limit=100))]
fn repo_log(py: Python<'_>, repo_path: String, limit: usize) -> PyResult<PyObject> {
    let entries = git_ops::commit_log(std::path::Path::new(&repo_path), limit)?;
    let list = pyo3::types::PyList::empty(py);
    for e in entries {
        let d = PyDict::new(py);
        d.set_item("oid", e.oid)?;
        d.set_item("short_oid", e.short_oid)?;
        d.set_item("summary", e.summary)?;
        d.set_item("body", e.body)?;
        d.set_item("author_name", e.author_name)?;
        d.set_item("author_email", e.author_email)?;
        d.set_item("time", e.time)?;
        list.append(d)?;
    }
    Ok(list.into())
}

#[pyfunction]
fn repo_commit_info(py: Python<'_>, repo_path: String, oid: String) -> PyResult<PyObject> {
    let e = git_ops::commit_info(std::path::Path::new(&repo_path), &oid)?;
    let d = PyDict::new(py);
    d.set_item("oid", e.oid)?;
    d.set_item("short_oid", e.short_oid)?;
    d.set_item("summary", e.summary)?;
    d.set_item("body", e.body)?;
    d.set_item("author_name", e.author_name)?;
    d.set_item("author_email", e.author_email)?;
    d.set_item("time", e.time)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_commit_diff(repo_path: String, oid: String) -> PyResult<String> {
    Ok(git_ops::commit_diff(
        std::path::Path::new(&repo_path),
        &oid,
    )?)
}

#[pyfunction]
fn repo_branch(repo_path: String) -> PyResult<String> {
    Ok(git_ops::current_branch(std::path::Path::new(&repo_path))?)
}

#[pyfunction]
fn repo_list_branches(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let listed = git_ops::list_branches(std::path::Path::new(&repo_path))?;
    let d = PyDict::new(py);
    d.set_item("current", listed.current)?;
    d.set_item("branches", listed.branches)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_list_compare_refs(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let listed = git_ops::list_compare_refs(std::path::Path::new(&repo_path))?;
    let d = PyDict::new(py);
    d.set_item("current", listed.current)?;
    d.set_item("branches", listed.branches)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_compare_branches(
    py: Python<'_>,
    repo_path: String,
    base_ref: String,
    other_ref: String,
) -> PyResult<PyObject> {
    let cmp = git_ops::compare_branches(std::path::Path::new(&repo_path), &base_ref, &other_ref)?;
    let d = PyDict::new(py);
    d.set_item("base_ref", cmp.base_ref)?;
    d.set_item("other_ref", cmp.other_ref)?;
    d.set_item("ahead", cmp.ahead)?;
    d.set_item("behind", cmp.behind)?;
    d.set_item("diff_text", cmp.diff_text)?;
    let commits = pyo3::types::PyList::empty(py);
    for c in cmp.commits {
        let row = PyDict::new(py);
        row.set_item("oid", c.oid)?;
        row.set_item("summary", c.summary)?;
        row.set_item("author", c.author)?;
        row.set_item("time", c.time)?;
        commits.append(row)?;
    }
    d.set_item("commits", commits)?;
    Ok(d.into())
}

#[pyfunction]
fn remote_branch_exists(py: Python<'_>, project_id: i64, branch: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let exists = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        api_client::remote_branch_exists(&base_url, &pat, &ssl_mode, project_id, &branch)
    })?;
    let d = PyDict::new(py);
    d.set_item("exists", exists)?;
    d.set_item("branch", branch)?;
    Ok(d.into())
}

#[pyfunction]
#[pyo3(signature = (repo_path, name, checkout=true))]
fn repo_create_branch(repo_path: String, name: String, checkout: bool) -> PyResult<()> {
    git_ops::create_branch(std::path::Path::new(&repo_path), &name, checkout)?;
    Ok(())
}

#[pyfunction]
fn repo_checkout_branch(repo_path: String, name: String) -> PyResult<()> {
    git_ops::checkout_branch(std::path::Path::new(&repo_path), &name)?;
    Ok(())
}

/// Resolve a local repo path to a cached GitLab project (for MR creation).
#[pyfunction]
fn resolve_repo_project(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let account_id = acc.id.clone();
    let conn = cache::open(&paths)?;

    let mut project_id: Option<i64> = None;
    let mut clone_url: Option<String> = None;

    if let Some((_aid, pid, curl)) = cache::find_local_repo_by_path(&conn, &repo_path)? {
        project_id = pid;
        clone_url = curl;
    }
    if clone_url.is_none() {
        clone_url = git_ops::remote_url(std::path::Path::new(&repo_path), "origin")?;
    }

    let project = if let Some(pid) = project_id {
        cache::get_cached_project(&conn, &account_id, pid)?
    } else if let Some(ref url) = clone_url {
        cache::find_project_by_clone_url(&conn, &account_id, url)?
    } else {
        None
    };

    let Some(project) = project else {
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-API-404",
                "Not found or no access.",
            )
            .with_detail(
                "Could not match this repository to a cached GitLab project. Refresh projects and open from the project list, or register the local path.",
            ),
        )
        .into());
    };

    let current = git_ops::current_branch(std::path::Path::new(&repo_path)).unwrap_or_default();
    let d = PyDict::new(py);
    d.set_item("project_id", project.project_id)?;
    d.set_item("name", project.name)?;
    d.set_item("path_with_namespace", project.path_with_namespace)?;
    d.set_item("default_branch", project.default_branch)?;
    d.set_item("web_url", project.web_url)?;
    d.set_item("current_branch", current)?;
    Ok(d.into())
}

#[pyfunction]
#[pyo3(signature = (project_id, source_branch, target_branch, title, description=None))]
fn create_merge_request(
    py: Python<'_>,
    project_id: i64,
    source_branch: String,
    target_branch: String,
    title: String,
    description: Option<String>,
) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&acc.keyring_account).map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
    })?;
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let mr = py.allow_threads(|| {
        api_client::create_merge_request(
            &base_url,
            &pat,
            &ssl_mode,
            project_id,
            &source_branch,
            &target_branch,
            &title,
            description.as_deref(),
        )
    })?;
    let d = PyDict::new(py);
    d.set_item("iid", mr.iid)?;
    d.set_item("title", mr.title)?;
    d.set_item("state", mr.state)?;
    d.set_item("web_url", mr.web_url)?;
    Ok(d.into())
}

/// Fetch opened MRs for a project into SQLite; returns list.
#[pyfunction]
fn refresh_merge_requests(py: Python<'_>, project_id: i64) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let account_id = acc.id.clone();
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let rows = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        let mrs = api_client::list_project_merge_requests(&base_url, &pat, &ssl_mode, project_id)?;
        let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
        if cache::replace_merge_requests(&conn, &account_id, project_id, &mrs).is_err() {
            let conn = cache::rebuild(&paths)?;
            cache::replace_merge_requests(&conn, &account_id, project_id, &mrs)?;
        }
        Ok::<_, LabDeskError>(mrs)
    })?;
    let list = pyo3::types::PyList::empty(py);
    for mr in rows {
        let d = PyDict::new(py);
        d.set_item("iid", mr.iid)?;
        d.set_item("title", mr.title)?;
        d.set_item("state", mr.state)?;
        d.set_item("web_url", mr.web_url)?;
        d.set_item("source_branch", mr.source_branch)?;
        d.set_item("target_branch", mr.target_branch)?;
        d.set_item("updated_at", mr.updated_at)?;
        list.append(d)?;
    }
    let out = PyDict::new(py);
    out.set_item("merge_requests", list)?;
    out.set_item("cached", false)?;
    Ok(out.into())
}

/// Cached opened MRs for a project (no network).
#[pyfunction]
fn cached_merge_requests(py: Python<'_>, project_id: i64) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Ok(py.None());
    };
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let rows = cache::list_cached_merge_requests(&conn, &acc.id, project_id)?;
    if rows.is_empty() {
        return Ok(py.None());
    }
    let list = pyo3::types::PyList::empty(py);
    let mut fetched_at = None;
    for mr in rows {
        if fetched_at.is_none() {
            fetched_at = Some(mr.fetched_at.clone());
        }
        let d = PyDict::new(py);
        d.set_item("iid", mr.mr_iid)?;
        d.set_item("title", mr.title)?;
        d.set_item("state", mr.state)?;
        d.set_item("web_url", mr.web_url)?;
        d.set_item("source_branch", mr.source_branch)?;
        d.set_item("target_branch", mr.target_branch)?;
        d.set_item("updated_at", mr.updated_at)?;
        list.append(d)?;
    }
    let out = PyDict::new(py);
    out.set_item("merge_requests", list)?;
    out.set_item("cached", true)?;
    out.set_item("fetched_at", fetched_at)?;
    Ok(out.into())
}

#[pyfunction]
fn repo_pull(py: Python<'_>, repo_path: String) -> PyResult<String> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&acc.keyring_account).ok();
    let ssl_insecure = inst.ssl_mode == "allow_self_signed";
    py.allow_threads(|| {
        let auth = git_ops::AuthOptions {
            pat_fallback: pat.as_deref(),
            ssl_insecure,
            prefer_ssh: false,
        };
        git_ops::pull(std::path::Path::new(&repo_path), "origin", &auth)
    })
    .map_err(Into::into)
}

#[pyfunction]
fn repo_fetch(py: Python<'_>, repo_path: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&acc.keyring_account).ok();
    let ssl_insecure = inst.ssl_mode == "allow_self_signed";
    py.allow_threads(|| {
        let auth = git_ops::AuthOptions {
            pat_fallback: pat.as_deref(),
            ssl_insecure,
            prefer_ssh: false,
        };
        git_ops::fetch(std::path::Path::new(&repo_path), "origin", &auth)
    })?;
    Ok(())
}

#[pyfunction]
fn repo_ahead_behind(py: Python<'_>, repo_path: String) -> PyResult<PyObject> {
    let (ahead, behind, upstream) =
        git_ops::ahead_behind(std::path::Path::new(&repo_path), "origin")?;
    let d = PyDict::new(py);
    d.set_item("ahead", ahead)?;
    d.set_item("behind", behind)?;
    d.set_item("upstream", upstream)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_merge_branch(repo_path: String, their_branch: String) -> PyResult<String> {
    Ok(git_ops::merge_local_branch(
        std::path::Path::new(&repo_path),
        &their_branch,
    )?)
}

#[pyfunction]
#[pyo3(signature = (repo_path, force=false))]
fn repo_push(py: Python<'_>, repo_path: String, force: bool) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&acc.keyring_account).ok();
    let ssl_insecure = inst.ssl_mode == "allow_self_signed";
    py.allow_threads(|| {
        let auth = git_ops::AuthOptions {
            pat_fallback: pat.as_deref(),
            ssl_insecure,
            prefer_ssh: false,
        };
        git_ops::push(std::path::Path::new(&repo_path), "origin", force, &auth)
    })?;

    // Update last_push_at when we can match the path.
    if let Ok(conn) = cache::open(&paths) {
        let stamp = config::iso8601_now_public();
        let _ = conn.execute(
            "UPDATE local_repos SET last_push_at = ?1 WHERE path = ?2",
            rusqlite::params![stamp, repo_path],
        );
    }
    Ok(())
}

/// Latest pipeline for the given project ref (current branch).
#[pyfunction]
fn latest_pipeline(py: Python<'_>, project_id: i64, ref_name: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let pipe = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        api_client::latest_pipeline(&base_url, &pat, &ssl_mode, project_id, &ref_name)
    })?;
    match pipe {
        None => Ok(py.None()),
        Some(p) => {
            let d = PyDict::new(py);
            d.set_item("id", p.id)?;
            d.set_item("status", p.status)?;
            d.set_item("ref", p.ref_)?;
            d.set_item("web_url", p.web_url)?;
            d.set_item("updated_at", p.updated_at)?;
            d.set_item("created_at", p.created_at)?;
            Ok(d.into())
        }
    }
}

/// Jobs for a pipeline (includes `when` for manual detection).
#[pyfunction]
fn list_pipeline_jobs(py: Python<'_>, project_id: i64, pipeline_id: u64) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let jobs = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        api_client::list_pipeline_jobs(&base_url, &pat, &ssl_mode, project_id, pipeline_id)
    })?;
    let list = pyo3::types::PyList::empty(py);
    for j in jobs {
        let d = PyDict::new(py);
        d.set_item("id", j.id)?;
        d.set_item("name", j.name)?;
        d.set_item("status", j.status)?;
        d.set_item("stage", j.stage)?;
        d.set_item("when", j.when)?;
        d.set_item("web_url", j.web_url)?;
        list.append(d)?;
    }
    Ok(list.into())
}

/// Persist latest pipeline + jobs for offline Pipelines tab (one row per ref).
#[pyfunction]
fn cache_pipeline(
    py: Python<'_>,
    project_id: i64,
    ref_name: String,
    pipeline: Bound<'_, PyAny>,
    jobs: Bound<'_, PyAny>,
) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    if pipeline.is_none() {
        return Ok(());
    }
    let pipe = pipeline.downcast::<PyDict>()?;
    let pipeline_id: i64 = pipe
        .get_item("id")?
        .ok_or_else(|| {
            LabDeskError::App(ErrorInfo::new(
                "LD-SYS-001",
                "Pipeline cache requires an id.",
            ))
        })?
        .extract()?;
    let status: Option<String> = pipe
        .get_item("status")?
        .map(|v| v.extract())
        .transpose()?;
    let web_url: Option<String> = pipe
        .get_item("web_url")?
        .map(|v| v.extract())
        .transpose()?;
    let updated_at: Option<String> = pipe
        .get_item("updated_at")?
        .or(pipe.get_item("created_at")?)
        .map(|v| v.extract())
        .transpose()?;
    let jobs_val: serde_json::Value = pythonize_jobs(py, &jobs)?;
    let jobs_json = serde_json::to_string(&jobs_val).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-SYS-001", "Failed to serialize pipeline jobs.")
                .with_detail(e.to_string()),
        )
    })?;
    let account_id = acc.id.clone();
    let ref_owned = ref_name.clone();
    py.allow_threads(|| {
        let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
        cache::upsert_pipeline(
            &conn,
            &account_id,
            project_id,
            &ref_owned,
            pipeline_id,
            status.as_deref(),
            web_url.as_deref(),
            updated_at.as_deref(),
            Some(&jobs_json),
        )
    })?;
    Ok(())
}

/// Cached latest pipeline + jobs for a ref, or None.
#[pyfunction]
fn cached_pipeline(py: Python<'_>, project_id: i64, ref_name: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, _inst)) = cfg.active_connection() else {
        return Ok(py.None());
    };
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let Some(row) = cache::get_pipeline(&conn, &acc.id, project_id, &ref_name)? else {
        return Ok(py.None());
    };
    let pipe = PyDict::new(py);
    pipe.set_item("id", row.pipeline_id)?;
    pipe.set_item("status", row.status)?;
    pipe.set_item("ref", &row.ref_name)?;
    pipe.set_item("web_url", row.web_url)?;
    pipe.set_item("updated_at", row.updated_at)?;
    let jobs_list = pyo3::types::PyList::empty(py);
    if let Some(raw) = row.jobs_json.as_deref() {
        if let Ok(serde_json::Value::Array(arr)) = serde_json::from_str::<serde_json::Value>(raw) {
            for item in arr {
                if let Some(obj) = item.as_object() {
                    let d = PyDict::new(py);
                    for (k, v) in obj {
                        set_json_item(py, &d, k, v)?;
                    }
                    jobs_list.append(d)?;
                }
            }
        }
    }
    let out = PyDict::new(py);
    out.set_item("pipeline", pipe)?;
    out.set_item("jobs", jobs_list)?;
    out.set_item("fetched_at", row.fetched_at)?;
    Ok(out.into())
}

fn pythonize_jobs(py: Python<'_>, jobs: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    let list = jobs.downcast::<pyo3::types::PyList>()?;
    let mut arr = Vec::with_capacity(list.len());
    for item in list.iter() {
        let d = item.downcast::<PyDict>()?;
        let mut map = serde_json::Map::new();
        for (k, v) in d.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_any_to_json(py, &v)?);
        }
        arr.push(serde_json::Value::Object(map));
    }
    Ok(serde_json::Value::Array(arr))
}

fn py_any_to_json(py: Python<'_>, v: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    if v.is_none() {
        return Ok(serde_json::Value::Null);
    }
    if let Ok(b) = v.extract::<bool>() {
        return Ok(serde_json::Value::Bool(b));
    }
    if let Ok(i) = v.extract::<i64>() {
        return Ok(serde_json::json!(i));
    }
    if let Ok(f) = v.extract::<f64>() {
        return Ok(serde_json::json!(f));
    }
    if let Ok(s) = v.extract::<String>() {
        return Ok(serde_json::Value::String(s));
    }
    let _ = py;
    Ok(serde_json::Value::String(v.str()?.to_string()))
}

fn set_json_item(
    py: Python<'_>,
    d: &Bound<'_, PyDict>,
    key: &str,
    v: &serde_json::Value,
) -> PyResult<()> {
    match v {
        serde_json::Value::Null => d.set_item(key, py.None())?,
        serde_json::Value::Bool(b) => d.set_item(key, *b)?,
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                d.set_item(key, i)?;
            } else if let Some(u) = n.as_u64() {
                d.set_item(key, u)?;
            } else if let Some(f) = n.as_f64() {
                d.set_item(key, f)?;
            }
        }
        serde_json::Value::String(s) => d.set_item(key, s)?,
        _ => d.set_item(key, v.to_string())?,
    }
    Ok(())
}

/// Play a manual CI job.
#[pyfunction]
fn play_job(py: Python<'_>, project_id: i64, job_id: u64) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some((acc, inst)) = cfg.active_connection() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let base_url = inst.base_url.clone();
    let ssl_mode = inst.ssl_mode.clone();
    let keyring = acc.keyring_account.clone();
    let j = py.allow_threads(|| {
        let pat = secrets::load_pat(&keyring)?;
        api_client::play_job(&base_url, &pat, &ssl_mode, project_id, job_id)
    })?;
    let d = PyDict::new(py);
    d.set_item("id", j.id)?;
    d.set_item("name", j.name)?;
    d.set_item("status", j.status)?;
    d.set_item("stage", j.stage)?;
    d.set_item("when", j.when)?;
    d.set_item("web_url", j.web_url)?;
    Ok(d.into())
}

/// Validate instance base URL (SaaS reject + LAN HTTP allowlist).
#[pyfunction]
fn validate_base_url(base_url: String) -> PyResult<()> {
    config::validate_base_url(&base_url)?;
    Ok(())
}

/// Restore config.known-good.toml over config.toml (startup recovery helper).
#[pyfunction]
fn revert_config_to_known_good() -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    config::revert_to_known_good(&paths)?;
    Ok(())
}

/// Parse an error string produced by this module into a dict if possible.
#[pyfunction]
fn parse_error_message(py: Python<'_>, message: &str) -> PyResult<PyObject> {
    let d = PyDict::new(py);
    if let Some(rest) = message.strip_prefix('[') {
        if let Some((code, msg)) = rest.split_once(']') {
            d.set_item("code", code.trim())?;
            d.set_item("message", msg.trim().trim_start_matches(':').trim())?;
            d.set_item("detail", py.None())?;
            d.set_item("retryable", false)?;
            return Ok(d.into());
        }
    }
    d.set_item("code", "LD-SYS-001")?;
    d.set_item("message", message)?;
    d.set_item("detail", py.None())?;
    d.set_item("retryable", false)?;
    Ok(d.into())
}

/// Return stored + expanded default clone directory.
#[pyfunction]
fn get_default_clone_dir(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let (stored, expanded) = config::get_default_clone_dir(&paths)?;
    let d = PyDict::new(py);
    d.set_item("stored", stored)?;
    d.set_item("expanded", expanded)?;
    Ok(d.into())
}

/// Set and persist `general.default_clone_dir` (expands `~`).
#[pyfunction]
fn set_default_clone_dir(py: Python<'_>, path: String) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let expanded = config::set_default_clone_dir(&paths, &path)?;
    let d = PyDict::new(py);
    d.set_item("stored", &expanded)?;
    d.set_item("expanded", &expanded)?;
    Ok(d.into())
}

/// Persist `general.theme` (UI-exposed; does not rewrite config-only keys).
#[pyfunction]
fn set_theme(theme: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    config::set_theme(&paths, &theme)?;
    Ok(())
}

/// Persist `general.active_ui_view` (pluggable main view id).
#[pyfunction]
fn set_active_ui_view(view_id: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    config::set_active_ui_view(&paths, &view_id)?;
    Ok(())
}

/// Persist `general.check_for_updates`.
#[pyfunction]
fn set_check_for_updates(enabled: bool) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let mut cfg = config::load_or_default(&paths)?;
    cfg.general.check_for_updates = enabled;
    config::save(&paths, &mut cfg)?;
    let _ = config::save_known_good(&paths);
    Ok(())
}

/// Persist `general.ui_shell` (`classic` | `sidebar`).
#[pyfunction]
fn set_ui_shell(shell: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    config::set_ui_shell(&paths, &shell)?;
    Ok(())
}

#[pymodule]
fn labdesk_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_paths, m)?)?;
    m.add_function(wrap_pyfunction!(load_config, m)?)?;
    m.add_function(wrap_pyfunction!(connect_instance, m)?)?;
    m.add_function(wrap_pyfunction!(connect_account, m)?)?;
    m.add_function(wrap_pyfunction!(add_account, m)?)?;
    m.add_function(wrap_pyfunction!(list_instances, m)?)?;
    m.add_function(wrap_pyfunction!(list_accounts, m)?)?;
    m.add_function(wrap_pyfunction!(set_active_account, m)?)?;
    m.add_function(wrap_pyfunction!(fetch_current_user, m)?)?;
    m.add_function(wrap_pyfunction!(refresh_projects, m)?)?;
    m.add_function(wrap_pyfunction!(list_projects, m)?)?;
    m.add_function(wrap_pyfunction!(clone_project, m)?)?;
    m.add_function(wrap_pyfunction!(find_local_repo, m)?)?;
    m.add_function(wrap_pyfunction!(register_local_repo, m)?)?;
    m.add_function(wrap_pyfunction!(open_repo_path, m)?)?;
    m.add_function(wrap_pyfunction!(repo_status, m)?)?;
    m.add_function(wrap_pyfunction!(repo_stage, m)?)?;
    m.add_function(wrap_pyfunction!(repo_unstage, m)?)?;
    m.add_function(wrap_pyfunction!(repo_commit, m)?)?;
    m.add_function(wrap_pyfunction!(repo_diff, m)?)?;
    m.add_function(wrap_pyfunction!(repo_list_files, m)?)?;
    m.add_function(wrap_pyfunction!(repo_show_file, m)?)?;
    m.add_function(wrap_pyfunction!(repo_head_summary, m)?)?;
    m.add_function(wrap_pyfunction!(repo_log, m)?)?;
    m.add_function(wrap_pyfunction!(repo_commit_info, m)?)?;
    m.add_function(wrap_pyfunction!(repo_commit_diff, m)?)?;
    m.add_function(wrap_pyfunction!(repo_branch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_list_branches, m)?)?;
    m.add_function(wrap_pyfunction!(repo_list_compare_refs, m)?)?;
    m.add_function(wrap_pyfunction!(repo_compare_branches, m)?)?;
    m.add_function(wrap_pyfunction!(remote_branch_exists, m)?)?;
    m.add_function(wrap_pyfunction!(repo_create_branch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_checkout_branch, m)?)?;
    m.add_function(wrap_pyfunction!(resolve_repo_project, m)?)?;
    m.add_function(wrap_pyfunction!(create_merge_request, m)?)?;
    m.add_function(wrap_pyfunction!(refresh_merge_requests, m)?)?;
    m.add_function(wrap_pyfunction!(cached_merge_requests, m)?)?;
    m.add_function(wrap_pyfunction!(repo_pull, m)?)?;
    m.add_function(wrap_pyfunction!(repo_fetch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_ahead_behind, m)?)?;
    m.add_function(wrap_pyfunction!(repo_merge_branch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_push, m)?)?;
    m.add_function(wrap_pyfunction!(latest_pipeline, m)?)?;
    m.add_function(wrap_pyfunction!(list_pipeline_jobs, m)?)?;
    m.add_function(wrap_pyfunction!(cache_pipeline, m)?)?;
    m.add_function(wrap_pyfunction!(cached_pipeline, m)?)?;
    m.add_function(wrap_pyfunction!(play_job, m)?)?;
    m.add_function(wrap_pyfunction!(get_default_clone_dir, m)?)?;
    m.add_function(wrap_pyfunction!(set_default_clone_dir, m)?)?;
    m.add_function(wrap_pyfunction!(set_theme, m)?)?;
    m.add_function(wrap_pyfunction!(set_check_for_updates, m)?)?;
    m.add_function(wrap_pyfunction!(set_active_ui_view, m)?)?;
    m.add_function(wrap_pyfunction!(set_ui_shell, m)?)?;
    m.add_function(wrap_pyfunction!(validate_base_url, m)?)?;
    m.add_function(wrap_pyfunction!(revert_config_to_known_good, m)?)?;
    m.add_function(wrap_pyfunction!(parse_error_message, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
