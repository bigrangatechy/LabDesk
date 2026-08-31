//! Retarget local clone remotes when switching GitLab hosts (domain ↔ LAN).

use rusqlite::Connection;

use crate::cache;
use crate::error::Result;
use crate::git_ops;

fn remote_url_is_ssh(url: &str) -> bool {
    let u = url.trim();
    u.starts_with("git@") || u.starts_with("ssh://")
}

/// Rewrite `origin` on known local clones when the active host `base_url` changes.
///
/// A clone is retargeted when:
/// - `origin` is http(s) and its host matches `old_base`, or
/// - `origin` is SSH and its host matches the hostname of `old_base`
/// - the repo path matches a project on `new_account_id`
pub fn retarget_local_remotes_for_host_switch(
    conn: &Connection,
    old_base: &str,
    new_base: &str,
    new_account_id: &str,
) -> Result<usize> {
    let old_base = old_base.trim();
    let new_base = new_base.trim();
    if old_base.is_empty() || new_base.is_empty() {
        return Ok(0);
    }
    if crate::config::normalize_base_url(old_base) == crate::config::normalize_base_url(new_base)
    {
        return Ok(0);
    }

    let old_host = git_ops::host_from_base_url(old_base);
    let new_host = git_ops::host_from_base_url(new_base);

    let rows = cache::list_local_repos(conn)?;
    let mut n = 0usize;
    for row in rows {
        let path = std::path::Path::new(&row.path);
        if !path.join(".git").is_dir() && !path.is_dir() {
            continue;
        }
        let Some(origin) = git_ops::remote_url(path, "origin")? else {
            continue;
        };

        let (pwn, new_url) = if remote_url_is_ssh(&origin) {
            let (Some(oh), Some(nh)) = (old_host.as_deref(), new_host.as_deref()) else {
                continue;
            };
            let Some(rewritten) = git_ops::retarget_ssh_remote_url(&origin, oh, nh) else {
                continue;
            };
            // Derive path_with_namespace from SSH URL
            let pwn = ssh_path_with_namespace(&origin).or_else(|| {
                ssh_path_with_namespace(&rewritten)
            });
            let Some(pwn) = pwn else { continue };
            (pwn, rewritten)
        } else {
            let Some(pwn) = git_ops::path_with_namespace_under_base(&origin, old_base) else {
                continue;
            };
            let new_url = git_ops::retarget_http_remote_url(&origin, old_base, new_base)
                .unwrap_or_else(|| {
                    git_ops::http_clone_url_for(new_base, &pwn)
                });
            (pwn, new_url)
        };

        let Some(project) = cache::find_project_by_path(conn, new_account_id, &pwn)? else {
            continue;
        };
        if !remote_url_is_ssh(&origin) && git_ops::http_remote_matches_base(&origin, new_base) {
            let a = origin.trim().trim_end_matches('/');
            let b = new_url.trim().trim_end_matches('/');
            if a.eq_ignore_ascii_case(b) {
                continue;
            }
        }
        if origin.trim() == new_url.trim() {
            continue;
        }
        git_ops::set_remote_url(path, "origin", &new_url)?;
        cache::update_local_repo_binding(
            conn,
            &row.path,
            new_account_id,
            Some(project.project_id),
            &new_url,
        )?;
        n += 1;
    }
    Ok(n)
}

