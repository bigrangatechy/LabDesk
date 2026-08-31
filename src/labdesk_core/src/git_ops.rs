//! Local git operations via libgit2.

use std::path::{Path, PathBuf};

use git2::{
    build::RepoBuilder, AutotagOption, Cred, CredentialType, DiffFormat, DiffOptions,
    FetchOptions, IndexAddOption, PushOptions, RemoteCallbacks, Repository, StatusOptions,
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
    /// When set (imported CA), libgit2 uses this PEM bundle via GIT_SSL_CAINFO.
    pub ssl_ca_bundle: Option<&'a Path>,
}

pub struct AuthOptions<'a> {
    pub pat_fallback: Option<&'a str>,
    pub ssl_insecure: bool,
    pub prefer_ssh: bool,
    pub ssl_ca_bundle: Option<&'a Path>,
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
    let _ca_guard = if let Some(bundle) = req.ssl_ca_bundle {
        Some(crate::tls::GitSslCaInfoGuard::apply(bundle)?)
    } else {
        None
    };
    let mut fetch_opts = FetchOptions::new();
    fetch_opts.remote_callbacks(make_callbacks(
        req.url.to_string(),
        auth_pat,
        req.transport == CloneTransport::Ssh,
        req.ssl_insecure,
        true,
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

/// Soft cap on status rows returned to the UI (dirty + untracked).
/// Huge untracked trees previously inflated this into a Qt allocate ABRT.
pub const STATUS_LIST_CAP: usize = 500;

pub fn repo_status(repo_path: &Path) -> Result<Vec<FileStatusEntry>> {
    repo_status_limited(repo_path, Some(STATUS_LIST_CAP))
}

pub fn repo_status_limited(
    repo_path: &Path,
    limit: Option<usize>,
) -> Result<Vec<FileStatusEntry>> {
    let repo = open_repo(repo_path)?;
    let mut opts = StatusOptions::new();
    // Do not recurse into untracked directories: a single `build/` or
    // `node_modules/` entry beats enumerating tens of thousands of paths
    // (memory + Qt list pressure in Flatpak).
    opts.include_untracked(true)
        .recurse_untracked_dirs(false)
        .include_ignored(false);

    let statuses = repo.statuses(Some(&mut opts)).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    let mut out = Vec::new();
    for entry in statuses.iter() {
        if let Some(lim) = limit {
            if out.len() >= lim {
                break;
            }
        }
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
        // With recurse_untracked_dirs(false), directories appear as a single WT_NEW
        // entry; keep the label distinct so Stage-all / Stage are clearer.
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
///
/// Directory paths (common when status does not recurse untracked dirs) are
/// expanded like `git add <dir>/` via `Index::add_all`.
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
        let rel = rel.trim_start_matches('/').trim_end_matches('/');
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
        } else if full.is_dir() {
            // Untracked dirs are listed as a single status row; expand them.
            let mut added = 0usize;
            {
                let mut cb = |_path: &std::path::Path, _matched: &[u8]| -> i32 {
                    added += 1;
                    0
                };
                index
                    .add_all([rel], IndexAddOption::DEFAULT, Some(&mut cb))
                    .map_err(|e| {
                        LabDeskError::App(
                            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                                .with_detail(format!("stage dir {rel}: {}", e.message())),
                        )
                    })?;
            }
            n += added;
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

/// Cap for text pushed into Qt viewers (diffs / file contents).
pub const TEXT_VIEW_MAX_CHARS: usize = 200_000;

fn append_diff_line(buf: &mut String, line: &git2::DiffLine<'_>) -> bool {
    if buf.len() >= TEXT_VIEW_MAX_CHARS {
        return false;
    }
    let origin = line.origin();
    if origin == '+' || origin == '-' || origin == ' ' || origin == '@' {
        buf.push(origin);
    }
    buf.push_str(std::str::from_utf8(line.content()).unwrap_or(""));
    true
}

fn finish_diff_buf(mut buf: String, empty_msg: &str) -> String {
    if buf.len() >= TEXT_VIEW_MAX_CHARS {
        buf.push_str("\n\n… (diff truncated)\n");
    } else if buf.is_empty() {
        buf = empty_msg.into();
    }
    buf
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
    diff.print(DiffFormat::Patch, |_delta, _hunk, line| append_diff_line(&mut buf, &line))
    .map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(e.message().to_string()),
        )
    })?;

    Ok(finish_diff_buf(buf, "(no textual diff for this path)\n"))
}

pub fn fetch(repo_path: &Path, remote_name: &str, auth: &AuthOptions<'_>) -> Result<()> {
    let _ca_guard = if let Some(bundle) = auth.ssl_ca_bundle {
        Some(crate::tls::GitSslCaInfoGuard::apply(bundle)?)
    } else {
        None
    };
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
        false,
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
            "LD-GIT-024",
            "Histories have diverged. Choose merge or rebase.",
        )
        .with_detail("non-fast-forward pull"),
    ))
}

