//! Gitea REST API v1 client (`Authorization: token …`).

use serde::Deserialize;

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::forge_types::{
    CreatedPullRequest, ForgeJob, ForgePipeline, ForgeProject, ForgePullRequest, ForgeUser,
    ForgeVersion,
};
use crate::http_client::{
    client_for, map_status, split_owner_repo, truncate, urlencoding_ref,
};

const FORGE: &str = "Gitea";

fn api_root(base_url: &str) -> String {
    format!("{}/api/v1", base_url.trim_end_matches('/'))
}

fn auth_header(pat: &str) -> String {
    format!("token {}", pat.trim())
}

fn err_map(status: reqwest::StatusCode, body: &str) -> LabDeskError {
    map_status(status, body, FORGE)
}

#[derive(Debug, Deserialize)]
struct RawUser {
    id: u64,
    login: String,
    #[serde(default)]
    full_name: String,
    html_url: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawRepo {
    id: u64,
    name: String,
    full_name: String,
    clone_url: Option<String>,
    ssh_url: Option<String>,
    html_url: Option<String>,
    default_branch: Option<String>,
    #[serde(default)]
    private: bool,
    updated_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawPull {
    number: i64,
    title: Option<String>,
    #[serde(default)]
    body: Option<String>,
    state: Option<String>,
    html_url: Option<String>,
    updated_at: Option<String>,
    #[serde(default)]
    draft: Option<bool>,
    user: Option<RawUser>,
    head: Option<RawRef>,
    base: Option<RawRef>,
}

#[derive(Debug, Deserialize)]
struct RawRef {
    #[serde(default)]
    label: String,
    #[serde(default)]
    r#ref: String,
}

#[derive(Debug, Clone, Deserialize)]
struct RawRun {
    id: u64,
    status: Option<String>,
    #[serde(default)]
    conclusion: Option<String>,
    html_url: Option<String>,
    updated_at: Option<String>,
    created_at: Option<String>,
    #[serde(default)]
    head_branch: Option<String>,
    #[serde(default)]
    event: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawRunsResponse {
    #[serde(default)]
    workflow_runs: Vec<RawRun>,
}

#[derive(Debug, Deserialize)]
struct RawJob {
    id: u64,
    name: Option<String>,
    status: Option<String>,
    conclusion: Option<String>,
    html_url: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawJobsResponse {
    #[serde(default)]
    jobs: Vec<RawJob>,
}

fn map_user(u: RawUser) -> ForgeUser {
    let name = if u.full_name.trim().is_empty() {
        u.login.clone()
    } else {
        u.full_name
    };
    ForgeUser {
        id: u.id,
        username: u.login,
        name,
        web_url: u.html_url,
    }
}

fn map_repo(r: RawRepo) -> ForgeProject {
    ForgeProject {
        id: r.id,
        name: r.name,
        name_with_namespace: r.full_name.clone(),
        path_with_namespace: r.full_name,
        http_url_to_repo: r.clone_url,
        ssh_url_to_repo: r.ssh_url,
        web_url: r.html_url,
        default_branch: r.default_branch,
        visibility: Some(if r.private {
            "private".into()
        } else {
            "public".into()
        }),
        last_activity_at: r.updated_at,
    }
}

fn branch_from_ref(r: &Option<RawRef>) -> Option<String> {
    let Some(r) = r else {
        return None;
    };
    if !r.r#ref.is_empty() {
        return Some(r.r#ref.clone());
    }
    if !r.label.is_empty() {
        // label may be "owner:branch"
        if let Some((_, b)) = r.label.split_once(':') {
            return Some(b.to_string());
        }
        return Some(r.label.clone());
    }
    None
}

fn map_pull(p: RawPull) -> ForgePullRequest {
    let state = p.state.map(|s| {
        if s.eq_ignore_ascii_case("open") {
            "opened".into()
        } else {
            s
        }
    });
    ForgePullRequest {
        iid: p.number,
        title: p.title,
        state,
        web_url: p.html_url,
        source_branch: branch_from_ref(&p.head),
        target_branch: branch_from_ref(&p.base),
        updated_at: p.updated_at,
    }
}

fn map_run(r: RawRun) -> ForgePipeline {
    let status = r
        .conclusion
        .filter(|c| !c.is_empty() && c != "null")
        .or(r.status);
    ForgePipeline {
        id: r.id,
        status,
        ref_: r.head_branch.or(r.event),
        web_url: r.html_url,
        updated_at: r.updated_at,
        created_at: r.created_at,
    }
}

fn map_job(j: RawJob) -> ForgeJob {
    let status = j
        .conclusion
        .filter(|c| !c.is_empty() && c != "null")
        .or(j.status);
    ForgeJob {
        id: j.id,
        name: j.name,
        status,
        stage: None,
        when: None,
        web_url: j.html_url,
    }
}

pub fn get_user(base_url: &str, pat: &str, ssl_mode: &str) -> Result<ForgeUser> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/user", api_root(base_url));
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    let raw: RawUser = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode /user: {e}")),
        )
    })?;
    Ok(map_user(raw))
}

