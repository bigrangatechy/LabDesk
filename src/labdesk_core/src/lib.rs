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
use pyo3::types::PyDict;

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
        d.set_item("api_auth", &inst.api_auth)?;
        d.set_item("keyring_account", &inst.keyring_account)?;
        d.set_item("git_https_auth", &inst.git_https_auth)?;
        d.set_item("ssl_mode", &inst.ssl_mode)?;
        d.set_item("created_at", &inst.created_at)?;
        d.set_item("last_connected", inst.last_connected.as_deref())?;
        d.set_item("gitlab_version", inst.gitlab_version.as_deref())?;
        d.set_item("gitlab_revision", inst.gitlab_revision.as_deref())?;
        instances.append(d)?;
    }
    root.set_item("instances", instances)?;
    root.set_item(
        "config_path",
        config::config_path_display(&paths::AppPaths::detect()),
    )?;
    Ok(root.into())
}

/// Connect instance: validate URL, GET /user, store PAT, save config + known-good.
#[pyfunction]
#[pyo3(signature = (name, base_url, pat, ssl_mode="strict"))]
fn connect_instance(
    py: Python<'_>,
    name: String,
    base_url: String,
    pat: String,
    ssl_mode: &str,
) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let mut cfg = config::load_or_default(&paths)?;

    let inst = config::upsert_instance(&mut cfg, name, base_url, ssl_mode.to_string())?;

    let user = match api_client::get_user(&inst.base_url, &pat, ssl_mode) {
        Ok(u) => u,
        Err(e) => {
            if e.info().code == "LD-AUTH-001" {
                let _ = secrets::clear_pat(&inst.keyring_account);
            }
            return Err(e.into());
        }
    };

    secrets::store_pat(&inst.keyring_account, &pat)?;

    if let Some(active) = cfg.active_instance_mut() {
        config::touch_last_connected(active);
        if let Ok(Some(ver)) = api_client::get_version(&inst.base_url, &pat, ssl_mode) {
            active.gitlab_version = ver.version;
            active.gitlab_revision = ver.revision;
        }
    }

    config::save(&paths, &mut cfg)?;
    config::save_known_good(&paths)?;

    // Best-effort project refresh after connect (failures don't undo connect).
    let project_count = match refresh_projects_inner(&paths, &inst.id, &inst.base_url, &pat, ssl_mode)
    {
        Ok(n) => n,
        Err(_) => 0,
    };

    let out = PyDict::new(py);
    out.set_item("instance_id", &inst.id)?;
    out.set_item("base_url", &inst.base_url)?;
    out.set_item("keyring_account", &inst.keyring_account)?;
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

fn refresh_projects_inner(
    paths: &paths::AppPaths,
    instance_id: &str,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<usize, LabDeskError> {
    let projects = api_client::list_membership_projects(base_url, pat, ssl_mode)?;
    let conn = cache::open(paths).or_else(|_| cache::rebuild(paths))?;
    if cache::replace_projects(&conn, instance_id, &projects).is_err() {
        let conn = cache::rebuild(paths)?;
        cache::replace_projects(&conn, instance_id, &projects)?;
    }
    Ok(projects.len())
}

/// Fetch current user for the active instance using the keyring PAT.
#[pyfunction]
fn fetch_current_user(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account)?;
    let user = api_client::get_user(&inst.base_url, &pat, &inst.ssl_mode)?;
    let u = PyDict::new(py);
    u.set_item("id", user.id)?;
    u.set_item("username", user.username)?;
    u.set_item("name", user.name)?;
    u.set_item("web_url", user.web_url)?;
    u.set_item("instance_name", &inst.name)?;
    u.set_item("base_url", &inst.base_url)?;
    Ok(u.into())
}

/// Refresh projects from API into SQLite; returns count.
#[pyfunction]
fn refresh_projects(py: Python<'_>) -> PyResult<PyObject> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account)?;
    let count =
        refresh_projects_inner(&paths, &inst.id, &inst.base_url, &pat, &inst.ssl_mode)?;
    let d = PyDict::new(py);
    d.set_item("count", count)?;
    d.set_item("source", "api")?;
    Ok(d.into())
}

