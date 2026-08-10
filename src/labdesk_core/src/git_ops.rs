//! Local git operations via libgit2.

use std::path::{Path, PathBuf};

use git2::{
    build::RepoBuilder, AutotagOption, Cred, CredentialType, DiffFormat, DiffOptions,
    FetchOptions, PushOptions, RemoteCallbacks, Repository, StatusOptions,
};

use crate::error::{ErrorInfo, LabDeskError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloneTransport {
    Https,
    Ssh,
}

pub struct CloneRequest<'a> {
    pub url: &'a str,
    pub destination: &'a Path,
    pub transport: CloneTransport,
    pub pat_fallback: Option<&'a str>,
    pub ssl_insecure: bool,
}

pub struct AuthOptions<'a> {
    pub pat_fallback: Option<&'a str>,
    pub ssl_insecure: bool,
    pub prefer_ssh: bool,
}

pub fn clone_repository(req: &CloneRequest<'_>) -> Result<()> {
    if req.destination.exists() {
        let is_empty = std::fs::read_dir(req.destination)
            .map(|mut d| d.next().is_none())
            .unwrap_or(false);
        if req.destination.join(".git").is_dir() {
            return Err(LabDeskError::App(
                ErrorInfo::new("LD-GIT-030", "Clone failed.").with_detail(format!(
                    "already a git repository: {}",
                    req.destination.display()
                )),
            ));
        }
        if !is_empty {
            return Err(LabDeskError::App(
                ErrorInfo::new("LD-GIT-030", "Clone failed.").with_detail(format!(
                    "destination already exists and is not empty: {}",
                    req.destination.display()
                )),
            ));
        }
    }

    if let Some(parent) = req.destination.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-030", "Clone failed.")
                    .with_detail(format!("create parent dirs: {e}")),
            )
        })?;
    }

    let auth_pat = req.pat_fallback.map(|s| s.to_string());
    let mut fetch_opts = FetchOptions::new();
    fetch_opts.remote_callbacks(make_callbacks(
        req.url.to_string(),
        auth_pat,
        req.transport == CloneTransport::Ssh,
        req.ssl_insecure,
    ));

    let mut builder = RepoBuilder::new();
    builder.fetch_options(fetch_opts);

    builder
        .clone(req.url, req.destination)
        .map_err(|e| map_git_error(e, "LD-GIT-030", "Clone failed."))?;
    Ok(())
}

#[derive(Debug, Clone)]
pub struct FileStatusEntry {
    pub path: String,
    pub status: String,
    /// True if the index differs from HEAD for this path.
    pub staged: bool,
    /// True if the worktree differs from the index (or untracked).
    pub unstaged: bool,
}

pub fn repo_status(repo_path: &Path) -> Result<Vec<FileStatusEntry>> {
    let repo = open_repo(repo_path)?;
    let mut opts = StatusOptions::new();
    opts.include_untracked(true)
        .recurse_untracked_dirs(true)
        .include_ignored(false);

    let statuses = repo.statuses(Some(&mut opts)).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    let mut out = Vec::new();
    for entry in statuses.iter() {
        let path = entry.path().unwrap_or("").to_string();
        if path.is_empty() {
            continue;
        }
        let st = entry.status();
        let staged = st.is_index_new()
            || st.is_index_modified()
            || st.is_index_deleted()
            || st.is_index_renamed()
            || st.is_index_typechange();
        let unstaged = st.is_wt_new()
            || st.is_wt_modified()
            || st.is_wt_deleted()
            || st.is_wt_renamed()
            || st.is_wt_typechange()
            || st.is_conflicted();
        let label = status_label(st, staged, unstaged);
        out.push(FileStatusEntry {
            path,
            status: label,
            staged,
            unstaged,
        });
    }
    out.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(out)
}