pub fn get_version(base_url: &str, pat: &str, ssl_mode: &str) -> Result<Option<ForgeVersion>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/version", api_root(base_url));
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    if !status.is_success() {
        return Ok(None);
    }
    let body = resp.text().unwrap_or_default();
    #[derive(Deserialize)]
    struct Ver {
        version: Option<String>,
    }
    let v: Ver = serde_json::from_str(&body).unwrap_or(Ver { version: None });
    Ok(Some(ForgeVersion {
        version: v.version,
        revision: None,
    }))
}

pub fn list_membership_projects(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<ForgeProject>> {
    let client = client_for(ssl_mode)?;
    let mut page = 1u32;
    let mut all = Vec::new();
    loop {
        let url = format!(
            "{}/user/repos?limit=50&page={}&sort=updated",
            api_root(base_url),
            page
        );
        let resp = client
            .get(&url)
            .header("Authorization", auth_header(pat))
            .header("Accept", "application/json")
            .send()
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                        .with_detail(e.to_string()),
                )
            })?;
        let status = resp.status();
        let body = resp.text().unwrap_or_default();
        if !status.is_success() {
            return Err(err_map(status, &body));
        }
        let batch: Vec<RawRepo> = serde_json::from_str(&body).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-API-001", "Gitea API error.")
                    .with_detail(format!("decode /user/repos: {e}")),
            )
        })?;
        if batch.is_empty() {
            break;
        }
        let n = batch.len();
        all.extend(batch.into_iter().map(map_repo));
        if n < 50 {
            break;
        }
        page += 1;
        if page > 100 {
            break;
        }
    }
    Ok(all)
}

fn resolve_owner_repo(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<(String, String)> {
    if let Some(p) = path_hint {
        if let Some(pair) = split_owner_repo(p) {
            return Ok(pair);
        }
    }
    // Fallback: scan membership list (small self-hosted instances).
    let projects = list_membership_projects(base_url, pat, ssl_mode)?;
    let proj = projects
        .into_iter()
        .find(|p| p.id as i64 == project_id)
        .ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-API-404", "Not found or no access.")
                    .with_detail(format!("repo id {project_id}")),
            )
        })?;
    split_owner_repo(&proj.path_with_namespace).ok_or_else(|| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail("invalid path_with_namespace"),
        )
    })
}

pub fn create_merge_request(
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
    let title = title.trim();
    if title.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-001", "Failed to create MR.")
                .with_detail("Title is required."),
        ));
    }
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!("{}/repos/{}/{}/pulls", api_root(base_url), owner, repo);
    let mut body = serde_json::json!({
        "head": source_branch.trim(),
        "base": target_branch.trim(),
        "title": title,
    });
    if draft {
        body["draft"] = serde_json::Value::Bool(true);
    }
    if let Some(desc) = description {
        body["body"] = serde_json::Value::String(desc.to_string());
    }
    let resp = client
        .post(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let text = resp.text().unwrap_or_default();
    if !status.is_success() {
        if status.as_u16() == 422 {
            return Err(LabDeskError::App(
                ErrorInfo::new("LD-API-MR-001", "Failed to create MR.")
                    .with_detail(truncate(&text, 200)),
            ));
        }
        return Err(err_map(status, &text));
    }
    let raw: RawPull = serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode pull: {e}")),
        )
    })?;
    Ok(CreatedPullRequest {
        iid: raw.number as u64,
        title: raw.title.unwrap_or_else(|| title.to_string()),
        state: raw.state,
        web_url: raw.html_url,
    })
}

pub fn list_project_merge_requests(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgePullRequest>> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/pulls?state=open&limit=50",
        api_root(base_url),
        owner,
        repo
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    let batch: Vec<RawPull> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode pulls: {e}")),
        )
    })?;
    Ok(batch.into_iter().map(map_pull).collect())
}

