//! Dispatch forge API calls by instance `forge` kind.

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::forge_types::{
    CreatedPullRequest, ForgeJob, ForgeKind, ForgePipeline, ForgeProject, ForgePullRequest,
    ForgeUser, ForgeVersion,
};
use crate::{forgejo, gitea, gitlab, onedev};

pub fn get_user(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<ForgeUser> {
    match forge {
        ForgeKind::Gitlab => gitlab::get_user(base_url, pat, ssl_mode),
        ForgeKind::Gitea => gitea::get_user(base_url, pat, ssl_mode),
        ForgeKind::Forgejo => forgejo::get_user(base_url, pat, ssl_mode),
        ForgeKind::Onedev => onedev::get_user(base_url, pat, ssl_mode),
    }
}

pub fn get_version(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Option<ForgeVersion>> {
    match forge {
        ForgeKind::Gitlab => gitlab::get_version(base_url, pat, ssl_mode),
        ForgeKind::Gitea => gitea::get_version(base_url, pat, ssl_mode),
        ForgeKind::Forgejo => forgejo::get_version(base_url, pat, ssl_mode),
        ForgeKind::Onedev => onedev::get_version(base_url, pat, ssl_mode),
    }
}

pub fn list_membership_projects(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<ForgeProject>> {
    match forge {
        ForgeKind::Gitlab => gitlab::list_membership_projects(base_url, pat, ssl_mode),
        ForgeKind::Gitea => gitea::list_membership_projects(base_url, pat, ssl_mode),
        ForgeKind::Forgejo => forgejo::list_membership_projects(base_url, pat, ssl_mode),
        ForgeKind::Onedev => onedev::list_membership_projects(base_url, pat, ssl_mode),
    }
}

pub fn create_merge_request(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    source_branch: &str,
    target_branch: &str,
    title: &str,
    description: Option<&str>,
    path_hint: Option<&str>,
) -> Result<CreatedPullRequest> {
    match forge {
        ForgeKind::Gitlab => gitlab::create_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            source_branch,
            target_branch,
            title,
            description,
        ),
        ForgeKind::Gitea => gitea::create_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            source_branch,
            target_branch,
            title,
            description,
            path_hint,
        ),
        ForgeKind::Forgejo => forgejo::create_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            source_branch,
            target_branch,
            title,
            description,
            path_hint,
        ),
        ForgeKind::Onedev => onedev::create_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            source_branch,
            target_branch,
            title,
            description,
            path_hint,
        ),
    }
}

pub fn list_project_merge_requests(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgePullRequest>> {
    match forge {
        ForgeKind::Gitlab => {
            gitlab::list_project_merge_requests(base_url, pat, ssl_mode, project_id)
        }
        ForgeKind::Gitea => {
            gitea::list_project_merge_requests(base_url, pat, ssl_mode, project_id, path_hint)
        }
        ForgeKind::Forgejo => {
            forgejo::list_project_merge_requests(base_url, pat, ssl_mode, project_id, path_hint)
        }
        ForgeKind::Onedev => {
            onedev::list_project_merge_requests(base_url, pat, ssl_mode, project_id, path_hint)
        }
    }
}

pub fn remote_branch_exists(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    branch: &str,
    path_hint: Option<&str>,
) -> Result<bool> {
    match forge {
        ForgeKind::Gitlab => {
            gitlab::remote_branch_exists(base_url, pat, ssl_mode, project_id, branch)
        }
        ForgeKind::Gitea => {
            gitea::remote_branch_exists(base_url, pat, ssl_mode, project_id, branch, path_hint)
        }
        ForgeKind::Forgejo => {
            forgejo::remote_branch_exists(base_url, pat, ssl_mode, project_id, branch, path_hint)
        }
        ForgeKind::Onedev => {
            onedev::remote_branch_exists(base_url, pat, ssl_mode, project_id, branch, path_hint)
        }
    }
}

pub fn latest_pipeline(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    ref_name: &str,
    path_hint: Option<&str>,
) -> Result<Option<ForgePipeline>> {
    match forge {
        ForgeKind::Gitlab => {
            gitlab::latest_pipeline(base_url, pat, ssl_mode, project_id, ref_name)
        }
        ForgeKind::Gitea => {
            gitea::latest_pipeline(base_url, pat, ssl_mode, project_id, ref_name, path_hint)
        }
        ForgeKind::Forgejo => {
            forgejo::latest_pipeline(base_url, pat, ssl_mode, project_id, ref_name, path_hint)
        }
        ForgeKind::Onedev => {
            onedev::latest_pipeline(base_url, pat, ssl_mode, project_id, ref_name, path_hint)
        }
    }
}

pub fn list_pipeline_jobs(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    pipeline_id: u64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgeJob>> {
    match forge {
        ForgeKind::Gitlab => {
            gitlab::list_pipeline_jobs(base_url, pat, ssl_mode, project_id, pipeline_id)
        }
        ForgeKind::Gitea => gitea::list_pipeline_jobs(
            base_url,
            pat,
            ssl_mode,
            project_id,
            pipeline_id,
            path_hint,
        ),
        ForgeKind::Forgejo => forgejo::list_pipeline_jobs(
            base_url,
            pat,
            ssl_mode,
            project_id,
            pipeline_id,
            path_hint,
        ),
        ForgeKind::Onedev => onedev::list_pipeline_jobs(
            base_url,
            pat,
            ssl_mode,
            project_id,
            pipeline_id,
            path_hint,
        ),
    }
}

pub fn play_job(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    job_id: u64,
) -> Result<ForgeJob> {
    if !forge.supports_play_job() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-JOB-001", "Failed to run CI job.").with_detail(format!(
                "{} does not support playing manual CI jobs from LabDesk.",
                forge.forge_display_name()
            )),
        ));
    }
    match forge {
        ForgeKind::Gitlab => gitlab::play_job(base_url, pat, ssl_mode, project_id, job_id),
        ForgeKind::Gitea => gitea::play_job(base_url, pat, ssl_mode, project_id, job_id),
        ForgeKind::Forgejo => forgejo::play_job(base_url, pat, ssl_mode, project_id, job_id),
        ForgeKind::Onedev => onedev::play_job(base_url, pat, ssl_mode, project_id, job_id),
    }
}