/// Ahead/behind vs upstream tracking branch (or `origin/<current>`).
/// Returns (ahead, behind, upstream_name).
pub fn ahead_behind(
    repo_path: &Path,
    remote_name: &str,
) -> Result<(usize, usize, Option<String>)> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    if !head.is_branch() {
        return Ok((0, 0, None));
    }
    let branch_name = head.shorthand().unwrap_or("HEAD").to_string();
    let local = repo
        .find_branch(&branch_name, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let upstream = match local.upstream() {
        Ok(up) => up,
        Err(_) => {
            match repo.find_branch(
                &format!("{remote_name}/{branch_name}"),
                git2::BranchType::Remote,
            ) {
                Ok(b) => b,
                Err(_) => return Ok((0, 0, None)),
            }
        }
    };
    let upstream_name = upstream
        .name()
        .ok()
        .flatten()
        .map(|s| s.to_string());
    let local_oid = head.peel_to_commit().map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?.id();
    let upstream_oid = upstream
        .get()
        .peel_to_commit()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?
        .id();
    let (ahead, behind) = repo
        .graph_ahead_behind(local_oid, upstream_oid)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok((ahead, behind, upstream_name))
}

/// Merge another local branch into HEAD. Clean merge only; conflicts → LD-GIT-020.
pub fn merge_local_branch(repo_path: &Path, their_branch: &str) -> Result<String> {
    let their_branch = their_branch.trim();
    if their_branch.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail("Branch name is required."),
        ));
    }
    let repo = open_repo(repo_path)?;
    let their = repo
        .find_branch(their_branch, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let annotated = repo
        .reference_to_annotated_commit(their.get())
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;

    let (analysis, _) = repo.merge_analysis(&[&annotated]).map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    if analysis.is_up_to_date() {
        return Ok(format!("Already up to date with {their_branch}."));
    }
    if analysis.is_fast_forward() {
        let mut head = repo.head().map_err(|e| {
            map_git_error(e, "LD-GIT-001", "Git operation failed.")
        })?;
        let name = head.name().unwrap_or("HEAD").to_string();
        head.set_target(annotated.id(), &format!("LabDesk merge FF {their_branch}"))
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        repo.set_head(&name)
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        repo.checkout_head(Some(git2::build::CheckoutBuilder::default().force()))
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        return Ok(format!("Fast-forwarded to {their_branch}."));
    }
    if !analysis.is_normal() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(format!("Cannot merge {their_branch} (unsupported analysis).")),
        ));
    }

    repo.merge(&[&annotated], None, None).map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;

    let mut index = repo.index().map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    if index.has_conflicts() {
        // Leave conflicts in place for the V2 conflict UI (do not hard-reset).
        let paths = crate::v2_git::list_conflicted_paths(repo_path).unwrap_or_default();
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-020",
                "Conflicts detected. Resolve in LabDesk or externally.",
            )
            .with_detail(if paths.is_empty() {
                format!("Merge of {their_branch} into HEAD has conflicts.")
            } else {
                format!(
                    "Merge of {their_branch} into HEAD has conflicts:\n{}",
                    paths.join("\n")
                )
            }),
        ));
    }

    let tree_oid = index.write_tree().map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    let tree = repo.find_tree(tree_oid).map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    let sig = repo.signature().map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-GIT-040",
            "Git user.name / user.email not configured.",
        ))
    })?;
    let head_commit = repo
        .head()
        .and_then(|h| h.peel_to_commit())
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let their_commit = their
        .get()
        .peel_to_commit()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let msg = format!("Merge branch '{their_branch}'");
    repo.commit(
        Some("HEAD"),
        &sig,
        &sig,
        &msg,
        &tree,
        &[&head_commit, &their_commit],
    )
    .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    repo.cleanup_state()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(format!("Merged {their_branch} into HEAD."))
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
    let _ca_guard = if let Some(bundle) = auth.ssl_ca_bundle {
        Some(crate::tls::GitSslCaInfoGuard::apply(bundle)?)
    } else {
        None
    };
    let url = remote.url().unwrap_or("").to_string();
    let mut opts = PushOptions::new();
    opts.remote_callbacks(make_callbacks(
        url,
        auth.pat_fallback.map(|s| s.to_string()),
        auth.prefer_ssh || remote_url_is_ssh(remote.url()),
        auth.ssl_insecure,
        true,
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

#[derive(Debug, Clone)]
pub struct BranchList {
    pub current: String,
    pub branches: Vec<String>,
}

/// List local branches (sorted) and the current branch name.
pub fn list_branches(repo_path: &Path) -> Result<BranchList> {
    let repo = open_repo(repo_path)?;
    let current = repo
        .head()
        .ok()
        .and_then(|h| h.shorthand().map(|s| s.to_string()))
        .unwrap_or_else(|| "HEAD".to_string());

    let mut branches = Vec::new();
    let iter = repo.branches(Some(git2::BranchType::Local)).map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    for item in iter {
        let (branch, _) = item.map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        if let Some(name) = branch.name().ok().flatten() {
            branches.push(name.to_string());
        }
    }
    branches.sort();
    Ok(BranchList { current, branches })
}

/// Local + remote-tracking branch names for Compare combos.
pub fn list_compare_refs(repo_path: &Path) -> Result<BranchList> {
    let mut listed = list_branches(repo_path)?;
    let repo = open_repo(repo_path)?;
    let iter = repo.branches(Some(git2::BranchType::Remote)).map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    for item in iter {
        let (branch, _) = item.map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        if let Some(name) = branch.name().ok().flatten() {
            // Skip remote HEAD symbolic refs like origin/HEAD
            if name.ends_with("/HEAD") {
                continue;
            }
            if !listed.branches.iter().any(|b| b == name) {
                listed.branches.push(name.to_string());
            }
        }
    }
    listed.branches.sort();
    Ok(listed)
}

#[derive(Debug, Clone)]
pub struct CompareCommit {
    pub oid: String,
    pub summary: String,
    pub author: String,
    pub time: i64,
}

#[derive(Debug, Clone)]
pub struct BranchCompare {
    pub base_ref: String,
    pub other_ref: String,
    /// Commits reachable from `other` but not `base`.
    pub ahead: usize,
    /// Commits reachable from `base` but not `other`.
    pub behind: usize,
    pub commits: Vec<CompareCommit>,
    pub diff_text: String,
}

const COMPARE_COMMIT_LIMIT: usize = 50;

/// Tip-to-tip compare: ahead/behind of `other` vs `base`, commits on other, unified diff.
pub fn compare_branches(repo_path: &Path, base_ref: &str, other_ref: &str) -> Result<BranchCompare> {
    let base_ref = base_ref.trim();
    let other_ref = other_ref.trim();
    if base_ref.is_empty() || other_ref.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail("Base and other refs are required."),
        ));
    }
    let repo = open_repo(repo_path)?;
    let base_obj = repo
        .revparse_single(base_ref)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let other_obj = repo
        .revparse_single(other_ref)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let base_commit = base_obj
        .peel_to_commit()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let other_commit = other_obj
        .peel_to_commit()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let base_oid = base_commit.id();
    let other_oid = other_commit.id();

    let (ahead, behind) = repo
        .graph_ahead_behind(other_oid, base_oid)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;

    let mut revwalk = repo
        .revwalk()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    revwalk
        .push(other_oid)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    revwalk
        .hide(base_oid)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    revwalk
        .set_sorting(git2::Sort::TOPOLOGICAL | git2::Sort::TIME)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;

    let mut commits = Vec::new();
    for oid in revwalk {
        if commits.len() >= COMPARE_COMMIT_LIMIT {
            break;
        }
        let oid = oid.map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        let c = repo
            .find_commit(oid)
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        let summary = c.summary().unwrap_or("").to_string();
        let author = c.author().name().unwrap_or("").to_string();
        commits.push(CompareCommit {
            oid: oid.to_string(),
            summary,
            author,
            time: c.time().seconds(),
        });
    }

    let base_tree = base_commit
        .tree()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let other_tree = other_commit
        .tree()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let mut opts = DiffOptions::new();
    let diff = repo
        .diff_tree_to_tree(Some(&base_tree), Some(&other_tree), Some(&mut opts))
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let mut buf = String::new();
    diff.print(DiffFormat::Patch, |_delta, _hunk, line| append_diff_line(&mut buf, &line))
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let buf = finish_diff_buf(buf, "(no textual diff between tips)\n");

    Ok(BranchCompare {
        base_ref: base_ref.to_string(),
        other_ref: other_ref.to_string(),
        ahead,
        behind,
        commits,
        diff_text: buf,
    })
}