/// List cached projects for the active instance (no network).
#[pyfunction]
#[pyo3(signature = (allow_stale=true))]
fn list_projects(py: Python<'_>, allow_stale: bool) -> PyResult<PyObject> {
    let _ = allow_stale;
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };

    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let rows = cache::list_projects(&conn, &inst.id)?;
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
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };

    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let Some(project) = cache::get_cached_project(&conn, &inst.id, project_id)? else {
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
            &inst.id,
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
        Some(secrets::load_pat(&inst.keyring_account)?)
    };

    let ssl_insecure = inst.ssl_mode == "allow_self_signed";
    git_ops::clone_repository(&git_ops::CloneRequest {
        url: &url,
        destination: &dest,
        transport: tr,
        pat_fallback: pat.as_deref(),
        ssl_insecure,
    })?;

    let local_id = cache::upsert_local_repo(
        &conn,
        &inst.id,
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
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let d = PyDict::new(py);

    if let Some((id, path)) = cache::find_local_repo_by_project(&conn, &inst.id, project_id)? {
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
    if let Some(project) = cache::get_cached_project(&conn, &inst.id, project_id)? {
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
                &inst.id,
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
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let conn = cache::open(&paths).or_else(|_| cache::rebuild(&paths))?;
    let Some(project) = cache::get_cached_project(&conn, &inst.id, project_id)? else {
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
        &inst.id,
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

    // If we have an active instance, remember the path for later (project_id unknown).
    let paths = paths::AppPaths::detect();
    if let Ok(cfg) = config::load_or_default(&paths) {
        if let Some(inst) = cfg.active_instance() {
            if let Ok(conn) = cache::open(&paths).or_else(|_| cache::rebuild(&paths)) {
                let _ = cache::upsert_local_repo(&conn, &inst.id, None, &root_s, &url);
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
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let conn = cache::open(&paths)?;

    let mut project_id: Option<i64> = None;
    let mut clone_url: Option<String> = None;

    if let Some((_iid, pid, curl)) = cache::find_local_repo_by_path(&conn, &repo_path)? {
        project_id = pid;
        clone_url = curl;
    }
    if clone_url.is_none() {
        clone_url = git_ops::remote_url(std::path::Path::new(&repo_path), "origin")?;
    }

    let project = if let Some(pid) = project_id {
        cache::get_cached_project(&conn, &inst.id, pid)?
    } else if let Some(ref url) = clone_url {
        cache::find_project_by_clone_url(&conn, &inst.id, url)?
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
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account).map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
    })?;
    let mr = api_client::create_merge_request(
        &inst.base_url,
        &pat,
        &inst.ssl_mode,
        project_id,
        &source_branch,
        &target_branch,
        &title,
        description.as_deref(),
    )?;
    let d = PyDict::new(py);
    d.set_item("iid", mr.iid)?;
    d.set_item("title", mr.title)?;
    d.set_item("state", mr.state)?;
    d.set_item("web_url", mr.web_url)?;
    Ok(d.into())
}

#[pyfunction]
fn repo_pull(repo_path: String) -> PyResult<String> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account).ok();
    let auth = git_ops::AuthOptions {
        pat_fallback: pat.as_deref(),
        ssl_insecure: inst.ssl_mode == "allow_self_signed",
        prefer_ssh: false,
    };
    Ok(git_ops::pull(
        std::path::Path::new(&repo_path),
        "origin",
        &auth,
    )?)
}

#[pyfunction]
fn repo_fetch(repo_path: String) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account).ok();
    let auth = git_ops::AuthOptions {
        pat_fallback: pat.as_deref(),
        ssl_insecure: inst.ssl_mode == "allow_self_signed",
        prefer_ssh: false,
    };
    git_ops::fetch(std::path::Path::new(&repo_path), "origin", &auth)?;
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
fn repo_push(repo_path: String, force: bool) -> PyResult<()> {
    let paths = paths::AppPaths::detect();
    let cfg = config::load_or_default(&paths)?;
    let Some(inst) = cfg.active_instance() else {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))
        .into());
    };
    let pat = secrets::load_pat(&inst.keyring_account).ok();
    let auth = git_ops::AuthOptions {
        pat_fallback: pat.as_deref(),
        ssl_insecure: inst.ssl_mode == "allow_self_signed",
        prefer_ssh: false,
    };
    git_ops::push(std::path::Path::new(&repo_path), "origin", force, &auth)?;

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
    m.add_function(wrap_pyfunction!(repo_create_branch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_checkout_branch, m)?)?;
    m.add_function(wrap_pyfunction!(resolve_repo_project, m)?)?;
    m.add_function(wrap_pyfunction!(create_merge_request, m)?)?;
    m.add_function(wrap_pyfunction!(repo_pull, m)?)?;
    m.add_function(wrap_pyfunction!(repo_fetch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_ahead_behind, m)?)?;
    m.add_function(wrap_pyfunction!(repo_merge_branch, m)?)?;
    m.add_function(wrap_pyfunction!(repo_push, m)?)?;
    m.add_function(wrap_pyfunction!(get_default_clone_dir, m)?)?;
    m.add_function(wrap_pyfunction!(set_default_clone_dir, m)?)?;
    m.add_function(wrap_pyfunction!(set_theme, m)?)?;
    m.add_function(wrap_pyfunction!(set_check_for_updates, m)?)?;
    m.add_function(wrap_pyfunction!(set_active_ui_view, m)?)?;
    m.add_function(wrap_pyfunction!(set_ui_shell, m)?)?;
    m.add_function(wrap_pyfunction!(revert_config_to_known_good, m)?)?;
    m.add_function(wrap_pyfunction!(parse_error_message, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
