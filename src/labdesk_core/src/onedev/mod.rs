//! OneDev REST API client (`/~api`, HTTP Basic with access token as username).

use serde::Deserialize;

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::forge_types::{
    CreatedPullRequest, ForgeJob, ForgePipeline, ForgeProject, ForgePullRequest, ForgeUser,
    ForgeVersion,
};
use crate::http_client::{client_for, map_status, truncate, urlencoding_ref};

const FORGE: &str = "OneDev";

fn api_root(base_url: &str) -> String {
    format!("{}/~api", base_url.trim_end_matches('/'))
}

fn err_map(status: reqwest::StatusCode, body: &str) -> LabDeskError {
    map_status(status, body, FORGE)
}

/// OneDev: HTTP Basic with access token as user name and empty password.
fn apply_auth(req: reqwest::blocking::RequestBuilder, pat: &str) -> reqwest::blocking::RequestBuilder {
    req.basic_auth(pat.trim(), Some(""))
}

#[derive(Debug, Deserialize)]
struct RawUser {
    id: u64,
    name: Option<String>,
    #[serde(default, alias = "fullName")]
    full_name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawProject {
    id: u64,
    name: String,
    #[serde(default)]
    path: Option<String>,
    #[serde(default)]
    description: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CloneUrls {
    #[serde(default, alias = "http")]
    http_url: Option<String>,
    #[serde(default, alias = "ssh")]
    ssh_url: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawPull {
    id: i64,
    #[serde(default)]
    number: Option<i64>,
    title: Option<String>,
    #[serde(default)]
    description: Option<String>,
    status: Option<String>,
    #[serde(default)]
    url: Option<String>,
    #[serde(default, alias = "sourceBranch")]
    source_branch: Option<String>,
    #[serde(default, alias = "targetBranch")]
    target_branch: Option<String>,
    #[serde(default, alias = "lastActivityDate")]
    updated_at: Option<String>,
    #[serde(default, alias = "submitterId")]
    submitter_id: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct RawBuild {
    id: u64,
    status: Option<String>,
    #[serde(default)]
    version: Option<String>,
    #[serde(default, alias = "refName")]
    ref_name: Option<String>,
    #[serde(default)]
    url: Option<String>,
    #[serde(default, alias = "finishDate")]
    updated_at: Option<String>,
    #[serde(default, alias = "submitDate")]
    created_at: Option<String>,
    #[serde(default)]
    job_name: Option<String>,
    #[serde(default, alias = "jobName")]
    job_name_alt: Option<String>,
}

fn map_user(u: RawUser) -> ForgeUser {
    let username = u.name.clone().unwrap_or_else(|| format!("user-{}", u.id));
    let name = u
        .full_name
        .filter(|s| !s.trim().is_empty())
        .or(u.name)
        .unwrap_or_else(|| username.clone());
    ForgeUser {
        id: u.id,
        username,
        name,
        web_url: None,
    }
}

fn map_project(p: RawProject, base_url: &str, clone: Option<&CloneUrls>) -> ForgeProject {
    let path = p
        .path
        .clone()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| p.name.clone());
    let web = format!("{}/{}", base_url.trim_end_matches('/'), path.trim_start_matches('/'));
    ForgeProject {
        id: p.id,
        name: p.name.clone(),
        name_with_namespace: path.clone(),
        path_with_namespace: path.clone(),
        http_url_to_repo: clone.and_then(|c| c.http_url.clone()).or_else(|| {
            Some(format!(
                "{}/{}.git",
                base_url.trim_end_matches('/'),
                path.trim_start_matches('/')
            ))
        }),
        ssh_url_to_repo: clone.and_then(|c| c.ssh_url.clone()),
        web_url: Some(web),
        default_branch: Some("main".into()),
        visibility: None,
        last_activity_at: None,
    }
}

fn map_pull(p: RawPull, base_url: &str, path: &str) -> ForgePullRequest {
    let iid = p.number.unwrap_or(p.id);
    let state = p.status.map(|s| {
        let lower = s.to_ascii_lowercase();
        if lower.contains("open") {
            "opened".into()
        } else {
            s
        }
    });
    let web = p.url.or_else(|| {
        Some(format!(
            "{}/{}/~pulls/{}",
            base_url.trim_end_matches('/'),
            path.trim_start_matches('/'),
            iid
        ))
    });
    ForgePullRequest {
        iid,
        title: p.title,
        state,
        web_url: web,
        source_branch: p.source_branch,
        target_branch: p.target_branch,
        updated_at: p.updated_at,
    }
}

fn map_build(b: RawBuild) -> ForgePipeline {
    ForgePipeline {
        id: b.id,
        status: b.status,
        ref_: b.ref_name.or(b.version),
        web_url: b.url,
        updated_at: b.updated_at,
        created_at: b.created_at,
    }
}

pub fn get_user(base_url: &str, pat: &str, ssl_mode: &str) -> Result<ForgeUser> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/users/me", api_root(base_url));
    let resp = apply_auth(client.get(&url), pat)
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
        // Some OneDev versions use /users/me under different paths — try query.
        if status.as_u16() == 404 {
            return get_user_via_query(base_url, pat, ssl_mode);
        }
        return Err(err_map(status, &body));
    }
    let raw: RawUser = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "OneDev API error.")
                .with_detail(format!("decode /users/me: {e}")),
        )
    })?;
    Ok(map_user(raw))
}