/// Create a local branch from HEAD; optionally check it out.
pub fn create_branch(repo_path: &Path, name: &str, checkout: bool) -> Result<()> {
    let name = name.trim();
    if name.is_empty() || name.contains([' ', '\t', '\n']) {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail("Branch name must be non-empty and without whitespace."),
        ));
    }
    let repo = open_repo(repo_path)?;
    let commit = repo
        .head()
        .and_then(|h| h.peel_to_commit())
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    repo.branch(name, &commit, false)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if checkout {
        checkout_branch(repo_path, name)?;
    }
    Ok(())
}

/// Check out an existing local branch.
pub fn checkout_branch(repo_path: &Path, name: &str) -> Result<()> {
    let repo = open_repo(repo_path)?;
    let branch = repo
        .find_branch(name, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let reference = branch
        .get()
        .name()
        .ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail("Branch has no reference name."),
            )
        })?
        .to_string();

    let obj = repo
        .revparse_single(&reference)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    repo.checkout_tree(&obj, None)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    repo.set_head(&reference)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
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
    diff.print(DiffFormat::Patch, |_delta, _hunk, line| append_diff_line(&mut buf, &line))
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;

    Ok(finish_diff_buf(buf, "(no textual diff for this commit)\n"))
}

/// Paths changed in a commit (vs first parent), with binary flag.
pub fn commit_changed_files(
    repo_path: &Path,
    oid_str: &str,
) -> Result<Vec<(String, bool)>> {
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
    let mut out = Vec::new();
    for delta in diff.deltas() {
        let path = delta
            .new_file()
            .path()
            .or_else(|| delta.old_file().path())
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default();
        if path.is_empty() {
            continue;
        }
        out.push((path, delta.new_file().is_binary() || delta.old_file().is_binary()));
    }
    Ok(out)
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
///
/// When `limit` is set, stop after that many paths (unsorted beyond the walk
/// order). Used by the UI to avoid allocating huge QListWidgets.
pub fn list_tracked_files(repo_path: &Path, limit: Option<usize>) -> Result<Vec<String>> {
    let repo = open_repo(repo_path)?;
    let Ok(head) = repo.head() else {
        return Ok(Vec::new());
    };
    let Ok(tree) = head.peel_to_tree() else {
        return Ok(Vec::new());
    };
    let mut out = Vec::new();
    let walk = tree.walk(git2::TreeWalkMode::PreOrder, |root, entry| {
        if entry.kind() == Some(git2::ObjectType::Blob) {
            let name = entry.name().unwrap_or("");
            if name.is_empty() {
                return git2::TreeWalkResult::Ok;
            }
            if let Some(lim) = limit {
                if out.len() >= lim {
                    return git2::TreeWalkResult::Abort;
                }
            }
            let path = if root.is_empty() {
                name.to_string()
            } else {
                format!("{root}{name}")
            };
            out.push(path);
        }
        git2::TreeWalkResult::Ok
    });
    // libgit2 reports Abort as GIT_EUSER (-7); that is expected when we hit `limit`.
    if let Err(e) = walk {
        let hit_limit = limit.map(|lim| out.len() >= lim).unwrap_or(false);
        if !(hit_limit && e.code() == git2::ErrorCode::User) {
            return Err(LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(e.message().to_string()),
            ));
        }
    }
    if limit.is_none() {
        out.sort();
    }
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
        let meta = std::fs::metadata(&work).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(format!("stat {}: {e}", work.display())),
            )
        })?;
        // Avoid reading multi-GB blobs into memory for the viewer.
        let max_bytes = TEXT_VIEW_MAX_CHARS.saturating_mul(4);
        if meta.len() as usize > max_bytes {
            return Ok(format!(
                "(file too large to preview — {} bytes; open in external editor)\n",
                meta.len()
            ));
        }
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
    let content = blob.content();
    let max_bytes = TEXT_VIEW_MAX_CHARS.saturating_mul(4);
    if content.len() > max_bytes {
        return Ok(format!(
            "(file too large to preview — {} bytes; open in external editor)\n",
            content.len()
        ));
    }
    Ok(decode_file_bytes(content))
}

