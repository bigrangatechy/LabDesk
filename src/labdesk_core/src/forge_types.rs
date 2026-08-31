//! Forge-neutral DTOs consumed by cache, PyO3, and UI.

use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ForgeKind {
    Gitlab,
    Gitea,
    Forgejo,
    Onedev,
}

impl ForgeKind {
    pub fn parse(s: &str) -> Option<Self> {
        match s.trim().to_ascii_lowercase().as_str() {
            "gitlab" | "" => Some(Self::Gitlab),
            "gitea" => Some(Self::Gitea),
            "forgejo" => Some(Self::Forgejo),
            "onedev" | "one-dev" => Some(Self::Onedev),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Gitlab => "gitlab",
            Self::Gitea => "gitea",
            Self::Forgejo => "forgejo",
            Self::Onedev => "onedev",
        }
    }

    pub fn default_api_version(self) -> &'static str {
        match self {
            Self::Gitlab => "v4",
            Self::Gitea | Self::Forgejo => "v1",
            Self::Onedev => "rest",
        }
    }

    /// Display noun for merge/pull requests in the UI.
    pub fn pull_request_label(self) -> &'static str {
        match self {
            Self::Gitlab => "Merge request",
            Self::Gitea | Self::Forgejo | Self::Onedev => "Pull request",
        }
    }

    pub fn pull_request_label_plural(self) -> &'static str {
        match self {
            Self::Gitlab => "Merge requests",
            Self::Gitea | Self::Forgejo | Self::Onedev => "Pull requests",
        }
    }

    pub fn forge_display_name(self) -> &'static str {
        match self {
            Self::Gitlab => "GitLab",
            Self::Gitea => "Gitea",
            Self::Forgejo => "Forgejo",
            Self::Onedev => "OneDev",
        }
    }

    /// Whether the forge API supports playing a manual CI job.
    pub fn supports_play_job(self) -> bool {
        matches!(self, Self::Gitlab)
    }

    /// Fetch single MR/PR detail (title, description, branches, …).
    pub fn supports_mr_detail(self) -> bool {
        true
    }

    /// Update title / description (and target branch where supported).
    pub fn supports_mr_update(self) -> bool {
        true
    }

    /// Change target branch via API (OneDev has no retarget endpoint in LabDesk).
    pub fn supports_mr_retarget(self) -> bool {
        matches!(self, Self::Gitlab | Self::Gitea | Self::Forgejo)
    }

    /// Merge / accept MR/PR via API.
    pub fn supports_mr_merge(self) -> bool {
        true
    }

    /// List read-only notes/comments on an MR/PR.
    pub fn supports_mr_notes(self) -> bool {
        true
    }

    /// Post a top-level MR/PR note/comment from LabDesk (Slice M).
    pub fn supports_mr_note_create(self) -> bool {
        true
    }

    /// Draft / WIP flag on create.
    pub fn supports_draft_mr(self) -> bool {
        matches!(self, Self::Gitlab | Self::Gitea | Self::Forgejo)
    }

    /// List CI runners / agents (instance and/or project).
    pub fn supports_runners(self) -> bool {
        true
    }

    /// Pause / enable (or disable) a runner via API.
    pub fn supports_runner_pause(self) -> bool {
        matches!(self, Self::Gitlab | Self::Gitea | Self::Forgejo)
    }

    /// Delete a runner via API.
    pub fn supports_runner_delete(self) -> bool {
        matches!(self, Self::Gitlab | Self::Gitea | Self::Forgejo)
    }

    /// List instance users (admin token usually required).
    pub fn supports_admin_users(self) -> bool {
        true
    }

    pub fn ci_tab_label(self) -> &'static str {
        match self {
            Self::Gitlab => "Pipelines",
            Self::Gitea | Self::Forgejo => "Actions",
            Self::Onedev => "Builds",
        }
    }

    pub fn runners_label(self) -> &'static str {
        match self {
            Self::Gitlab | Self::Gitea | Self::Forgejo => "Runners",
            Self::Onedev => "Agents",
        }
    }
}

#[cfg(test)]
mod capability_tests {
    use super::ForgeKind;

    #[test]
    fn gitlab_supports_full_mr_surface_and_play_job() {
        let f = ForgeKind::Gitlab;
        assert!(f.supports_play_job());
        assert!(f.supports_mr_detail());
        assert!(f.supports_mr_update());
        assert!(f.supports_mr_retarget());
        assert!(f.supports_mr_merge());
        assert!(f.supports_mr_notes());
        assert!(f.supports_draft_mr());
        assert!(f.supports_mr_note_create());
        assert!(f.supports_runners());
        assert!(f.supports_runner_pause());
        assert!(f.supports_runner_delete());
        assert!(f.supports_admin_users());
    }