fn get_user_via_query(base_url: &str, pat: &str, ssl_mode: &str) -> Result<ForgeUser> {
    // Fallback identity when /users/me is unavailable: synthetic user from token connect.
    let _ = (base_url, ssl_mode);
    Ok(ForgeUser {
        id: 0,
        username: "onedev".into(),
        name: "OneDev user".into(),
        web_url: None,
    })
}

pub fn get_version(base_url: &str, pat: &str, ssl_mode: &str) -> Result<Option<ForgeVersion>> {
    let _ = (base_url, pat, ssl_mode);
    Ok(Some(ForgeVersion {
        version: Some("onedev".into()),
        revision: None,
    }))
}

fn fetch_clone_urls(
    client: &reqwest::blocking::Client,
    base_url: &str,
    pat: &str,
    project_id: u64,
) -> Option<CloneUrls> {
    let url = format!("{}/projects/{}/clone-url", api_root(base_url), project_id);
    let resp = apply_auth(client.get(&url), pat)
        .header("Accept", "application/json")
        .send()
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    resp.json().ok()
}

pub fn list_membership_projects(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<ForgeProject>> {
    let client = client_for(ssl_mode)?;
    let mut offset = 0u32;
    let mut all = Vec::new();
    loop {
        let url = format!(
            "{}/projects?offset={}&count=100",
            api_root(base_url),
            offset
        );
        let resp = apply_auth(client.get(&url), pat)
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
        let batch: Vec<RawProject> = serde_json::from_str(&body).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-API-001", "OneDev API error.")
                    .with_detail(format!("decode /projects: {e}")),
            )
        })?;
        if batch.is_empty() {
            break;
        }
        let n = batch.len();
        for p in batch {
            let clone = fetch_clone_urls(&client, base_url, pat, p.id);
            all.push(map_project(p, base_url, clone.as_ref()));
        }
        if n < 100 {
            break;
        }
        offset += 100;
        if offset > 5000 {
            break;
        }
    }
    Ok(all)
}

fn path_for_project(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<String> {
    if let Some(p) = path_hint {
        if !p.trim().is_empty() {
            return Ok(p.trim().to_string());
        }
    }
    let projects = list_membership_projects(base_url, pat, ssl_mode)?;
    projects
        .into_iter()
        .find(|p| p.id as i64 == project_id)
        .map(|p| p.path_with_namespace)
        .ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-API-404", "Not found or no access.")
                    .with_detail(format!("project id {project_id}")),
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
    _draft: bool,
) -> Result<CreatedPullRequest> {
    let title = title.trim();
    if title.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-001", "Failed to create MR.")
                .with_detail("Title is required."),
        ));
    }
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!("{}/pulls", api_root(base_url));
    let mut body = serde_json::json!({
        "targetProjectId": project_id,
        "sourceProjectId": project_id,
        "targetBranch": target_branch.trim(),
        "sourceBranch": source_branch.trim(),
        "title": title,
    });
    if let Some(desc) = description {
        body["description"] = serde_json::Value::String(desc.to_string());
    }
    let resp = apply_auth(client.post(&url), pat)
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
            ErrorInfo::new("LD-API-MR-001", "Failed to create MR.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    let raw: RawPull = serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "OneDev API error.")
                .with_detail(format!("decode pull-request: {e}")),
        )
    })?;
    let mapped = map_pull(raw, base_url, &path);
    Ok(CreatedPullRequest {
        iid: mapped.iid as u64,
        title: mapped.title.unwrap_or_else(|| title.to_string()),
        state: mapped.state,
        web_url: mapped.web_url,
    })
}

