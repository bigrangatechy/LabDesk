//! Back-compat re-exports — prefer `crate::gitlab` / `crate::forge`.

pub use crate::forge_types::{
    CreatedMergeRequest, GitLabJob, GitLabMergeRequest, GitLabPipeline, GitLabProject, GitLabUser,
    GitLabVersion,
};
pub use crate::gitlab::{
    create_merge_request, get_user, get_version, latest_pipeline, list_membership_projects,
    list_pipeline_jobs, list_project_merge_requests, play_job, remote_branch_exists,
};