fn decode_file_bytes(bytes: &[u8]) -> String {
    if looks_binary(bytes) {
        return format!("(binary file, {} bytes — not shown)\n", bytes.len());
    }
    let text = String::from_utf8_lossy(bytes);
    if text.len() > TEXT_VIEW_MAX_CHARS {
        let mut out = text[..TEXT_VIEW_MAX_CHARS].to_string();
        out.push_str("\n\n… (file truncated for preview)\n");
        return out;
    }
    text.into_owned()
}

fn looks_binary(bytes: &[u8]) -> bool {
    let sample = &bytes[..bytes.len().min(8000)];
    sample.contains(&0) || sample.iter().filter(|b| **b < 9 && **b != b'\t' && **b != b'\n' && **b != b'\r').count() > sample.len() / 10
}

pub(crate) fn open_repo(path: &Path) -> Result<Repository> {
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

/// Set the URL of an existing remote (`origin`, etc.).
pub fn set_remote_url(repo_path: &Path, remote_name: &str, url: &str) -> Result<()> {
    let repo = open_repo(repo_path)?;
    repo.remote_set_url(remote_name, url).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                .with_detail(format!("set remote URL: {}", e.message())),
        )
    })?;
    Ok(())
}

/// True when `remote_url` is http(s) and its host[:port] matches `base_url`.
pub fn http_remote_matches_base(remote_url: &str, base_url: &str) -> bool {
    let Ok(remote) = url::Url::parse(remote_url.trim()) else {
        return false;
    };
    let Ok(base) = url::Url::parse(base_url.trim()) else {
        return false;
    };
    if remote.scheme() != "http" && remote.scheme() != "https" {
        return false;
    }
    if base.scheme() != "http" && base.scheme() != "https" {
        return false;
    }
    authority_key(&remote) == authority_key(&base)
}

