//! V2 git helpers: stash, rebase, conflicts, discard, branch delete, upstream.

use std::path::Path;

use git2::{build::CheckoutBuilder, Repository, ResetType, StashFlags};

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::git_ops::{map_git_error, open_repo};

pub fn list_conflicted_paths(repo_path: &Path) -> Result<Vec<String>> {
    let repo = open_repo(repo_path)?;
    let index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let mut paths = Vec::new();
    let conflicts = index.conflicts().map_err(|e| {
        map_git_error(e, "LD-GIT-001", "Git operation failed.")
    })?;
    for c in conflicts {
        let c = c.map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        let entry = c.our.as_ref().or(c.their.as_ref()).or(c.ancestor.as_ref());
        if let Some(entry) = entry {
            let path = String::from_utf8_lossy(&entry.path).into_owned();
            if !paths.iter().any(|p| p == &path) {
                paths.push(path);
            }
        }
    }
    paths.sort();
    Ok(paths)
}

pub fn repo_in_merge_or_rebase(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let state = repo.state();
    Ok(format!("{state:?}"))
}

/// Leave merge conflicts in place (do not hard-reset).
pub fn merge_upstream(
    repo_path: &Path,
    remote_name: &str,
) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if !head.is_branch() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail("HEAD is not a branch"),
        ));
    }
    let branch_name = head.shorthand().unwrap_or("HEAD").to_string();
    let local = repo
        .find_branch(&branch_name, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let upstream = match local.upstream() {
        Ok(up) => up,
        Err(_) => repo
            .find_branch(
                &format!("{remote_name}/{branch_name}"),
                git2::BranchType::Remote,
            )
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                        .with_detail(format!("no upstream: {e}")),
                )
            })?,
    };
    let annotated = repo
        .reference_to_annotated_commit(upstream.get())
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let (analysis, _) = repo
        .merge_analysis(&[&annotated])
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if analysis.is_up_to_date() {
        return Ok("Already up to date.".into());
    }
    if analysis.is_fast_forward() {
        let mut reference = repo.head().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        let name = reference.name().unwrap_or("HEAD").to_string();
        reference
            .set_target(annotated.id(), "LabDesk merge upstream FF")
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        repo.set_head(&name)
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        repo.checkout_head(Some(CheckoutBuilder::default().force()))
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
        return Ok("Fast-forwarded to upstream.".into());
    }
    repo.merge(&[&annotated], None, None)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if index.has_conflicts() {
        let paths = list_conflicted_paths(repo_path)?;
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-020",
                "Conflicts detected. Resolve in LabDesk or externally.",
            )
            .with_detail(paths.join("\n")),
        ));
    }
    finish_merge_commit(&repo, "Merge remote-tracking branch")?;
    Ok("Merged upstream.".into())
}

fn finish_merge_commit(repo: &Repository, msg: &str) -> Result<()> {
    let mut index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let tree_oid = index
        .write_tree()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let tree = repo
        .find_tree(tree_oid)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
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
    let mut parents = vec![head_commit];
    if let Ok(merge_head) = repo.find_reference("MERGE_HEAD") {
        if let Ok(c) = merge_head.peel_to_commit() {
            parents.push(c);
        }
    }
    let parent_refs: Vec<&git2::Commit> = parents.iter().collect();
    repo.commit(
        Some("HEAD"),
        &sig,
        &sig,
        msg,
        &tree,
        &parent_refs,
    )
    .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    repo.cleanup_state()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
}

pub fn continue_merge(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if index.has_conflicts() {
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-023",
                "Could not continue: unresolved conflicts remain.",
            )
            .with_detail("Resolve all conflicted paths first."),
        ));
    }
    finish_merge_commit(&repo, "Merge")?;
    Ok("Merge completed.".into())
}

pub fn abort_merge(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    if let Ok(obj) = repo.revparse_single("HEAD") {
        repo.reset(&obj, ResetType::Hard, None)
            .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    }
    let _ = repo.cleanup_state();
    Ok("Merge aborted.".into())
}