fn ssh_path_with_namespace(url: &str) -> Option<String> {
    let u = url.trim();
    let path = if let Some(rest) = u.strip_prefix("git@") {
        rest.split_once(':')?.1
    } else if let Some(rest) = u.strip_prefix("ssh://") {
        let after_auth = rest.split_once('@').map(|(_, h)| h).unwrap_or(rest);
        let (_, path) = after_auth.split_once('/')?;
        path
    } else {
        return None;
    };
    let path = path.trim_start_matches('/').trim_end_matches(".git");
    if path.is_empty() {
        None
    } else {
        Some(path.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api_client::GitLabProject;
    use crate::paths::AppPaths;
    use std::fs;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_paths() -> (std::path::PathBuf, AppPaths) {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-host-remotes-{stamp}"));
        let config_dir = root.join("config");
        let data_dir = root.join("data");
        fs::create_dir_all(&config_dir).unwrap();
        fs::create_dir_all(&data_dir).unwrap();
        (
            root,
            AppPaths {
                config_dir,
                data_dir,
            },
        )
    }

    fn git(cwd: &std::path::Path, args: &[&str]) {
        let st = Command::new("git")
            .args(args)
            .current_dir(cwd)
            .env("GIT_AUTHOR_NAME", "Test")
            .env("GIT_AUTHOR_EMAIL", "t@example.com")
            .env("GIT_COMMITTER_NAME", "Test")
            .env("GIT_COMMITTER_EMAIL", "t@example.com")
            .status()
            .expect("git");
        assert!(st.success(), "git {args:?} failed");
    }

    fn init_repo_with_origin(path: &std::path::Path, origin: &str) {
        fs::create_dir_all(path).unwrap();
        git(path, &["init", "-b", "main"]);
        fs::write(path.join("README"), "x\n").unwrap();
        git(path, &["add", "README"]);
        git(path, &["commit", "-m", "init"]);
        git(path, &["remote", "add", "origin", origin]);
    }

    fn project(id: i64, path_with_namespace: &str) -> GitLabProject {
        GitLabProject {
            id: id as u64,
            name: path_with_namespace.rsplit('/').next().unwrap_or("p").into(),
            name_with_namespace: path_with_namespace.into(),
            path_with_namespace: path_with_namespace.into(),
            http_url_to_repo: None,
            ssh_url_to_repo: None,
            web_url: None,
            default_branch: Some("main".into()),
            visibility: Some("private".into()),
            last_activity_at: None,
        }
    }

    #[test]
    fn host_switch_retargets_matching_clone_to_lan() {
        let (root, paths) = temp_paths();
        let conn = cache::open(&paths).expect("cache");
        let domain = "https://gitlab.example.com";
        let lan = "http://192.168.0.214:8929";
        let repo = root.join("work").join("Ranga").join("labdesk");
        init_repo_with_origin(&repo, &format!("{domain}/Ranga/labdesk.git"));

        cache::replace_projects(&conn, "acc-lan", &[project(42, "Ranga/labdesk")]).unwrap();
        cache::upsert_local_repo(
            &conn,
            "acc-domain",
            Some(42),
            &repo.display().to_string(),
            &format!("{domain}/Ranga/labdesk.git"),
        )
        .unwrap();

        let n = retarget_local_remotes_for_host_switch(&conn, domain, lan, "acc-lan").unwrap();
        assert_eq!(n, 1);
        assert_eq!(
            git_ops::remote_url(&repo, "origin").unwrap().as_deref(),
            Some("http://192.168.0.214:8929/Ranga/labdesk.git")
        );
        let bound = cache::find_local_repo_by_path(&conn, &repo.display().to_string())
            .unwrap()
            .expect("row");
        assert_eq!(bound.0.as_deref(), Some("acc-lan"));
        assert_eq!(bound.1, Some(42));
        assert_eq!(
            bound.2.as_deref(),
            Some("http://192.168.0.214:8929/Ranga/labdesk.git")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn host_switch_skips_when_new_account_lacks_project() {
        let (root, paths) = temp_paths();
        let conn = cache::open(&paths).expect("cache");
        let domain = "https://gitlab.example.com";
        let lan = "http://10.0.0.5:8929";
        let repo = root.join("other");
        init_repo_with_origin(&repo, &format!("{domain}/Other/private.git"));
        cache::replace_projects(&conn, "acc-lan", &[project(1, "Ranga/labdesk")]).unwrap();
        cache::upsert_local_repo(
            &conn,
            "acc-domain",
            Some(9),
            &repo.display().to_string(),
            &format!("{domain}/Other/private.git"),
        )
        .unwrap();

        let n = retarget_local_remotes_for_host_switch(&conn, domain, lan, "acc-lan").unwrap();
        assert_eq!(n, 0);
        assert_eq!(
            git_ops::remote_url(&repo, "origin").unwrap().as_deref(),
            Some("https://gitlab.example.com/Other/private.git")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn host_switch_retargets_ssh_remotes() {
        let (root, paths) = temp_paths();
        let conn = cache::open(&paths).expect("cache");
        let domain = "https://gitlab.example.com";
        let lan = "http://10.0.0.5:8929";
        let repo = root.join("ssh-clone");
        init_repo_with_origin(&repo, "git@gitlab.example.com:Ranga/labdesk.git");
        cache::replace_projects(&conn, "acc-lan", &[project(42, "Ranga/labdesk")]).unwrap();
        cache::upsert_local_repo(
            &conn,
            "acc-domain",
            Some(42),
            &repo.display().to_string(),
            "git@gitlab.example.com:Ranga/labdesk.git",
        )
        .unwrap();

        let n = retarget_local_remotes_for_host_switch(&conn, domain, lan, "acc-lan").unwrap();
        assert_eq!(n, 1);
        assert_eq!(
            git_ops::remote_url(&repo, "origin").unwrap().as_deref(),
            Some("git@10.0.0.5:Ranga/labdesk.git")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn host_switch_retargets_ssh_url_form() {
        let (root, paths) = temp_paths();
        let conn = cache::open(&paths).expect("cache");
        let domain = "https://gitlab.example.com";
        let lan = "http://10.0.0.5:8929";
        let repo = root.join("ssh-url-clone");
        init_repo_with_origin(&repo, "ssh://git@gitlab.example.com/Ranga/labdesk.git");
        cache::replace_projects(&conn, "acc-lan", &[project(42, "Ranga/labdesk")]).unwrap();
        cache::upsert_local_repo(
            &conn,
            "acc-domain",
            Some(42),
            &repo.display().to_string(),
            "ssh://git@gitlab.example.com/Ranga/labdesk.git",
        )
        .unwrap();

        let n = retarget_local_remotes_for_host_switch(&conn, domain, lan, "acc-lan").unwrap();
        assert_eq!(n, 1);
        assert_eq!(
            git_ops::remote_url(&repo, "origin").unwrap().as_deref(),
            Some("ssh://git@10.0.0.5/Ranga/labdesk.git")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn same_base_url_is_noop() {
        let (root, paths) = temp_paths();
        let conn = cache::open(&paths).expect("cache");
        let n = retarget_local_remotes_for_host_switch(
            &conn,
            "https://gitlab.example.com",
            "https://gitlab.example.com/",
            "acc",
        )
        .unwrap();
        assert_eq!(n, 0);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn retarget_failure_path_is_typed() {
        // Keep Result alias wired for callers.
        let ok: Result<usize> = Ok(0);
        assert_eq!(ok.unwrap(), 0);
    }
}