fn authority_key(u: &url::Url) -> String {
    let host = u.host_str().unwrap_or("").to_ascii_lowercase();
    let port = u.port_or_known_default().unwrap_or(0);
    format!("{host}:{port}")
}

/// Repo path_with_namespace from an http(s) remote under `base_url`, if any.
///
/// `https://git.example/a/b.git` + base `https://git.example` → `a/b`
pub fn path_with_namespace_under_base(remote_url: &str, base_url: &str) -> Option<String> {
    if !http_remote_matches_base(remote_url, base_url) {
        return None;
    }
    let remote = url::Url::parse(remote_url.trim()).ok()?;
    let mut path = remote.path().trim_start_matches('/').to_string();
    if path.is_empty() {
        return None;
    }
    if let Some(stripped) = path.strip_suffix(".git") {
        path = stripped.to_string();
    }
    path = path.trim_end_matches('/').to_string();
    if path.is_empty() {
        None
    } else {
        Some(path)
    }
}

/// Build `{to_base}/{path_with_namespace}.git` (no trailing slash on base).
pub fn http_clone_url_for(base_url: &str, path_with_namespace: &str) -> String {
    let base = base_url.trim().trim_end_matches('/');
    let path = path_with_namespace
        .trim()
        .trim_start_matches('/')
        .trim_end_matches('/');
    let path = path.strip_suffix(".git").unwrap_or(path);
    format!("{base}/{path}.git")
}