pub fn remote_branch_exists(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    branch: &str,
    path_hint: Option<&str>,
) -> Result<bool> {
    let branch = branch.trim().trim_start_matches("refs/heads/");
    let branch = branch
        .strip_prefix("origin/")
        .unwrap_or(branch)
        .trim();
    if branch.is_empty() {
        return Ok(false);
    }
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/branches/{}",
        api_root(base_url),
        owner,
        repo,
        urlencoding_ref(branch)
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    if status.as_u16() == 200 {
        return Ok(true);
    }
    if status.as_u16() == 404 {
        return Ok(false);
    }
    let body = resp.text().unwrap_or_default();
    Err(err_map(status, &body))
}

pub fn latest_pipeline(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    ref_name: &str,
    path_hint: Option<&str>,
) -> Result<Option<ForgePipeline>> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/actions/runs?limit=20",
        api_root(base_url),
        owner,
        repo
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if status.as_u16() == 404 {
        return Ok(None);
    }
    if !status.is_success() {
        // Actions may be disabled — treat as no pipeline rather than hard fail for list icons.
        return Ok(None);
    }
    let parsed: RawRunsResponse = serde_json::from_str(&body).unwrap_or(RawRunsResponse {
        workflow_runs: Vec::new(),
    });
    let ref_name = ref_name.trim();
    let run = parsed
        .workflow_runs
        .iter()
        .find(|r| {
            r.head_branch
                .as_deref()
                .map(|b| b == ref_name)
                .unwrap_or(false)
        })
        .cloned()
        .or_else(|| parsed.workflow_runs.into_iter().next());
    Ok(run.map(map_run))
}

pub fn list_pipeline_jobs(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    pipeline_id: u64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgeJob>> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/actions/runs/{}/jobs",
        api_root(base_url),
        owner,
        repo,
        pipeline_id
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if status.as_u16() == 404 {
        return Ok(Vec::new());
    }
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    let parsed: RawJobsResponse = serde_json::from_str(&body).unwrap_or(RawJobsResponse {
        jobs: Vec::new(),
    });
    Ok(parsed.jobs.into_iter().map(map_job).collect())
}

pub fn play_job(
    _base_url: &str,
    _pat: &str,
    _ssl_mode: &str,
    _project_id: i64,
    _job_id: u64,
) -> Result<ForgeJob> {
    Err(LabDeskError::App(
        ErrorInfo::new("LD-API-JOB-001", "Failed to run CI job.").with_detail(
            "Gitea Actions does not support playing manual jobs from LabDesk.",
        ),
    ))
}

fn map_pull_detail(p: RawPull) -> crate::forge_types::ForgePullRequestDetail {
    let state = p.state.map(|s| {
        if s.eq_ignore_ascii_case("open") {
            "opened".into()
        } else {
            s
        }
    });
    crate::forge_types::ForgePullRequestDetail {
        iid: p.number,
        title: p.title,
        description: p.body,
        state,
        web_url: p.html_url,
        source_branch: branch_from_ref(&p.head),
        target_branch: branch_from_ref(&p.base),
        author: p.user.map(|u| u.login),
        draft: p.draft.unwrap_or(false),
        updated_at: p.updated_at,
    }
}

pub fn get_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/pulls/{}",
        api_root(base_url),
        owner,
        repo,
        mr_iid
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    let raw: RawPull = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode pull: {e}")),
        )
    })?;
    Ok(map_pull_detail(raw))
}

pub fn update_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    title: Option<&str>,
    description: Option<&str>,
    target_branch: Option<&str>,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/pulls/{}",
        api_root(base_url),
        owner,
        repo,
        mr_iid
    );
    let mut body = serde_json::Map::new();
    if let Some(t) = title {
        body.insert("title".into(), serde_json::Value::String(t.to_string()));
    }
    if let Some(d) = description {
        body.insert("body".into(), serde_json::Value::String(d.to_string()));
    }
    if let Some(t) = target_branch {
        body.insert("base".into(), serde_json::Value::String(t.to_string()));
    }
    let resp = client
        .patch(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let text = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-002", "Failed to update MR.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)
}

pub fn merge_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    merge_method: Option<&str>,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/repos/{}/{}/pulls/{}/merge",
        api_root(base_url),
        owner,
        repo,
        mr_iid
    );
    let style = match merge_method.map(|s| s.to_ascii_lowercase()).as_deref() {
        Some("squash") => "squash",
        Some("rebase") => "rebase",
        _ => "merge",
    };
    let body = serde_json::json!({ "Do": style });
    let resp = client
        .post(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let text = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-003", "Failed to merge MR.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)
}

