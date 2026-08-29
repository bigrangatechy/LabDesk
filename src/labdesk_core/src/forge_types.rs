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

    pub fn ci_tab_label(self) -> &'static str {
        match self {
            Self::Gitlab => "Pipelines",
            Self::Gitea | Self::Forgejo => "Actions",
            Self::Onedev => "Builds",
        }
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

// Back-compat aliases used across cache / older call sites.
pub type GitLabUser = ForgeUser;
pub type GitLabVersion = ForgeVersion;
pub type GitLabProject = ForgeProject;
pub type CreatedMergeRequest = CreatedPullRequest;
pub type GitLabMergeRequest = ForgePullRequest;
pub type GitLabPipeline = ForgePipeline;
pub type GitLabJob = ForgeJob;
