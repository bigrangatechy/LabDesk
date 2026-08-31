//! Slice N: submodule management (libgit2) + optional Git LFS via host `git-lfs`.

use std::path::Path;
use std::process::Command;

use git2::{FetchOptions, SubmoduleIgnore, SubmoduleUpdateOptions};

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::git_ops::{map_git_error, open_repo, AuthOptions};

#[derive(Debug, Clone)]
pub struct SubmoduleInfo {
    pub name: String,
    pub path: String,
    pub url: Option<String>,
    pub head_id: Option<String>,
    pub index_id: Option<String>,
    pub workdir_id: Option<String>,
    pub initialized: bool,
    pub dirty: bool,
    pub status_summary: String,
}

fn short_oid(oid: Option<git2::Oid>) -> Option<String> {
    oid.map(|o| {
        let s = o.to_string();
        s.chars().take(8).collect()
    })
}

fn status_summary(st: git2::SubmoduleStatus) -> String {
    let mut parts = Vec::new();
    if st.is_wd_uninitialized() {
        parts.push("uninitialized");
    } else if st.is_in_wd() {
        parts.push("checked out");
    }
    if st.is_wd_modified() || st.is_index_modified() {
        parts.push("commit differs");
    }
    if st.is_wd_wd_modified() || st.intersects(git2::SubmoduleStatus::WD_INDEX_MODIFIED) {
        parts.push("dirty");
    }
    if st.is_wd_untracked() {
        parts.push("untracked");
    }
    if parts.is_empty() {
        parts.push("ok");
    }
    parts.join(", ")
}

/// List submodules recorded in `.gitmodules` / the superproject.
pub fn list_submodules(repo_path: &Path) -> Result<Vec<SubmoduleInfo>> {
    let repo = open_repo(repo_path)?;
    let subs = repo
        .submodules()
        .map_err(|e| map_git_error(e, "LD-GIT-050", "Failed to list submodules."))?;
    let mut out = Vec::with_capacity(subs.len());
    for sub in subs {
        let name = sub.name().unwrap_or("?").to_string();
        let path = sub.path().display().to_string();
        let url = sub.url().map(|s| s.to_string());
        let st = repo
            .submodule_status(&name, SubmoduleIgnore::Unspecified)
            .unwrap_or_else(|_| git2::SubmoduleStatus::empty());
        let initialized = !st.is_wd_uninitialized() && st.is_in_wd();
        let dirty = st.is_wd_wd_modified()
            || st.intersects(git2::SubmoduleStatus::WD_INDEX_MODIFIED)
            || st.is_wd_untracked()
            || st.is_wd_modified()
            || st.is_index_modified();
        out.push(SubmoduleInfo {
            name,
            path,
            url,
            head_id: short_oid(sub.head_id()),
            index_id: short_oid(sub.index_id()),
            workdir_id: short_oid(sub.workdir_id()),
            initialized,
            dirty,
            status_summary: status_summary(st),
        });
    }
    out.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(out)
}

fn find_sub_mut<'a>(
    repo: &'a git2::Repository,
    name_or_path: &str,
) -> Result<git2::Submodule<'a>> {
    let key = name_or_path.trim();
    if key.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-054", "Submodule not found.").with_detail("empty name"),
        ));
    }
    if let Ok(s) = repo.find_submodule(key) {
        return Ok(s);
    }
    let subs = repo
        .submodules()
        .map_err(|e| map_git_error(e, "LD-GIT-050", "Failed to list submodules."))?;
    for s in subs {
        if s.path().display().to_string() == key || s.name() == Some(key) {
            let name = s.name().unwrap_or(key).to_string();
            return repo.find_submodule(&name).map_err(|e| {
                map_git_error(e, "LD-GIT-054", "Submodule not found.")
            });
        }
    }
    Err(LabDeskError::App(
        ErrorInfo::new("LD-GIT-054", "Submodule not found.").with_detail(key.to_string()),
    ))
}