    #[test]
    fn gitea_supports_mr_surface_but_not_play_job() {
        let f = ForgeKind::Gitea;
        assert!(!f.supports_play_job());
        assert!(f.supports_mr_detail());
        assert!(f.supports_mr_update());
        assert!(f.supports_mr_retarget());
        assert!(f.supports_mr_merge());
        assert!(f.supports_mr_notes());
        assert!(f.supports_draft_mr());
        assert!(f.supports_mr_note_create());
        assert!(f.supports_runners());
        assert!(f.supports_runner_pause());
        assert!(f.supports_runner_delete());
        assert!(f.supports_admin_users());
    }

    #[test]
    fn forgejo_matches_gitea_capabilities() {
        let f = ForgeKind::Forgejo;
        assert!(!f.supports_play_job());
        assert!(f.supports_mr_detail());
        assert!(f.supports_mr_update());
        assert!(f.supports_mr_retarget());
        assert!(f.supports_mr_merge());
        assert!(f.supports_mr_notes());
        assert!(f.supports_draft_mr());
        assert!(f.supports_mr_note_create());
        assert!(f.supports_runners());
        assert!(f.supports_runner_pause());
        assert!(f.supports_runner_delete());
    }

    #[test]
    fn onedev_supports_mr_ops_except_draft_and_retarget_and_play() {
        let f = ForgeKind::Onedev;
        assert!(!f.supports_play_job());
        assert!(f.supports_mr_detail());
        assert!(f.supports_mr_update());
        assert!(!f.supports_mr_retarget());
        assert!(f.supports_mr_merge());
        assert!(f.supports_mr_notes());
        assert!(!f.supports_draft_mr());
        assert!(f.supports_mr_note_create());
        assert!(f.supports_runners());
        assert!(!f.supports_runner_pause());
        assert!(!f.supports_runner_delete());
        assert!(f.supports_admin_users());
        assert_eq!(f.runners_label(), "Agents");
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgeUser {
    pub id: u64,
    pub username: String,
    pub name: String,
    pub web_url: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgeVersion {
    pub version: Option<String>,
    pub revision: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgeProject {
    pub id: u64,
    pub name: String,
    pub name_with_namespace: String,
    pub path_with_namespace: String,
    pub http_url_to_repo: Option<String>,
    pub ssh_url_to_repo: Option<String>,
    pub web_url: Option<String>,
    pub default_branch: Option<String>,
    pub visibility: Option<String>,
    pub last_activity_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CreatedPullRequest {
    pub iid: u64,
    pub title: String,
    pub state: Option<String>,
    pub web_url: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgePullRequest {
    pub iid: i64,
    pub title: Option<String>,
    pub state: Option<String>,
    pub web_url: Option<String>,
    pub source_branch: Option<String>,
    pub target_branch: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgePullRequestDetail {
    pub iid: i64,
    pub title: Option<String>,
    pub description: Option<String>,
    pub state: Option<String>,
    pub web_url: Option<String>,
    pub source_branch: Option<String>,
    pub target_branch: Option<String>,
    pub author: Option<String>,
    pub draft: bool,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgeNote {
    pub id: i64,
    pub body: Option<String>,
    pub author: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgePipeline {
    pub id: u64,
    pub status: Option<String>,
    #[serde(rename = "ref")]
    pub ref_: Option<String>,
    pub web_url: Option<String>,
    pub updated_at: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForgeJob {
    pub id: u64,
    pub name: Option<String>,
    pub status: Option<String>,
    pub stage: Option<String>,
    pub when: Option<String>,
    pub web_url: Option<String>,
}

/// CI runner / agent row for Admin + project runners UI (Slice J).
#[derive(Debug, Clone)]
pub struct ForgeRunner {
    pub id: String,
    pub description: Option<String>,
    pub active: bool,
    pub online: Option<bool>,
    pub paused: Option<bool>,
    pub is_shared: Option<bool>,
    pub tag_list: Vec<String>,
    pub runner_type: Option<String>,
    pub web_url: Option<String>,
    pub scope: Option<String>,
}

/// Instance user row for Admin users list (Slice J).
#[derive(Debug, Clone)]
pub struct ForgeAdminUser {
    pub id: u64,
    pub username: String,
    pub name: Option<String>,
    pub email: Option<String>,
    pub is_admin: Option<bool>,
    pub state: Option<String>,
    pub web_url: Option<String>,
}

// Back-compat aliases used across cache / older call sites.
pub type GitLabUser = ForgeUser;
pub type GitLabVersion = ForgeVersion;
pub type GitLabProject = ForgeProject;
pub type CreatedMergeRequest = CreatedPullRequest;
pub type GitLabMergeRequest = ForgePullRequest;
pub type GitLabPipeline = ForgePipeline;
pub type GitLabJob = ForgeJob;