pub fn checkout_ours(repo_path: &Path, rel: &str) -> Result<()> {
    checkout_stage(repo_path, rel, 2)
}

pub fn checkout_theirs(repo_path: &Path, rel: &str) -> Result<()> {
    checkout_stage(repo_path, rel, 3)
}

fn checkout_stage(repo_path: &Path, rel: &str, stage: i32) -> Result<()> {
    let rel = rel.trim_start_matches('/');
    if rel.is_empty() || rel.contains("..") {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail("invalid path"),
        ));
    }
    let repo = open_repo(repo_path)?;
    let index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let entry = index
        .get_path(Path::new(rel), stage)
        .ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.")
                    .with_detail(format!("no stage {stage} for {rel}")),
            )
        })?;
    let blob = repo
        .find_blob(entry.id)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let full = repo_path.join(rel);
    if let Some(parent) = full.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail(e.to_string()),
            )
        })?;
    }
    std::fs::write(&full, blob.content()).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail(e.to_string()),
        )
    })?;
    Ok(())
}

pub fn mark_resolved(repo_path: &Path, rel: &str) -> Result<()> {
    let rel = rel.trim_start_matches('/');
    let repo = open_repo(repo_path)?;
    let mut index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    index
        .add_path(Path::new(rel))
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    index
        .write()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
}

pub fn stash_save(repo_path: &Path, include_untracked: bool) -> Result<String> {
    let mut repo = open_repo(repo_path)?;
    let sig = repo.signature().map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-GIT-040",
            "Git user.name / user.email not configured.",
        ))
    })?;
    let mut flags = StashFlags::DEFAULT;
    if include_untracked {
        flags.insert(StashFlags::INCLUDE_UNTRACKED);
    }
    let oid = repo
        .stash_save(&sig, "LabDesk stash", Some(flags))
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-022", "Stash failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    Ok(format!("Stashed {oid}"))
}

pub fn stash_pop(repo_path: &Path) -> Result<String> {
    let mut repo = open_repo(repo_path)?;
    repo.stash_pop(0, None).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-022", "Stash failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok("Stash applied (pop).".into())
}

pub fn rebase_onto_upstream(repo_path: &Path, remote_name: &str) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let head = repo.head().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if !head.is_branch() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail("HEAD is not a branch"),
        ));
    }
    let branch_name = head.shorthand().unwrap_or("HEAD").to_string();
    let local = repo
        .find_branch(&branch_name, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    let upstream = match local.upstream() {
        Ok(up) => up,
        Err(_) => repo
            .find_branch(
                &format!("{remote_name}/{branch_name}"),
                git2::BranchType::Remote,
            )
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                        .with_detail(format!("no upstream: {e}")),
                )
            })?,
    };
    let upstream_commit = upstream
        .get()
        .peel_to_commit()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    let annotated = repo
        .reference_to_annotated_commit(upstream.get())
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    let mut rebase = repo
        .rebase(None, None, Some(&annotated), None)
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                    .with_detail(e.message().to_string()),
            )
        })?;
    let sig = repo.signature().map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-GIT-040",
            "Git user.name / user.email not configured.",
        ))
    })?;
    loop {
        match rebase.next() {
            Some(Ok(_)) => {
                let index = repo.index().map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                            .with_detail(e.message().to_string()),
                    )
                })?;
                if index.has_conflicts() {
                    let paths = list_conflicted_paths(repo_path).unwrap_or_default();
                    return Err(LabDeskError::App(
                        ErrorInfo::new(
                            "LD-GIT-020",
                            "Conflicts detected. Resolve in LabDesk or externally.",
                        )
                        .with_detail(format!("rebase onto {};\n{}", upstream_commit.id(), paths.join("\n"))),
                    ));
                }
                rebase.commit(None, &sig, None).map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                            .with_detail(e.message().to_string()),
                    )
                })?;
            }
            None => break,
            Some(Err(e)) => {
                return Err(LabDeskError::App(
                    ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                        .with_detail(e.message().to_string()),
                ));
            }
        }
    }
    rebase.finish(None).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok("Rebased onto upstream.".into())
}