/// `git submodule init` for one submodule (or all when `name_or_path` is empty).
pub fn submodule_init(repo_path: &Path, name_or_path: Option<&str>) -> Result<usize> {
    let repo = open_repo(repo_path)?;
    let mut count = 0usize;
    if let Some(key) = name_or_path.map(str::trim).filter(|s| !s.is_empty()) {
        let mut sub = find_sub_mut(&repo, key)?;
        sub.init(false)
            .map_err(|e| map_git_error(e, "LD-GIT-051", "Failed to init submodule."))?;
        count = 1;
    } else {
        let names: Vec<String> = repo
            .submodules()
            .map_err(|e| map_git_error(e, "LD-GIT-050", "Failed to list submodules."))?
            .into_iter()
            .filter_map(|s| s.name().map(|n| n.to_string()))
            .collect();
        for name in names {
            let mut sub = repo
                .find_submodule(&name)
                .map_err(|e| map_git_error(e, "LD-GIT-054", "Submodule not found."))?;
            sub.init(false)
                .map_err(|e| map_git_error(e, "LD-GIT-051", "Failed to init submodule."))?;
            count += 1;
        }
    }
    Ok(count)
}

fn update_opts_for(auth: &AuthOptions<'_>, url: &str) -> SubmoduleUpdateOptions<'static> {
    let auth_pat = auth.pat_fallback.map(|s| s.to_string());
    let mut fetch_opts = FetchOptions::new();
    fetch_opts.remote_callbacks(crate::git_ops::make_callbacks(
        url.to_string(),
        auth_pat,
        auth.prefer_ssh || url.starts_with("git@") || url.starts_with("ssh://"),
        auth.ssl_insecure,
        true,
    ));
    let mut opts = SubmoduleUpdateOptions::new();
    opts.fetch(fetch_opts);
    opts
}

/// `git submodule update --init` for one submodule (or all when empty).
pub fn submodule_update(
    repo_path: &Path,
    name_or_path: Option<&str>,
    auth: &AuthOptions<'_>,
) -> Result<usize> {
    let _ca_guard = if let Some(bundle) = auth.ssl_ca_bundle {
        Some(crate::tls::GitSslCaInfoGuard::apply(bundle)?)
    } else {
        None
    };
    let repo = open_repo(repo_path)?;
    let mut count = 0usize;
    let targets: Vec<String> = if let Some(key) = name_or_path.map(str::trim).filter(|s| !s.is_empty())
    {
        let sub = find_sub_mut(&repo, key)?;
        vec![sub.name().unwrap_or(key).to_string()]
    } else {
        repo.submodules()
            .map_err(|e| map_git_error(e, "LD-GIT-050", "Failed to list submodules."))?
            .into_iter()
            .filter_map(|s| s.name().map(|n| n.to_string()))
            .collect()
    };
    for name in targets {
        let mut sub = repo
            .find_submodule(&name)
            .map_err(|e| map_git_error(e, "LD-GIT-054", "Submodule not found."))?;
        let url = sub.url().unwrap_or("").to_string();
        let mut opts = update_opts_for(auth, &url);
        sub.update(true, Some(&mut opts))
            .map_err(|e| map_git_error(e, "LD-GIT-052", "Failed to update submodule."))?;
        count += 1;
    }
    Ok(count)
}

/// `git submodule sync` for one submodule (or all when empty).
pub fn submodule_sync(repo_path: &Path, name_or_path: Option<&str>) -> Result<usize> {
    let repo = open_repo(repo_path)?;
    let mut count = 0usize;
    if let Some(key) = name_or_path.map(str::trim).filter(|s| !s.is_empty()) {
        let mut sub = find_sub_mut(&repo, key)?;
        sub.sync()
            .map_err(|e| map_git_error(e, "LD-GIT-053", "Failed to sync submodule."))?;
        count = 1;
    } else {
        let names: Vec<String> = repo
            .submodules()
            .map_err(|e| map_git_error(e, "LD-GIT-050", "Failed to list submodules."))?
            .into_iter()
            .filter_map(|s| s.name().map(|n| n.to_string()))
            .collect();
        for name in names {
            let mut sub = repo
                .find_submodule(&name)
                .map_err(|e| map_git_error(e, "LD-GIT-054", "Submodule not found."))?;
            sub.sync()
                .map_err(|e| map_git_error(e, "LD-GIT-053", "Failed to sync submodule."))?;
            count += 1;
        }
    }
    Ok(count)
}

/// True when `.gitattributes` (or nested) mentions `filter=lfs`.
pub fn repo_mentions_lfs(repo_path: &Path) -> bool {
    let candidates = [
        repo_path.join(".gitattributes"),
        repo_path.join(".git").join("info").join("attributes"),
    ];
    for path in candidates {
        if let Ok(text) = std::fs::read_to_string(path) {
            if text.lines().any(|l| l.contains("filter=lfs")) {
                return true;
            }
        }
    }
    false
}

/// Whether the host has a working `git-lfs` binary.
pub fn lfs_cli_available() -> bool {
    Command::new("git-lfs")
        .arg("version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[derive(Debug, Clone)]
pub struct LfsStatusInfo {
    pub available: bool,
    pub mentions_lfs: bool,
    pub version: Option<String>,
    pub summary: String,
}

/// Probe LFS tooling and optionally run `git lfs status`.
pub fn lfs_status(repo_path: &Path) -> Result<LfsStatusInfo> {
    let mentions = repo_mentions_lfs(repo_path);
    if !lfs_cli_available() {
        return Ok(LfsStatusInfo {
            available: false,
            mentions_lfs: mentions,
            version: None,
            summary: if mentions {
                "This repo references Git LFS, but git-lfs is not installed on the host."
                    .into()
            } else {
                "git-lfs is not installed on the host.".into()
            },
        });
    }
    let ver = Command::new("git-lfs")
        .arg("version")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
    let out = Command::new("git")
        .args(["lfs", "status"])
        .current_dir(repo_path)
        .output()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-061", "Failed to read LFS status.")
                    .with_detail(e.to_string()),
            )
        })?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-061", "Failed to read LFS status.")
                .with_detail(err.trim().chars().take(200).collect::<String>()),
        ));
    }
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let summary = if text.is_empty() {
        "No LFS objects pending (git lfs status empty).".into()
    } else {
        // Keep UI compact: first ~12 lines.
        text.lines().take(12).collect::<Vec<_>>().join("\n")
    };
    Ok(LfsStatusInfo {
        available: true,
        mentions_lfs: mentions,
        version: ver,
        summary,
    })
}