pub fn list_merge_request_notes(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    page: u32,
    path_hint: Option<&str>,
) -> Result<Vec<crate::forge_types::ForgeNote>> {
    // Gitea returns the full comment list in one shot; page>1 would duplicate.
    if page > 1 {
        return Ok(vec![]);
    }
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    // Gitea PR comments share the issue comments endpoint.
    let url = format!(
        "{}/repos/{}/{}/issues/{}/comments",
        api_root(base_url),
        owner,
        repo,
        mr_iid
    );
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    #[derive(Deserialize)]
    struct RawComment {
        id: i64,
        body: Option<String>,
        created_at: Option<String>,
        user: Option<RawUser>,
    }
    let raw: Vec<RawComment> = serde_json::from_str(&body).unwrap_or_default();
    Ok(raw
        .into_iter()
        .map(|c| crate::forge_types::ForgeNote {
            id: c.id,
            body: c.body,
            author: c.user.map(|u| u.login),
            created_at: c.created_at,
        })
        .collect())
}

// --- Slice J: runners + admin users ---

#[derive(Debug, Deserialize)]
struct RawRunnerLabel {
    #[serde(default)]
    name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawActionRunner {
    id: i64,
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    busy: Option<bool>,
    #[serde(default)]
    disabled: Option<bool>,
    #[serde(default)]
    labels: Vec<RawRunnerLabel>,
}

#[derive(Debug, Deserialize)]
struct RawRunnersResponse {
    /// Prefer `runners`; some builds expose the list as `entries`.
    #[serde(default, alias = "entries")]
    runners: Vec<RawActionRunner>,
}

fn map_action_runner(
    r: RawActionRunner,
    base_url: &str,
    scope: &str,
) -> crate::forge_types::ForgeRunner {
    let disabled = r.disabled.unwrap_or(false);
    let online = r
        .status
        .as_deref()
        .map(|s| s.to_ascii_lowercase().contains("online"));
    let tag_list: Vec<String> = r
        .labels
        .into_iter()
        .filter_map(|l| l.name.filter(|n| !n.is_empty()))
        .collect();
    let _ = r.busy;
    crate::forge_types::ForgeRunner {
        id: r.id.to_string(),
        description: r.name,
        active: !disabled,
        online,
        paused: Some(disabled),
        is_shared: None,
        tag_list,
        runner_type: None,
        web_url: Some(format!(
            "{}/admin/actions/runners",
            base_url.trim_end_matches('/')
        )),
        scope: Some(scope.into()),
    }
}

fn decode_action_runners(body: &str) -> Result<Vec<RawActionRunner>> {
    if let Ok(wrap) = serde_json::from_str::<RawRunnersResponse>(body) {
        return Ok(wrap.runners);
    }
    serde_json::from_str(body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode runners: {e}")),
        )
    })
}

fn fetch_action_runners(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    path_and_query: &str,
) -> Result<Vec<RawActionRunner>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}{}", api_root(base_url), path_and_query);
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    decode_action_runners(&body)
}

fn runner_url(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    runner_id: &str,
    project_id: Option<i64>,
    path_hint: Option<&str>,
) -> Result<String> {
    if let Some(pid) = project_id {
        let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, pid, path_hint)?;
        Ok(format!(
            "{}/repos/{}/{}/actions/runners/{}",
            api_root(base_url),
            owner,
            repo,
            urlencoding_ref(runner_id)
        ))
    } else {
        Ok(format!(
            "{}/admin/actions/runners/{}",
            api_root(base_url),
            urlencoding_ref(runner_id)
        ))
    }
}