fn status_label(st: git2::Status, staged: bool, unstaged: bool) -> String {
    if st.is_conflicted() {
        return "conflict".into();
    }
    if st.is_wt_new() && !staged {
        return "untracked".into();
    }
    if staged && unstaged {
        return "staged+mod".into();
    }
    if staged {
        if st.is_index_new() {
            return "staged new".into();
        }
        if st.is_index_deleted() {
            return "staged del".into();
        }
        return "staged".into();
    }
    if st.is_wt_deleted() || st.is_index_deleted() {
        return "deleted".into();
    }
    if st.is_wt_renamed() || st.is_index_renamed() {
        return "renamed".into();
    }
    "modified".into()
}

/// Stage paths (add to index). Creates index entries for new files.
pub fn stage_paths(repo_path: &Path, paths: &[String]) -> Result<usize> {
    let repo = open_repo(repo_path)?;
    let mut index = repo.index().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let mut n = 0usize;
    for rel in paths {
        let rel = rel.trim_start_matches('/');
        if rel.is_empty() || rel.contains("..") {
            continue;
        }
        let full = repo_path.join(rel);
        if full.is_file() {
            index.add_path(std::path::Path::new(rel)).map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                        .with_detail(format!("stage {rel}: {}", e.message())),
                )
            })?;
            n += 1;
        } else {
            // Deleted from worktree — stage the removal if it was tracked.
            match index.remove_path(std::path::Path::new(rel)) {
                Ok(()) => n += 1,
                Err(e) => {
                    return Err(LabDeskError::App(
                        ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                            .with_detail(format!("stage delete {rel}: {}", e.message())),
                    ));
                }
            }
        }
    }
    index.write().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok(n)
}

/// Unstage paths (reset index entries to HEAD).
pub fn unstage_paths(repo_path: &Path, paths: &[String]) -> Result<usize> {
    let repo = open_repo(repo_path)?;
    let cleaned: Vec<&str> = paths
        .iter()
        .map(|s| s.trim_start_matches('/'))
        .filter(|s| !s.is_empty() && !s.contains(".."))
        .collect();
    if cleaned.is_empty() {
        return Ok(0);
    }

    let head_oid = match repo.head() {
        Ok(head) => match head.peel_to_commit() {
            Ok(c) => Some(c.id()),
            Err(_) => None,
        },
        Err(_) => None,
    };

    if let Some(oid) = head_oid {
        let obj = repo.find_object(oid, None).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        repo.reset_default(Some(&obj), cleaned.iter().copied())
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                        .with_detail(e.message().to_string()),
                )
            })?;
        return Ok(cleaned.len());
    }

    let mut index = repo.index().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let mut n = 0usize;
    for rel in &cleaned {
        if index.remove_path(std::path::Path::new(rel)).is_ok() {
            n += 1;
        }
    }
    index.write().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok(n)
}

/// Create a commit from the current index. Uses repo `user.name` / `user.email`.
pub fn commit_index(repo_path: &Path, message: &str) -> Result<String> {
    let message = message.trim();
    if message.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-GIT-041",
            "Commit message is required.",
        )));
    }
    let repo = open_repo(repo_path)?;
    let sig = repo.signature().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-040",
                "Git user.name / user.email not configured.",
            )
            .with_detail(e.message().to_string()),
        )
    })?;

    let mut index = repo.index().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    // Ensure something is staged vs HEAD.
    let tree_oid = index.write_tree().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let tree = repo.find_tree(tree_oid).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    let parent_commit = match repo.head() {
        Ok(head) => Some(head.peel_to_commit().map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?),
        Err(_) => None,
    };

    if let Some(ref parent) = parent_commit {
        if parent.tree_id() == tree_oid {
            return Err(LabDeskError::App(ErrorInfo::new(
                "LD-GIT-042",
                "Nothing staged to commit.",
            )));
        }
    } else if tree.is_empty() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-GIT-042",
            "Nothing staged to commit.",
        )));
    }

    let parents: Vec<&git2::Commit> = match parent_commit.as_ref() {
        Some(c) => vec![c],
        None => vec![],
    };

    let oid = repo
        .commit(Some("HEAD"), &sig, &sig, message, &tree, &parents)
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    Ok(oid.to_string())
}