/// Fetch LFS objects for the working tree (`git lfs pull`).
pub fn lfs_pull(repo_path: &Path) -> Result<String> {
    if !lfs_cli_available() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-GIT-060",
            "git-lfs is not available.",
        )));
    }
    let out = Command::new("git")
        .args(["lfs", "pull"])
        .current_dir(repo_path)
        .output()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-062", "Failed to pull LFS objects.")
                    .with_detail(e.to_string()),
            )
        })?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-062", "Failed to pull LFS objects.")
                .with_detail(err.trim().chars().take(200).collect::<String>()),
        ));
    }
    let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
    Ok(if stdout.is_empty() {
        "LFS pull completed.".into()
    } else {
        stdout
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn git(cwd: &Path, args: &[&str]) {
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

    #[test]
    fn list_submodules_empty_repo() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-sub-empty-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        fs::write(root.join("a.txt"), "x\n").unwrap();
        git(&root, &["add", "a.txt"]);
        git(&root, &["commit", "-m", "init"]);
        let list = list_submodules(&root).expect("list");
        assert!(list.is_empty());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn mentions_lfs_from_gitattributes() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-lfs-attr-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        assert!(!repo_mentions_lfs(&root));
        fs::write(root.join(".gitattributes"), "*.bin filter=lfs diff=lfs merge=lfs -text\n")
            .unwrap();
        assert!(repo_mentions_lfs(&root));
        let _ = fs::remove_dir_all(root);
    }
}