/// Rewrite an http(s) URL so scheme/host/port match `base_url`, keeping path/query.
///
/// Used when the forge API returns public-hostname clone/web URLs while the
/// user is connected via a LAN `base_url` (or the reverse). SSH URLs → `None`.
pub fn rebase_http_url_to_base(url: &str, base_url: &str) -> Option<String> {
    let url = url.trim();
    let base_url = base_url.trim();
    if url.is_empty() || base_url.is_empty() {
        return None;
    }
    if url.starts_with("git@") || url.starts_with("ssh://") {
        return None;
    }
    let parsed = url::Url::parse(url).ok()?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return None;
    }
    let base = url::Url::parse(base_url).ok()?;
    if base.scheme() != "http" && base.scheme() != "https" {
        return None;
    }
    if authority_key(&parsed) == authority_key(&base) {
        let mut s = url.to_string();
        while s.ends_with('/') && s.len() > 1 {
            s.pop();
        }
        return Some(s);
    }
    let mut out = base;
    out.set_path(parsed.path());
    out.set_query(parsed.query());
    out.set_fragment(None);
    let mut s = out.to_string();
    if s.ends_with('/') && !parsed.path().ends_with('/') {
        s.pop();
    }
    Some(s)
}

/// Force project http/web URLs onto the active host `base_url`.
pub fn align_project_urls_to_base(project: &mut crate::forge_types::ForgeProject, base_url: &str) {
    let path = project.path_with_namespace.clone();
    if !path.trim().is_empty() {
        project.http_url_to_repo = Some(http_clone_url_for(base_url, &path));
        project.web_url = Some(format!(
            "{}/{}",
            base_url.trim().trim_end_matches('/'),
            path.trim().trim_start_matches('/')
        ));
    } else {
        if let Some(http) = project.http_url_to_repo.clone() {
            if let Some(rewritten) = rebase_http_url_to_base(&http, base_url) {
                project.http_url_to_repo = Some(rewritten);
            }
        }
        if let Some(web) = project.web_url.clone() {
            if let Some(rewritten) = rebase_http_url_to_base(&web, base_url) {
                project.web_url = Some(rewritten);
            }
        }
    }
}

/// If `remote_url` lives on `from_base`, return the same path on `to_base`.
pub fn retarget_http_remote_url(
    remote_url: &str,
    from_base: &str,
    to_base: &str,
) -> Option<String> {
    let path = path_with_namespace_under_base(remote_url, from_base)?;
    Some(http_clone_url_for(to_base, &path))
}

/// Rewrite `git@old:group/proj.git` / `ssh://old/...` when host matches `from_host`.
pub fn retarget_ssh_remote_url(
    remote_url: &str,
    from_host: &str,
    to_host: &str,
) -> Option<String> {
    let from_host = from_host.trim().trim_end_matches('/').to_ascii_lowercase();
    let to_host = to_host.trim().trim_end_matches('/').to_ascii_lowercase();
    if from_host.is_empty() || to_host.is_empty() || from_host == to_host {
        return None;
    }
    let u = remote_url.trim();
    if let Some(rest) = u.strip_prefix("git@") {
        let (host, path) = rest.split_once(':')?;
        if host.eq_ignore_ascii_case(&from_host) {
            return Some(format!("git@{to_host}:{path}"));
        }
        return None;
    }
    if let Some(rest) = u.strip_prefix("ssh://") {
        // ssh://[user@]host[:port]/path
        let after_auth = rest.split_once('@').map(|(_, h)| h).unwrap_or(rest);
        let (host_port, path) = after_auth.split_once('/')?;
        let host = host_port.split(':').next().unwrap_or(host_port);
        if host.eq_ignore_ascii_case(&from_host) {
            let user = if rest.contains('@') {
                rest.split_once('@').map(|(u, _)| u).unwrap_or("git")
            } else {
                "git"
            };
            return Some(format!("ssh://{user}@{to_host}/{path}"));
        }
    }
    None
}

pub fn host_from_base_url(base: &str) -> Option<String> {
    let b = base.trim().trim_end_matches('/');
    let without = b
        .strip_prefix("https://")
        .or_else(|| b.strip_prefix("http://"))?;
    let host = without.split('/').next()?.split(':').next()?;
    if host.is_empty() {
        None
    } else {
        Some(host.to_string())
    }
}