pub fn list_instance_runners(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<crate::forge_types::ForgeRunner>> {
    let raw = fetch_action_runners(base_url, pat, ssl_mode, "/admin/actions/runners")?;
    Ok(raw
        .into_iter()
        .map(|r| map_action_runner(r, base_url, "instance"))
        .collect())
}

pub fn list_project_runners(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<Vec<crate::forge_types::ForgeRunner>> {
    let (owner, repo) = resolve_owner_repo(base_url, pat, ssl_mode, project_id, path_hint)?;
    let path = format!("/repos/{owner}/{repo}/actions/runners");
    let raw = fetch_action_runners(base_url, pat, ssl_mode, &path)?;
    Ok(raw
        .into_iter()
        .map(|r| map_action_runner(r, base_url, "project"))
        .collect())
}

pub fn set_runner_paused(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    runner_id: &str,
    paused: bool,
    project_id: Option<i64>,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgeRunner> {
    let client = client_for(ssl_mode)?;
    let url = runner_url(base_url, pat, ssl_mode, runner_id, project_id, path_hint)?;
    let body = serde_json::json!({ "disabled": paused });
    let scope = if project_id.is_some() {
        "project"
    } else {
        "instance"
    };
    let resp = client
        .patch(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let text = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-RUN-001", "Failed to update runner.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    let raw: RawActionRunner = serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode runner: {e}")),
        )
    })?;
    Ok(map_action_runner(raw, base_url, scope))
}

pub fn delete_runner(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    runner_id: &str,
    project_id: Option<i64>,
    path_hint: Option<&str>,
) -> Result<()> {
    let client = client_for(ssl_mode)?;
    let url = runner_url(base_url, pat, ssl_mode, runner_id, project_id, path_hint)?;
    let resp = client
        .delete(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let text = resp.text().unwrap_or_default();
    if !status.is_success() && status.as_u16() != 204 {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-RUN-001", "Failed to delete runner.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
struct RawAdminUser {
    id: u64,
    #[serde(default)]
    login: Option<String>,
    #[serde(default)]
    username: Option<String>,
    #[serde(default)]
    full_name: Option<String>,
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    is_admin: Option<bool>,
    #[serde(default)]
    active: Option<bool>,
    #[serde(default)]
    html_url: Option<String>,
}

pub fn list_admin_users(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<crate::forge_types::ForgeAdminUser>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/admin/users?limit=100", api_root(base_url));
    let resp = client
        .get(&url)
        .header("Authorization", auth_header(pat))
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;
    let status = resp.status();
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Err(err_map(status, &body));
    }
    let raw: Vec<RawAdminUser> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "Gitea API error.")
                .with_detail(format!("decode users: {e}")),
        )
    })?;
    Ok(raw
        .into_iter()
        .map(|u| {
            let username = u
                .login
                .or(u.username)
                .unwrap_or_else(|| format!("user-{}", u.id));
            let name = u
                .full_name
                .filter(|s| !s.trim().is_empty())
                .or(u.name.filter(|s| !s.trim().is_empty()));
            let state = u.active.map(|a| {
                if a {
                    "active".into()
                } else {
                    "inactive".into()
                }
            });
            crate::forge_types::ForgeAdminUser {
                id: u.id,
                username,
                name,
                email: u.email,
                is_admin: u.is_admin,
                state,
                web_url: u.html_url,
            }
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn map_repo_fixture() {
        let raw = r#"{
            "id": 7,
            "name": "labdesk",
            "full_name": "Ranga/labdesk",
            "clone_url": "https://git.lan/Ranga/labdesk.git",
            "ssh_url": "git@git.lan:Ranga/labdesk.git",
            "html_url": "https://git.lan/Ranga/labdesk",
            "default_branch": "main",
            "private": true,
            "updated_at": "2026-08-30T00:00:00Z"
        }"#;
        let r: RawRepo = serde_json::from_str(raw).unwrap();
        let p = map_repo(r);
        assert_eq!(p.path_with_namespace, "Ranga/labdesk");
        assert_eq!(p.visibility.as_deref(), Some("private"));
    }

    #[test]
    fn map_pull_open_to_opened() {
        let raw = r#"{
            "number": 3,
            "title": "Ship",
            "state": "open",
            "html_url": "https://git.lan/Ranga/labdesk/pulls/3",
            "updated_at": "2026-08-30T00:00:00Z",
            "head": {"ref": "feature", "label": "Ranga:feature"},
            "base": {"ref": "main", "label": "Ranga:main"}
        }"#;
        let p: RawPull = serde_json::from_str(raw).unwrap();
        let m = map_pull(p);
        assert_eq!(m.iid, 3);
        assert_eq!(m.state.as_deref(), Some("opened"));
        assert_eq!(m.source_branch.as_deref(), Some("feature"));
    }

    #[test]
    fn auth_header_format() {
        assert_eq!(auth_header("abc"), "token abc");
    }

    #[test]
    fn api_root_v1() {
        assert_eq!(api_root("http://192.168.0.5:3000/"), "http://192.168.0.5:3000/api/v1");
    }
}