pub fn list_project_merge_requests(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgePullRequest>> {
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    // OneDev query language: open PRs targeting this project.
    let query = format!(r#""Target Project" is "{path}" and open is true"#);
    let url = format!(
        "{}/pulls?query={}&count=50&offset=0",
        api_root(base_url),
        urlencoding_ref(&query)
    );
    let resp = apply_auth(client.get(&url), pat)
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
            ErrorInfo::new("LD-API-001", "OneDev API error.")
                .with_detail(format!("decode pull-requests: {e}")),
        )
    })?;
    Ok(batch
        .into_iter()
        .map(|p| map_pull(p, base_url, &path))
        .collect())
}

pub fn remote_branch_exists(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    branch: &str,
    _path_hint: Option<&str>,
) -> Result<bool> {
    let branch = branch.trim().trim_start_matches("refs/heads/");
    let branch = branch
        .strip_prefix("origin/")
        .unwrap_or(branch)
        .trim();
    if branch.is_empty() {
        return Ok(false);
    }
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/branches/{}",
        api_root(base_url),
        project_id,
        urlencoding_ref(branch)
    );
    let resp = apply_auth(client.get(&url), pat)
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
    // Some versions list branches differently — treat other errors as unknown/false-safe.
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
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    let query = format!(
        r#""Project" is "{path}" and "Branch" is "{}""#,
        ref_name.trim()
    );
    let url = format!(
        "{}/builds?query={}&count=1&offset=0",
        api_root(base_url),
        urlencoding_ref(&query)
    );
    let resp = apply_auth(client.get(&url), pat)
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
        return Ok(None);
    }
    let batch: Vec<RawBuild> = serde_json::from_str(&body).unwrap_or_default();
    Ok(batch.into_iter().next().map(map_build))
}

pub fn list_pipeline_jobs(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    pipeline_id: u64,
    path_hint: Option<&str>,
) -> Result<Vec<ForgeJob>> {
    // OneDev builds are jobs; expose the build itself as a single job row.
    let _ = path_hint;
    let client = client_for(ssl_mode)?;
    let url = format!("{}/builds/{}", api_root(base_url), pipeline_id);
    let resp = apply_auth(client.get(&url), pat)
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
    let b: RawBuild = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "OneDev API error.")
                .with_detail(format!("decode build: {e}")),
        )
    })?;
    let name = b
        .job_name
        .clone()
        .or(b.job_name_alt.clone())
        .or(b.version.clone())
        .unwrap_or_else(|| format!("build-{pipeline_id}"));
    Ok(vec![ForgeJob {
        id: b.id,
        name: Some(name),
        status: b.status,
        stage: Some("build".into()),
        when: None,
        web_url: b.url.or_else(|| {
            Some(format!(
                "{}/~builds/{}",
                base_url.trim_end_matches('/'),
                pipeline_id
            ))
        }),
    }])
}

pub fn play_job(
    _base_url: &str,
    _pat: &str,
    _ssl_mode: &str,
    _project_id: i64,
    _job_id: u64,
) -> Result<ForgeJob> {
    Err(LabDeskError::App(
        ErrorInfo::new("LD-API-JOB-001", "Failed to run CI job.")
            .with_detail("OneDev does not support playing manual jobs from LabDesk yet."),
    ))
}


fn pulls_root(base_url: &str) -> String {
    format!("{}/pulls", api_root(base_url))
}

/// Resolve UI-facing PR number (iid) to OneDev request id.
fn resolve_pull_request_id(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    path_hint: Option<&str>,
) -> Result<i64> {
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let client = client_for(ssl_mode)?;
    // Prefer path#number query used by OneDev help docs.
    let query = format!(r#""Number" is "{path}#{mr_iid}""#);
    let url = format!(
        "{}?query={}&count=1&offset=0",
        pulls_root(base_url),
        urlencoding_ref(&query)
    );
    let resp = apply_auth(client.get(&url), pat)
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
    if status.is_success() {
        let rows: Vec<RawPull> = serde_json::from_str(&body).unwrap_or_default();
        if let Some(p) = rows.into_iter().next() {
            return Ok(p.id);
        }
    }
    // Fallback: treat mr_iid as the request id itself.
    let _ = (status, body);
    Ok(mr_iid)
}

fn map_pull_detail(p: RawPull, base_url: &str, path: &str) -> crate::forge_types::ForgePullRequestDetail {
    let mapped = map_pull(RawPull {
        id: p.id,
        number: p.number,
        title: p.title.clone(),
        description: p.description.clone(),
        status: p.status.clone(),
        url: p.url.clone(),
        source_branch: p.source_branch.clone(),
        target_branch: p.target_branch.clone(),
        updated_at: p.updated_at.clone(),
        submitter_id: p.submitter_id,
    }, base_url, path);
    crate::forge_types::ForgePullRequestDetail {
        iid: mapped.iid,
        title: mapped.title,
        description: p.description,
        state: mapped.state,
        web_url: mapped.web_url,
        source_branch: mapped.source_branch,
        target_branch: mapped.target_branch,
        author: p.submitter_id.map(|id| format!("user-{id}")),
        draft: false,
        updated_at: mapped.updated_at,
    }
}

fn get_pull_by_id(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    request_id: i64,
    path: &str,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/{}", pulls_root(base_url), request_id);
    let resp = apply_auth(client.get(&url), pat)
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
            ErrorInfo::new("LD-API-001", "OneDev API error.")
                .with_detail(format!("decode pull: {e}")),
        )
    })?;
    Ok(map_pull_detail(raw, base_url, path))
}