fn make_callbacks(
    url: String,
    pat: Option<String>,
    prefer_ssh: bool,
    ssl_insecure: bool,
    report_progress: bool,
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
    if report_progress {
        callbacks.transfer_progress(|stats| {
            crate::git_progress::on_transfer(
                stats.received_objects(),
                stats.total_objects(),
                stats.indexed_objects(),
                stats.received_bytes(),
            );
            true
        });
        callbacks.push_transfer_progress(|current, total, bytes| {
            crate::git_progress::on_transfer(current, total, current, bytes);
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

pub(crate) fn map_git_error(e: git2::Error, code: &'static str, message: &str) -> LabDeskError {
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
    fn compare_branches_ahead_and_diff() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-compare-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        fs::write(root.join("a.txt"), "one\n").unwrap();
        git(&root, &["add", "a.txt"]);
        git(&root, &["commit", "-m", "base"]);
        git(&root, &["checkout", "-b", "feature"]);
        fs::write(root.join("a.txt"), "one\ntwo\n").unwrap();
        git(&root, &["add", "a.txt"]);
        git(&root, &["commit", "-m", "feature change"]);
        let cmp = compare_branches(&root, "main", "feature").expect("compare");
        assert_eq!(cmp.ahead, 1);
        assert_eq!(cmp.behind, 0);
        assert!(!cmp.commits.is_empty());
        assert!(cmp.diff_text.contains("two") || cmp.diff_text.contains("+"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn list_tracked_files_respects_limit() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-tracked-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        for i in 0..12 {
            let name = format!("f{i:02}.txt");
            fs::write(root.join(&name), format!("{i}\n")).unwrap();
            git(&root, &["add", &name]);
        }
        git(&root, &["commit", "-m", "many files"]);
        let all = list_tracked_files(&root, None).expect("all");
        assert_eq!(all.len(), 12);
        let capped = list_tracked_files(&root, Some(5)).expect("capped");
        assert_eq!(capped.len(), 5);
        let probe = list_tracked_files(&root, Some(13)).expect("probe");
        assert_eq!(probe.len(), 12);
        let _ = fs::remove_dir_all(root);
    }

    /// Regression: unlimited walks on big trees previously fed huge QListWidgets
    /// (Qt `QArrayData::allocate` ABRT). Cap must stop early without erroring.
    #[test]
    fn list_tracked_files_large_tree_cap_does_not_error() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-tracked-big-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        for i in 0..250 {
            let name = format!("blob_{i:04}.txt");
            fs::write(root.join(&name), format!("{i}\n")).unwrap();
            git(&root, &["add", &name]);
        }
        git(&root, &["commit", "-m", "250 files"]);
        let capped = list_tracked_files(&root, Some(200)).expect("capped walk");
        assert_eq!(capped.len(), 200);
        let over = list_tracked_files(&root, Some(201)).expect("probe truncate");
        assert_eq!(over.len(), 201);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn status_does_not_recurse_untracked_dirs() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-status-untracked-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        fs::write(root.join("tracked.txt"), "ok\n").unwrap();
        git(&root, &["add", "tracked.txt"]);
        git(&root, &["commit", "-m", "init"]);
        let junk = root.join("build");
        fs::create_dir_all(&junk).unwrap();
        for i in 0..80 {
            fs::write(junk.join(format!("out_{i}.o")), b"x").unwrap();
        }
        let statuses = repo_status(&root).expect("status");
        // One untracked directory entry, not 80 nested files.
        assert!(
            statuses.iter().any(|e| e.path == "build" || e.path == "build/"),
            "expected untracked dir entry, got {statuses:?}"
        );
        assert!(
            !statuses.iter().any(|e| e.path.contains("out_")),
            "must not recurse untracked dirs: {statuses:?}"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn stage_paths_expands_untracked_directory() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-stage-dir-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        fs::write(root.join("tracked.txt"), "ok\n").unwrap();
        git(&root, &["add", "tracked.txt"]);
        git(&root, &["commit", "-m", "init"]);
        let nested = root.join("feature");
        fs::create_dir_all(nested.join("deep")).unwrap();
        fs::write(nested.join("a.rs"), "a\n").unwrap();
        fs::write(nested.join("deep/b.rs"), "b\n").unwrap();

        let statuses = repo_status(&root).expect("status");
        assert!(
            statuses.iter().any(|e| e.path == "feature" || e.path == "feature/"),
            "expected untracked dir row, got {statuses:?}"
        );

        let n = stage_paths(&root, &["feature".into()]).expect("stage dir");
        assert!(n >= 2, "expected nested files staged, got {n}");

        let after = repo_status(&root).expect("after");
        let staged_new: Vec<_> = after
            .iter()
            .filter(|e| e.staged && e.path.contains("feature"))
            .map(|e| e.path.as_str())
            .collect();
        assert!(
            staged_new.iter().any(|p| p.ends_with("a.rs")),
            "a.rs should be staged: {after:?}"
        );
        assert!(
            staged_new.iter().any(|p| p.ends_with("b.rs")),
            "b.rs should be staged: {after:?}"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn show_file_truncates_large_text() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-show-big-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        let big = "x".repeat(TEXT_VIEW_MAX_CHARS + 5_000);
        fs::write(root.join("fat.txt"), &big).unwrap();
        git(&root, &["add", "fat.txt"]);
        git(&root, &["commit", "-m", "fat"]);
        let text = show_file(&root, "fat.txt").expect("show");
        assert!(text.contains("truncated") || text.len() <= TEXT_VIEW_MAX_CHARS + 80);
        assert!(text.len() < big.len());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn retarget_http_remote_domain_to_lan() {
        let from = "https://gitlab.example.com";
        let to = "http://192.168.0.214:8929";
        let remote = "https://gitlab.example.com/Ranga/labdesk.git";
        assert!(http_remote_matches_base(remote, from));
        assert_eq!(
            path_with_namespace_under_base(remote, from).as_deref(),
            Some("Ranga/labdesk")
        );
        assert_eq!(
            retarget_http_remote_url(remote, from, to).as_deref(),
            Some("http://192.168.0.214:8929/Ranga/labdesk.git")
        );
        assert!(retarget_http_remote_url(remote, to, from).is_none());
        assert!(retarget_http_remote_url("git@gitlab.example.com:Ranga/labdesk.git", from, to)
            .is_none());
    }

    #[test]
    fn rebase_http_url_keeps_path_on_lan_base() {
        let base = "http://192.168.0.214:8929";
        assert_eq!(
            rebase_http_url_to_base(
                "https://gitlab.example.com/Ranga/labdesk/-/pipelines/9",
                base
            )
            .as_deref(),
            Some("http://192.168.0.214:8929/Ranga/labdesk/-/pipelines/9")
        );
        assert_eq!(
            rebase_http_url_to_base("https://gitlab.example.com/Ranga/labdesk.git", base)
                .as_deref(),
            Some("http://192.168.0.214:8929/Ranga/labdesk.git")
        );
        assert!(rebase_http_url_to_base("git@gitlab.example.com:Ranga/labdesk.git", base).is_none());
    }

    #[test]
    fn align_project_urls_to_base_overrides_api_host() {
        let mut p = crate::forge_types::ForgeProject {
            id: 1,
            name: "labdesk".into(),
            name_with_namespace: "Ranga / labdesk".into(),
            path_with_namespace: "Ranga/labdesk".into(),
            http_url_to_repo: Some("https://gitlab.example.com/Ranga/labdesk.git".into()),
            ssh_url_to_repo: None,
            web_url: Some("https://gitlab.example.com/Ranga/labdesk".into()),
            default_branch: Some("main".into()),
            visibility: None,
            last_activity_at: None,
        };
        align_project_urls_to_base(&mut p, "http://10.0.0.5:8929");
        assert_eq!(
            p.http_url_to_repo.as_deref(),
            Some("http://10.0.0.5:8929/Ranga/labdesk.git")
        );
        assert_eq!(
            p.web_url.as_deref(),
            Some("http://10.0.0.5:8929/Ranga/labdesk")
        );
    }

    #[test]
    fn set_remote_url_updates_origin() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-remote-{stamp}"));
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-b", "main"]);
        fs::write(root.join("a.txt"), "x\n").unwrap();
        git(&root, &["add", "a.txt"]);
        git(&root, &["commit", "-m", "init"]);
        git(
            &root,
            &[
                "remote",
                "add",
                "origin",
                "https://gitlab.example.com/g/p.git",
            ],
        );
        set_remote_url(
            &root,
            "origin",
            "http://10.0.0.2:8929/g/p.git",
        )
        .expect("set url");
        assert_eq!(
            remote_url(&root, "origin").unwrap().as_deref(),
            Some("http://10.0.0.2:8929/g/p.git")
        );
        let _ = fs::remove_dir_all(root);
    }
}
