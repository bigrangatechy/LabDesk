//! Dispatch forge API calls by instance `forge` kind.

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::forge_types::{
    CreatedPullRequest, ForgeJob, ForgeKind, ForgeNote, ForgePipeline, ForgeProject,
    ForgePullRequest, ForgePullRequestDetail, ForgeUser, ForgeVersion,
};
use crate::{forgejo, gitea, gitlab, onedev};

fn unsupported_mr(forge: ForgeKind, code: &'static str, message: &str, feature: &str) -> LabDeskError {
    LabDeskError::App(
        ErrorInfo::new(code, message).with_detail(format!(
            "{} does not support {feature} from LabDesk.",
            forge.forge_display_name()
        )),
    )
}

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
    draft: bool,
) -> Result<CreatedPullRequest> {
    if draft && !forge.supports_draft_mr() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "Draft MRs are not supported on this forge.",
            "draft merge/pull requests",
        ));
    }
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
            draft,
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
            draft,
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
            draft,
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
            draft,
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

pub fn get_merge_request(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    path_hint: Option<&str>,
) -> Result<ForgePullRequestDetail> {
    if !forge.supports_mr_detail() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "MR detail is not supported on this forge.",
            "MR/PR detail",
        ));
    }
    match forge {
        ForgeKind::Gitlab => {
            gitlab::get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid)
        }
        ForgeKind::Gitea => {
            gitea::get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)
        }
        ForgeKind::Forgejo => {
            forgejo::get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)
        }
        ForgeKind::Onedev => {
            onedev::get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)
        }
    }
}

pub fn update_merge_request(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    title: Option<&str>,
    description: Option<&str>,
    target_branch: Option<&str>,
    path_hint: Option<&str>,
) -> Result<ForgePullRequestDetail> {
    if !forge.supports_mr_update() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "Updating MRs is not supported on this forge.",
            "MR/PR metadata update",
        ));
    }
    if target_branch.is_some() && !forge.supports_mr_retarget() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "Changing the target branch is not supported on this forge.",
            "changing MR/PR target branch",
        ));
    }
    match forge {
        ForgeKind::Gitlab => gitlab::update_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            title,
            description,
            target_branch,
        ),
        ForgeKind::Gitea => gitea::update_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            title,
            description,
            target_branch,
            path_hint,
        ),
        ForgeKind::Forgejo => forgejo::update_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            title,
            description,
            target_branch,
            path_hint,
        ),
        ForgeKind::Onedev => onedev::update_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            title,
            description,
            target_branch,
            path_hint,
        ),
    }
}

pub fn merge_merge_request(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    merge_method: Option<&str>,
    path_hint: Option<&str>,
) -> Result<ForgePullRequestDetail> {
    if !forge.supports_mr_merge() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "Merging MRs is not supported on this forge.",
            "MR/PR merge via API",
        ));
    }
    match forge {
        ForgeKind::Gitlab => {
            gitlab::merge_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, merge_method)
        }
        ForgeKind::Gitea => gitea::merge_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            merge_method,
            path_hint,
        ),
        ForgeKind::Forgejo => forgejo::merge_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            merge_method,
            path_hint,
        ),
        ForgeKind::Onedev => onedev::merge_merge_request(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            merge_method,
            path_hint,
        ),
    }
}

pub fn list_merge_request_notes(
    forge: ForgeKind,
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    page: u32,
    path_hint: Option<&str>,
) -> Result<Vec<ForgeNote>> {
    if !forge.supports_mr_notes() {
        return Err(unsupported_mr(
            forge,
            "LD-API-MR-004",
            "MR notes are not supported on this forge.",
            "MR/PR notes",
        ));
    }
    match forge {
        ForgeKind::Gitlab => {
            gitlab::list_merge_request_notes(base_url, pat, ssl_mode, project_id, mr_iid, page)
        }
        ForgeKind::Gitea => gitea::list_merge_request_notes(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            page,
            path_hint,
        ),
        ForgeKind::Forgejo => forgejo::list_merge_request_notes(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            page,
            path_hint,
        ),
        ForgeKind::Onedev => onedev::list_merge_request_notes(
            base_url,
            pat,
            ssl_mode,
            project_id,
            mr_iid,
            page,
            path_hint,
        ),
    }
}

#[cfg(test)]
mod unsupported_feature_tests {
    use super::*;

    #[test]
    fn gitea_play_job_is_rejected_with_job_code() {
        let err = play_job(ForgeKind::Gitea, "http://gitea.lan", "tok", "strict", 1, 9)
            .expect_err("gitea play");
        assert_eq!(err.info().code, "LD-API-JOB-001");
        assert!(err.info().detail.as_deref().unwrap_or("").contains("Gitea"));
    }

    #[test]
    fn forgejo_play_job_is_rejected_with_job_code() {
        let err = play_job(ForgeKind::Forgejo, "http://fj.lan", "tok", "strict", 1, 9)
            .expect_err("forgejo play");
        assert_eq!(err.info().code, "LD-API-JOB-001");
        assert!(err.info().detail.as_deref().unwrap_or("").contains("Forgejo"));
    }

    #[test]
    fn onedev_play_job_is_rejected_with_job_code() {
        let err = play_job(ForgeKind::Onedev, "http://od.lan", "tok", "strict", 1, 9)
            .expect_err("onedev play");
        assert_eq!(err.info().code, "LD-API-JOB-001");
        assert!(err.info().detail.as_deref().unwrap_or("").contains("OneDev"));
    }

    #[test]
    fn onedev_draft_create_is_rejected_with_mr_004() {
        let err = create_merge_request(
            ForgeKind::Onedev,
            "http://od.lan",
            "tok",
            "strict",
            1,
            "feature",
            "main",
            "Title",
            None,
            Some("proj"),
            true,
        )
        .expect_err("onedev draft");
        assert_eq!(err.info().code, "LD-API-MR-004");
    }

    #[test]
    fn onedev_retarget_update_is_rejected_with_mr_004() {
        let err = update_merge_request(
            ForgeKind::Onedev,
            "http://od.lan",
            "tok",
            "strict",
            1,
            3,
            Some("t"),
            None,
            Some("develop"),
            Some("proj"),
        )
        .expect_err("onedev retarget");
        assert_eq!(err.info().code, "LD-API-MR-004");
    }

    #[test]
    fn gitlab_full_mr_capabilities_enabled() {
        assert!(ForgeKind::Gitlab.supports_draft_mr());
        assert!(ForgeKind::Gitlab.supports_play_job());
        assert!(ForgeKind::Gitlab.supports_mr_retarget());
    }
}
