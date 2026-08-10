//! SQLite cache (`Docs/data-model.md`).

use rusqlite::{params, Connection, OptionalExtension};

use crate::api_client::GitLabProject;
use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::paths::AppPaths;

const SCHEMA_VERSION: &str = "2";

pub fn open(paths: &AppPaths) -> Result<Connection> {
    paths.ensure_dirs().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CACHE-001", "Cache corrupted. Rebuilding.").with_detail(e.to_string()),
        )
    })?;

    let conn = Connection::open(paths.cache_db()).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CACHE-001", "Cache corrupted. Rebuilding.").with_detail(e.to_string()),
        )
    })?;

    init_schema(&conn)?;
    Ok(conn)
}

fn init_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            instance_id TEXT NOT NULL,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_with_namespace TEXT NOT NULL,
            path_with_namespace TEXT NOT NULL,
            http_url_to_repo TEXT,
            ssh_url_to_repo TEXT,
            web_url TEXT,
            default_branch TEXT,
            visibility TEXT,
            last_activity_at TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (instance_id, project_id)
        );
        CREATE TABLE IF NOT EXISTS local_repos (
            id TEXT PRIMARY KEY,
            instance_id TEXT NOT NULL,
            project_id INTEGER,
            path TEXT NOT NULL UNIQUE,
            preferred_remote TEXT,
            clone_url TEXT,
            added_at TEXT NOT NULL,
            last_opened_at TEXT,
            last_push_at TEXT
        );
        "#,
    )
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CACHE-002", "Cache upgrade failed. Rebuilding.")
                .with_detail(e.to_string()),
        )
    })?;

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?1)",
        params![SCHEMA_VERSION],
    )
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-CACHE-002", "Cache upgrade failed. Rebuilding.")
                .with_detail(e.to_string()),
        )
    })?;
    Ok(())
}

pub fn rebuild(paths: &AppPaths) -> Result<Connection> {
    let db = paths.cache_db();
    if db.exists() {
        std::fs::remove_file(&db).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-CACHE-001", "Cache corrupted. Rebuilding.")
                    .with_detail(e.to_string()),
            )
        })?;
    }
    open(paths)
}

fn fetched_stamp() -> String {
    crate::config::iso8601_now_public()
}

pub fn replace_projects(
    conn: &Connection,
    instance_id: &str,
    projects: &[GitLabProject],
) -> Result<()> {
    let tx = conn.unchecked_transaction().map_err(cache_err)?;
    tx.execute(
        "DELETE FROM projects WHERE instance_id = ?1",
        params![instance_id],
    )
    .map_err(cache_err)?;

    let stamp = fetched_stamp();
    {
        let mut stmt = tx
            .prepare(
                r#"
                INSERT INTO projects (
                    instance_id, project_id, name, name_with_namespace, path_with_namespace,
                    http_url_to_repo, ssh_url_to_repo, web_url, default_branch, visibility,
                    last_activity_at, fetched_at
                ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12)
                "#,
            )
            .map_err(cache_err)?;

        for p in projects {
            stmt.execute(params![
                instance_id,
                p.id as i64,
                p.name,
                p.name_with_namespace,
                p.path_with_namespace,
                p.http_url_to_repo,
                p.ssh_url_to_repo,
                p.web_url,
                p.default_branch,
                p.visibility,
                p.last_activity_at,
                stamp,
            ])
            .map_err(cache_err)?;
        }
    }
    tx.commit().map_err(cache_err)?;
    Ok(())
}

#[derive(Debug, Clone)]
pub struct CachedProject {
    pub project_id: i64,
    pub name: String,
    pub name_with_namespace: String,
    pub path_with_namespace: String,
    pub http_url_to_repo: Option<String>,
    pub ssh_url_to_repo: Option<String>,
    pub web_url: Option<String>,
    pub default_branch: Option<String>,
    pub visibility: Option<String>,
    pub last_activity_at: Option<String>,
    pub fetched_at: String,
}

pub fn list_projects(conn: &Connection, instance_id: &str) -> Result<Vec<CachedProject>> {
    let mut stmt = conn
        .prepare(
            r#"
            SELECT project_id, name, name_with_namespace, path_with_namespace,
                   http_url_to_repo, ssh_url_to_repo, web_url, default_branch,
                   visibility, last_activity_at, fetched_at
            FROM projects
            WHERE instance_id = ?1
            ORDER BY last_activity_at DESC NULLS LAST, name_with_namespace ASC
            "#,
        )
        .map_err(cache_err)?;

    let rows = stmt
        .query_map(params![instance_id], |row| {
            Ok(CachedProject {
                project_id: row.get(0)?,
                name: row.get(1)?,
                name_with_namespace: row.get(2)?,
                path_with_namespace: row.get(3)?,
                http_url_to_repo: row.get(4)?,
                ssh_url_to_repo: row.get(5)?,
                web_url: row.get(6)?,
                default_branch: row.get(7)?,
                visibility: row.get(8)?,
                last_activity_at: row.get(9)?,
                fetched_at: row.get(10)?,
            })
        })
        .map_err(cache_err)?;

    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(cache_err)?);
    }
    Ok(out)
}