/// Unified diff text for a path (workdir vs HEAD / index as appropriate).
pub fn file_diff(repo_path: &Path, rel_path: &str) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let mut opts = DiffOptions::new();
    opts.pathspec(rel_path);
    opts.include_untracked(true);

    let diff = if let Ok(head) = repo.head().and_then(|h| h.peel_to_tree()) {
        repo.diff_tree_to_workdir_with_index(Some(&head), Some(&mut opts))
    } else {
        repo.diff_tree_to_workdir_with_index(None, Some(&mut opts))
    }
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    let mut buf = String::new();
    diff.print(DiffFormat::Patch, |_delta, _hunk, line| {
        let origin = line.origin();
        if origin == '+' || origin == '-' || origin == ' ' {
            buf.push(origin);
        }
        buf.push_str(std::str::from_utf8(line.content()).unwrap_or(""));
        true
    })
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    if buf.is_empty() {
        buf = "(no textual diff for this path)\n".into();
    }
    Ok(buf)
}

pub fn fetch(repo_path: &Path, remote_name: &str, auth: &AuthOptions<'_>) -> Result<()> {
    let repo = open_repo(repo_path)?;
    let mut remote = repo.find_remote(remote_name).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let url = remote.url().unwrap_or("").to_string();
    let mut opts = FetchOptions::new();
    opts.remote_callbacks(make_callbacks(
        url,
        auth.pat_fallback.map(|s| s.to_string()),
        auth.prefer_ssh || remote_url_is_ssh(remote.url()),
        auth.ssl_insecure,
    ));
    opts.download_tags(AutotagOption::All);
    remote
        .fetch(&[] as &[&str], Some(&mut opts), None)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
}

/// Fetch + fast-forward merge of upstream tracking branch when possible.
pub fn pull(repo_path: &Path, remote_name: &str, auth: &AuthOptions<'_>) -> Result<String> {
    fetch(repo_path, remote_name, auth)?;
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    if !head.is_branch() {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-GIT-001",
            "Git operation failed.",
        ).with_detail("HEAD is not a branch")));
    }
    let branch_name = head.shorthand().unwrap_or("HEAD").to_string();
    let upstream_ref = {
        let local = repo.find_branch(&branch_name, git2::BranchType::Local).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        match local.upstream() {
            Ok(up) => up,
            Err(_) => {
                // Fallback origin/<branch>
                repo.find_branch(
                    &format!("{remote_name}/{branch_name}"),
                    git2::BranchType::Remote,
                )
                .map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                            .with_detail(format!("no upstream to pull: {e}")),
                    )
                })?
            }
        }
    };

    let annotated = repo
        .reference_to_annotated_commit(upstream_ref.get())
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;

    let (analysis, _) = repo.merge_analysis(&[&annotated]).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    if analysis.is_up_to_date() {
        return Ok("Already up to date.".into());
    }
    if analysis.is_fast_forward() {
        let mut reference = head;
        let name = reference.name().unwrap_or("HEAD").to_string();
        let oid = annotated.id();
        reference.set_target(oid, "LabDesk pull (fast-forward)").map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        repo.set_head(&name).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                        .with_detail(e.message().to_string()),
                )
            })?;
        return Ok("Pulled (fast-forward).".into());
    }

    Err(LabDeskError::App(
        ErrorInfo::new(
            "LD-GIT-020",
            "Conflicts detected. Resolve externally.",
        )
        .with_detail("non-fast-forward pull; merge/conflict UI not in V1"),
    ))
}