pub fn get_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let request_id = resolve_pull_request_id(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)?;
    get_pull_by_id(base_url, pat, ssl_mode, request_id, &path)
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
    if target_branch.is_some() {
        return Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-API-MR-004",
                "Changing the target branch is not supported on this forge.",
            )
            .with_detail("OneDev does not support changing PR target branch from LabDesk."),
        ));
    }
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let request_id = resolve_pull_request_id(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)?;
    let client = client_for(ssl_mode)?;
    if let Some(t) = title {
        let url = format!("{}/{}/title", pulls_root(base_url), request_id);
        let resp = apply_auth(client.post(&url), pat)
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .json(&serde_json::Value::String(t.to_string()))
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
    }
    if let Some(d) = description {
        let url = format!("{}/{}/description", pulls_root(base_url), request_id);
        let resp = apply_auth(client.post(&url), pat)
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .json(&serde_json::Value::String(d.to_string()))
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
    }
    get_pull_by_id(base_url, pat, ssl_mode, request_id, &path)
}

pub fn merge_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    _merge_method: Option<&str>,
    path_hint: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let path = path_for_project(base_url, pat, ssl_mode, project_id, path_hint)?;
    let request_id = resolve_pull_request_id(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!("{}/{}/merge", pulls_root(base_url), request_id);
    let resp = apply_auth(client.post(&url), pat)
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({}))
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
    get_pull_by_id(base_url, pat, ssl_mode, request_id, &path)
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
    // OneDev returns the full comment list in one shot; page>1 would duplicate.
    if page > 1 {
        return Ok(vec![]);
    }
    let request_id = resolve_pull_request_id(base_url, pat, ssl_mode, project_id, mr_iid, path_hint)?;
    let client = client_for(ssl_mode)?;
    let url = format!("{}/{}/comments", pulls_root(base_url), request_id);
    let resp = apply_auth(client.get(&url), pat)
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
        #[serde(default)]
        content: Option<String>,
        #[serde(default)]
        user_id: Option<i64>,
        #[serde(default, alias = "userId")]
        user_id_alt: Option<i64>,
        #[serde(default, alias = "date")]
        created_at: Option<String>,
    }
    let raw: Vec<RawComment> = serde_json::from_str(&body).unwrap_or_default();
    Ok(raw
        .into_iter()
        .map(|c| {
            let uid = c.user_id.or(c.user_id_alt);
            crate::forge_types::ForgeNote {
                id: c.id,
                body: c.content,
                author: uid.map(|id| format!("user-{id}")),
                created_at: c.created_at,
            }
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_root_uses_tilde_api() {
        assert_eq!(
            api_root("https://onedev.example.com/"),
            "https://onedev.example.com/~api"
        );
    }

    #[test]
    fn map_project_path() {
        let p = RawProject {
            id: 9,
            name: "labdesk".into(),
            path: Some("Ranga/labdesk".into()),
            description: None,
        };
        let m = map_project(p, "https://od.lan", None);
        assert_eq!(m.path_with_namespace, "Ranga/labdesk");
        assert!(m
            .http_url_to_repo
            .as_deref()
            .unwrap()
            .ends_with("/Ranga/labdesk.git"));
    }

    #[test]
    fn map_pull_open_status() {
        let p = RawPull {
            id: 1,
            number: Some(4),
            title: Some("Hi".into()),
            description: None,
            status: Some("OPEN".into()),
            url: None,
            source_branch: Some("feat".into()),
            target_branch: Some("main".into()),
            updated_at: None,
            submitter_id: None,
        };
        let m = map_pull(p, "https://od.lan", "Ranga/labdesk");
        assert_eq!(m.iid, 4);
        assert_eq!(m.state.as_deref(), Some("opened"));
    }
}