pub fn get_cached_project(
    conn: &Connection,
    instance_id: &str,
    project_id: i64,
) -> Result<Option<CachedProject>> {
    let mut stmt = conn
        .prepare(
            r#"
            SELECT project_id, name, name_with_namespace, path_with_namespace,
                   http_url_to_repo, ssh_url_to_repo, web_url, default_branch,
                   visibility, last_activity_at, fetched_at
            FROM projects
            WHERE instance_id = ?1 AND project_id = ?2
            "#,
        )
        .map_err(cache_err)?;

    let mut rows = stmt
        .query_map(params![instance_id, project_id], |row| {
            Ok(CachedProject {
                project_id: row.get(0)?,
                name: row.get(1)?,
                name_with_namespace: row.get(2)?,
                path_with_namespace: row.get(3)?,
                http_url_to_repo: row.get(4)?,
                ssh_url_to_repo: row.get(5)?,
                web_url: row.get(6)?,
                default_branch: row.get(7)?,
                visibility: row.get(8)?,
                last_activity_at: row.get(9)?,
                fetched_at: row.get(10)?,
            })
        })
        .map_err(cache_err)?;

    match rows.next() {
        Some(Ok(p)) => Ok(Some(p)),
        Some(Err(e)) => Err(cache_err(e)),
        None => Ok(None),
    }
}

pub fn upsert_local_repo(
    conn: &Connection,
    instance_id: &str,
    project_id: Option<i64>,
    path: &str,
    clone_url: &str,
) -> Result<String> {
    let existing: Option<String> = conn
        .query_row(
            "SELECT id FROM local_repos WHERE path = ?1",
            params![path],
            |row| row.get(0),
        )
        .optional()
        .map_err(cache_err)?;

    let stamp = fetched_stamp();
    if let Some(id) = existing {
        conn.execute(
            r#"
            UPDATE local_repos
            SET instance_id = ?1, project_id = ?2, clone_url = ?3,
                last_opened_at = ?4, preferred_remote = 'origin'
            WHERE id = ?5
            "#,
            params![instance_id, project_id, clone_url, stamp, id],
        )
        .map_err(cache_err)?;
        return Ok(id);
    }

    let id = uuid::Uuid::new_v4().to_string();
    conn.execute(
        r#"
        INSERT INTO local_repos (
            id, instance_id, project_id, path, preferred_remote, clone_url,
            added_at, last_opened_at, last_push_at
        ) VALUES (?1,?2,?3,?4,'origin',?5,?6,?6,NULL)
        "#,
        params![id, instance_id, project_id, path, clone_url, stamp],
    )
    .map_err(cache_err)?;
    Ok(id)
}

pub fn find_local_repo_by_project(
    conn: &Connection,
    instance_id: &str,
    project_id: i64,
) -> Result<Option<(String, String)>> {
    // Prefer an existing path; then most recently opened/added.
    let mut stmt = conn
        .prepare(
            "SELECT id, path FROM local_repos
             WHERE instance_id = ?1 AND project_id = ?2
             ORDER BY COALESCE(last_opened_at, added_at) DESC",
        )
        .map_err(cache_err)?;
    let rows = stmt
        .query_map(params![instance_id, project_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(cache_err)?;

    let mut first: Option<(String, String)> = None;
    for row in rows {
        let (id, path) = row.map_err(cache_err)?;
        let p = std::path::Path::new(&path);
        let exists = p.join(".git").is_dir() || p.is_dir();
        if first.is_none() {
            first = Some((id.clone(), path.clone()));
        }
        if exists {
            return Ok(Some((id, path)));
        }
    }
    Ok(first)
}

/// Look up a local_repos row by absolute path.
pub fn find_local_repo_by_path(
    conn: &Connection,
    path: &str,
) -> Result<Option<(Option<String>, Option<i64>, Option<String>)>> {
    let mut stmt = conn
        .prepare(
            "SELECT instance_id, project_id, clone_url FROM local_repos WHERE path = ?1 LIMIT 1",
        )
        .map_err(cache_err)?;
    let mut rows = stmt
        .query_map(params![path], |row| {
            Ok((
                row.get::<_, Option<String>>(0)?,
                row.get::<_, Option<i64>>(1)?,
                row.get::<_, Option<String>>(2)?,
            ))
        })
        .map_err(cache_err)?;
    match rows.next() {
        Some(Ok(v)) => Ok(Some(v)),
        Some(Err(e)) => Err(cache_err(e)),
        None => Ok(None),
    }
}

fn normalize_git_url(url: &str) -> String {
    let u = url.trim().trim_end_matches('/').trim_end_matches(".git");
    u.to_lowercase()
}

/// Match a clone/remote URL against cached project http/ssh URLs.
pub fn find_project_by_clone_url(
    conn: &Connection,
    instance_id: &str,
    clone_url: &str,
) -> Result<Option<CachedProject>> {
    let needle = normalize_git_url(clone_url);
    if needle.is_empty() {
        return Ok(None);
    }
    let projects = list_projects(conn, instance_id)?;
    for p in projects {
        let http = p.http_url_to_repo.clone();
        let ssh = p.ssh_url_to_repo.clone();
        for cand in [http, ssh].into_iter().flatten() {
            if normalize_git_url(&cand) == needle {
                return Ok(Some(p));
            }
        }
    }
    Ok(None)
}

fn cache_err(e: rusqlite::Error) -> LabDeskError {
    LabDeskError::App(
        ErrorInfo::new("LD-CACHE-001", "Cache corrupted. Rebuilding.").with_detail(e.to_string()),
    )
}