pub fn abort_rebase(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let mut rebase = repo.open_rebase(None).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    rebase.abort().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok("Rebase aborted.".into())
}

/// Continue an in-progress rebase after conflicts are resolved.
pub fn continue_rebase(repo_path: &Path) -> Result<String> {
    let repo = open_repo(repo_path)?;
    let index = repo.index().map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    if index.has_conflicts() {
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-GIT-023",
                "Could not continue: unresolved conflicts remain.",
            )
            .with_detail("Resolve all conflicted paths first."),
        ));
    }
    let mut rebase = repo.open_rebase(None).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    let sig = repo.signature().map_err(|_| {
        LabDeskError::App(ErrorInfo::new(
            "LD-GIT-040",
            "Git user.name / user.email not configured.",
        ))
    })?;
    // Commit the current step if needed, then continue.
    let _ = rebase.commit(None, &sig, None);
    loop {
        match rebase.next() {
            Some(Ok(_)) => {
                let index = repo.index().map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                            .with_detail(e.message().to_string()),
                    )
                })?;
                if index.has_conflicts() {
                    let paths = list_conflicted_paths(repo_path).unwrap_or_default();
                    return Err(LabDeskError::App(
                        ErrorInfo::new(
                            "LD-GIT-020",
                            "Conflicts detected. Resolve in LabDesk or externally.",
                        )
                        .with_detail(paths.join("\n")),
                    ));
                }
                rebase.commit(None, &sig, None).map_err(|e| {
                    LabDeskError::App(
                        ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                            .with_detail(e.message().to_string()),
                    )
                })?;
            }
            None => break,
            Some(Err(e)) => {
                return Err(LabDeskError::App(
                    ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                        .with_detail(e.message().to_string()),
                ));
            }
        }
    }
    rebase.finish(None).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-GIT-021", "Rebase failed.")
                .with_detail(e.message().to_string()),
        )
    })?;
    Ok("Rebase completed.".into())
}

pub fn discard_path(repo_path: &Path, rel: &str) -> Result<()> {
    let rel = rel.trim_start_matches('/');
    if rel.is_empty() || rel.contains("..") {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-GIT-001", "Git operation failed.").with_detail("invalid path"),
        ));
    }
    let repo = open_repo(repo_path)?;
    let mut opts = CheckoutBuilder::new();
    opts.force().path(rel);
    repo.checkout_head(Some(&mut opts))
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    // Also remove untracked file
    let full = repo_path.join(rel);
    if full.is_file() {
        // If still present and untracked, remove
        let mut status_opts = git2::StatusOptions::new();
        status_opts.pathspec(rel);
        if let Ok(statuses) = repo.statuses(Some(&mut status_opts)) {
            for entry in statuses.iter() {
                if entry.status().is_wt_new() {
                    let _ = std::fs::remove_file(&full);
                }
            }
        }
    }
    Ok(())
}

pub fn delete_local_branch(repo_path: &Path, name: &str) -> Result<()> {
    let name = name.trim();
    let repo = open_repo(repo_path)?;
    let mut branch = repo
        .find_branch(name, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    branch
        .delete()
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
}

pub fn set_upstream(repo_path: &Path, remote_name: &str, branch: &str) -> Result<()> {
    let repo = open_repo(repo_path)?;
    let mut local = repo
        .find_branch(branch, git2::BranchType::Local)
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    local
        .set_upstream(Some(&format!("{remote_name}/{branch}")))
        .map_err(|e| map_git_error(e, "LD-GIT-001", "Git operation failed."))?;
    Ok(())
}