pub fn push(
    repo_path: &Path,
    remote_name: &str,
    force: bool,
    auth: &AuthOptions<'_>,
) -> Result<()> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let branch = head.shorthand().unwrap_or("HEAD");
    let refspec = if force {
        format!("+refs/heads/{branch}:refs/heads/{branch}")
    } else {
        format!("refs/heads/{branch}:refs/heads/{branch}")
    };

    let mut remote = repo.find_remote(remote_name).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let url = remote.url().unwrap_or("").to_string();
    let mut opts = PushOptions::new();
    opts.remote_callbacks(make_callbacks(
        url,
        auth.pat_fallback.map(|s| s.to_string()),
        auth.prefer_ssh || remote_url_is_ssh(remote.url()),
        auth.ssl_insecure,
    ));

    remote
        .push(&[refspec.as_str()], Some(&mut opts))
        .map_err(|e| {
            let msg = e.message().to_string();
            let lower = msg.to_lowercase();
            if lower.contains("non-fast-forward") || lower.contains("rejected") {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-010", "Push rejected. Pull first?").with_detail(msg),
                )
            } else if force {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-011", "Force push failed.").with_detail(msg),
                )
            } else {
                map_git_error(e, "LD-GIT-001", "Git operation failed.")
            }
        })?;
    Ok(())
}

pub fn current_branch(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok(head.shorthand().unwrap_or("HEAD").to_string())
}

/// Short subject of HEAD commit (empty string if unavailable).
pub fn head_commit_summary(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let commit = head.peel_to_commit().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let msg = commit.summary().unwrap_or("").trim();
    let short = commit.id().to_string();
    let short = &short[..7.min(short.len())];
    if msg.is_empty() {
        Ok(short.to_string())
    } else {
        Ok(format!("{short} — {msg}"))
    }
}

#[derive(Debug, Clone)]
pub struct CommitInfo {
    pub oid: String,
    pub short_oid: String,
    pub summary: String,
    pub body: String,
    pub author_name: String,
    pub author_email: String,
    pub time: i64,
}

/// Walk commits reachable from HEAD (newest first), up to `limit`.
pub fn commit_log(repo_path: &Path, limit: usize) -> Result<Vec<CommitInfo>> {
    let repo = open_repo(repo_path)?;
    let mut walk = repo.revwalk().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    walk.set_sorting(git2::Sort::TIME).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    walk.push_head().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    let mut out = Vec::new();
    for oid_res in walk {
        if out.len() >= limit {
            break;
        }
        let oid = oid_res.map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        let commit = repo.find_commit(oid).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
        out.push(commit_to_info(&commit));
    }
    Ok(out)
}

pub fn commit_info(repo_path: &Path, oid_str: &str) -> Result<CommitInfo> {
    let repo = open_repo(repo_path)?;
    let oid = git2::Oid::from_str(oid_str.trim()).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let commit = repo.find_commit(oid).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok(commit_to_info(&commit))
}

/// Unified diff of `oid` against its first parent (or empty tree for root).
pub fn commit_diff(repo_path: &Path, oid_str: &str) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let oid = git2::Oid::from_str(oid_str.trim()).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let commit = repo.find_commit(oid).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let tree = commit.tree().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let parent_tree = if commit.parent_count() > 0 {
        Some(
            commit
                .parent(0)
                .and_then(|p| p.tree())
                .map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                            .with_detail(e.message().to_string()),
                    )
                })?,
        )
    } else {
        None
    };

    let mut opts = DiffOptions::new();
    let diff = repo
        .diff_tree_to_tree(parent_tree.as_ref(), Some(&tree), Some(&mut opts))
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;

    let mut buf = String::new();
    diff.print(DiffFormat::Patch, |_delta, _hunk, line| {
        let origin = line.origin();
        if origin == '+' || origin == '-' || origin == ' ' {
            buf.push(origin);
        }
        buf.push_str(std::str::from_utf8(line.content()).unwrap_or(""));
        true
    })
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    if buf.is_empty() {
        buf = "(no textual diff for this commit)\n".into();
    }
    Ok(buf)
}

fn commit_to_info(commit: &git2::Commit<'_>) -> CommitInfo {
    let oid = commit.id().to_string();
    let short_oid = oid[..7.min(oid.len())].to_string();
    let summary = commit.summary().unwrap_or("").to_string();
    let message = commit.message().unwrap_or("").to_string();
    let body = {
        let trimmed = message.trim();
        if let Some(rest) = trimmed.strip_prefix(summary.trim()) {
            rest.trim_start_matches('\n').to_string()
        } else {
            String::new()
        }
    };
    let author = commit.author();
    CommitInfo {
        oid,
        short_oid,
        summary: summary.trim().to_string(),
        body,
        author_name: author.name().unwrap_or("").to_string(),
        author_email: author.email().unwrap_or("").to_string(),
        time: author.when().seconds(),
    }
}

/// Paths of blobs in HEAD (tracked files). Empty repo / no HEAD → empty list.
pub fn list_tracked_files(repo_path: &Path) -> Result<Vec<String>> {
    let repo = open_repo(repo_path)?;
    let Ok(head) = repo.head() else {
        return Ok(Vec::new());
    };
    let Ok(tree) = head.peel_to_tree() else {
        return Ok(Vec::new());
    };
    let mut out = Vec::new();
    tree.walk(git2::TreeWalkMode::PreOrder, |root, entry| {
        if entry.kind() == Some(git2::ObjectType::Blob) {
            let name = entry.name().unwrap_or("");
            if name.is_empty() {
                return git2::TreeWalkResult::Ok;
            }
            let path = if root.is_empty() {
                name.to_string()
            } else {
                format!("{root}{name}")
            };
            out.push(path);
        }
        git2::TreeWalkResult::Ok
    })
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    out.sort();
    Ok(out)
}

/// Read file for the viewer: workdir if present, else HEAD blob.
pub fn show_file(repo_path: &Path, rel_path: &str) -> Result<String> {
    let rel = rel_path.trim_start_matches('/');
    if rel.is_empty() || rel.contains("..") {
        return Err(LabDeskError::App(ErrorInfo::new(
            "LD-GIT-001",
            "Git operation failed.",
        ).with_detail("invalid path")));
    }

    let work = repo_path.join(rel);
    if work.is_file() {
        let bytes = std::fs::read(&work).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(format!("read {}: {e}", work.display())),
            )
        })?;
        return Ok(decode_file_bytes(&bytes));
    }

    let repo = open_repo(repo_path)?;
    let tree = repo
        .head()
        .and_then(|h| h.peel_to_tree())
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    let entry = tree.get_path(Path::new(rel)).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(format!("{rel}: {}", e.message())),
        )
    })?;
    let blob = entry.to_object(&repo).and_then(|o| o.peel_to_blob()).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok(decode_file_bytes(blob.content()))
}

fn decode_file_bytes(bytes: &[u8]) -> String {
    if looks_binary(bytes) {
        return format!("(binary file, {} bytes — not shown)\n", bytes.len());
    }
    String::from_utf8_lossy(bytes).into_owned()
}

fn looks_binary(bytes: &[u8]) -> bool {
    let sample = &bytes[..bytes.len().min(8000)];
    sample.contains(&0) || sample.iter().filter(|b| **b < 9 && **b != b'\t' && **b != b'\n' && **b != b'\r').count() > sample.len() / 10
}

fn open_repo(path: &Path) -> Result<Repository> {
    if !path.join(".git").exists() && Repository::discover(path).is_err() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-031", "Repository folder is missing.")
                .with_detail(path.display().to_string()),
        ));
    }
    Repository::open(path).or_else(|_| Repository::discover(path)).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-031", "Repository folder is missing.")
                .with_detail(format!("{}: {}", path.display(), e.message())),
        )
    })
}

/// True if `path` is (or contains) a git working tree / repo.
pub fn is_git_repository(path: &Path) -> bool {
    open_repo(path).is_ok()
}

/// Resolve canonical absolute path for a repo root (best-effort).
pub fn resolve_repo_root(path: &Path) -> Result<PathBuf> {
    let repo = open_repo(path)?;
    let root = repo
        .workdir()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| path.to_path_buf());
    let canonical = std::fs::canonicalize(&root).unwrap_or(root);
    Ok(canonical)
}

/// URL of named remote, if configured.
pub fn remote_url(repo_path: &Path, remote_name: &str) -> Result<Option<String>> {
    let repo = open_repo(repo_path)?;
    let Ok(remote) = repo.find_remote(remote_name) else {
        return Ok(None);
    };
    Ok(remote.url().map(|s| s.to_string()))
}

fn make_callbacks(
    url: String,
    pat: Option<String>,
    prefer_ssh: bool,
    ssl_insecure: bool,
) -> RemoteCallbacks<'static> {
    let mut callbacks = RemoteCallbacks::new();
    callbacks.credentials(move |_url, username_from_url, allowed| {
        credentials_cb(
            &url,
            username_from_url,
            allowed,
            prefer_ssh,
            pat.as_deref(),
        )
    });
    if ssl_insecure {
        callbacks.certificate_check(|_cert, _valid| {
            Ok(git2::CertificateCheckStatus::CertificateOk)
        });
    }
    callbacks
}

fn remote_url_is_ssh(url: Option<&str>) -> bool {
    url.map(|u| u.starts_with("git@") || u.starts_with("ssh://"))
        .unwrap_or(false)
}

fn credentials_cb(
    url: &str,
    username_from_url: Option<&str>,
    allowed: CredentialType,
    prefer_ssh: bool,
    pat_fallback: Option<&str>,
) -> std::result::Result<Cred, git2::Error> {
    if prefer_ssh || allowed.contains(CredentialType::SSH_KEY) {
        if allowed.contains(CredentialType::SSH_KEY) {
            let username = username_from_url.unwrap_or("git");
            if let Ok(cred) = Cred::ssh_key_from_agent(username) {
                return Ok(cred);
            }
        }
    }

    if allowed.contains(CredentialType::USER_PASS_PLAINTEXT) {
        let cfg = git2::Config::open_default()?;
        if let Ok(cred) = Cred::credential_helper(&cfg, url, username_from_url) {
            return Ok(cred);
        }
        if let Some(pat) = pat_fallback {
            let user = username_from_url.unwrap_or("oauth2");
            return Cred::userpass_plaintext(user, pat);
        }
    }

    Err(git2::Error::from_str(
        "no usable git credentials (helper empty and no PAT fallback)",
    ))
}

fn map_git_error(e: git2::Error, code: &'static str, message: &str) -> LabDeskError {
    let msg = e.message().to_string();
    let lower = msg.to_lowercase();
    if lower.contains("authentication")
        || lower.contains("auth fail")
        || lower.contains("credentials")
        || lower.contains("unauthorized")
        || lower.contains("401")
        || lower.contains("403")
    {
        return LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-002",
                "Git authentication failed. Check credentials or SSH keys.",
            )
            .with_detail(msg),
        );
    }
    if lower.contains("certificate") || lower.contains("ssl") || lower.contains("tls") {
        return LabDeskError::App(
            ErrorInfo::new(
                "LD-NET-010",
                "Certificate not trusted. Import CA or allow.",
            )
            .with_detail(msg),
        );
    }
    LabDeskError::App(ErrorInfo::new(code, message).with_detail(msg))
}

/// Destination path: `{clone_root}/{path_with_namespace}`.
pub fn destination_for(clone_root: &Path, path_with_namespace: &str) -> PathBuf {
    let mut path = clone_root.to_path_buf();
    for part in path_with_namespace.split('/') {
        if !part.is_empty() && part != "." && part != ".." {
            path.push(part);
        }
    }
    path
}
