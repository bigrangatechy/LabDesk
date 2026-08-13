//! GitLab REST API v4 client (PRIVATE-TOKEN).

use serde::Deserialize;

use crate::error::{ErrorInfo, LabDeskError, Result};

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabUser {
    pub id: u64,
    pub username: String,
    pub name: String,
    pub web_url: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabVersion {
    pub version: Option<String>,
    pub revision: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabProject {
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

fn api_root(base_url: &str) -> String {
    format!("{}/api/v4", base_url.trim_end_matches('/'))
}

fn labdesk_user_agent() -> String {
    let ver = option_env!("LABDESK_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"));
    format!("LabDesk/{ver}")
}

fn client_for(ssl_mode: &str) -> Result<reqwest::blocking::Client> {
    let mut b = reqwest::blocking::Client::builder()
        .user_agent(labdesk_user_agent())
        .timeout(std::time::Duration::from_secs(30));

    match ssl_mode {
        "allow_self_signed" => {
            b = b.danger_accept_invalid_certs(true);
        }
        "imported_ca" => {
            // Full imported CA support comes later; for now use system trust
            // and surface LD-NET-010 on failure.
        }
        _ => {}
    }

    b.build().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-SYS-001", "Something went wrong (LD-SYS-001).")
                .with_detail(e.to_string()),
        )
    })
}

fn map_status(status: reqwest::StatusCode, body: &str) -> LabDeskError {
    let summary = truncate(body, 200);
    match status.as_u16() {
        401 => LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-001",
            "Authentication failed. Check your token.",
        )),
        403 => LabDeskError::App(
            ErrorInfo::new("LD-API-403", "Access denied by GitLab.").with_detail(summary),
        ),
        404 => LabDeskError::App(
            ErrorInfo::new("LD-API-404", "Not found or no access.").with_detail(summary),
        ),
        422 => LabDeskError::App(
            ErrorInfo::new("LD-API-422", "Request rejected.").with_detail(summary),
        ),
        429 => LabDeskError::App(
            ErrorInfo::new("LD-API-429", "Rate limited. Retrying in N seconds.").retryable(),
        ),
        s if (500..600).contains(&s) => LabDeskError::App(
            ErrorInfo::new("LD-API-5XX", format!("GitLab server error ({s})."))
                .with_detail(summary)
                .retryable(),
        ),
        _ => LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("{status}: {summary}")),
        ),
    }
}

fn truncate(s: &str, max: usize) -> String {
    let t = s.trim();
    if t.len() <= max {
        t.to_string()
    } else {
        format!("{}…", &t[..max])
    }
}

pub fn get_user(base_url: &str, pat: &str, ssl_mode: &str) -> Result<GitLabUser> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/user", api_root(base_url));
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
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
        return Err(map_status(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode /user: {e}")),
        )
    })
}

pub fn get_version(base_url: &str, pat: &str, ssl_mode: &str) -> Result<Option<GitLabVersion>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/version", api_root(base_url));
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
        .header("Accept", "application/json")
        .send()
        .map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                    .with_detail(e.to_string()),
            )
        })?;

    let status = resp.status();
    if status.as_u16() == 403 || status.as_u16() == 404 {
        return Ok(None);
    }
    let body = resp.text().unwrap_or_default();
    if !status.is_success() {
        return Ok(None);
    }
    Ok(serde_json::from_str(&body).ok())
}

/// Paginated membership project list (`api-contract.md` §5.3).
pub fn list_membership_projects(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<GitLabProject>> {
    let client = client_for(ssl_mode)?;
    let mut page = 1u32;
    let mut all = Vec::new();

    loop {
        let url = format!(
            "{}/projects?membership=true&simple=false&order_by=last_activity_at&sort=desc&per_page=100&page={}",
            api_root(base_url),
            page
        );
        let resp = client
            .get(&url)
            .header("PRIVATE-TOKEN", pat)
            .header("Accept", "application/json")
            .send()
            .map_err(|e| {
                LabDeskError::App(
                    ErrorInfo::new("LD-NET-001", "Cannot reach instance. Working offline.")
                        .with_detail(e.to_string()),
                )
            })?;

        let status = resp.status();
        let next = resp
            .headers()
            .get("x-next-page")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string());
        let body = resp.text().unwrap_or_default();
        if !status.is_success() {
            return Err(map_status(status, &body));
        }

        let batch: Vec<GitLabProject> = serde_json::from_str(&body).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-API-001", "GitLab API error.")
                    .with_detail(format!("decode /projects: {e}")),
            )
        })?;

        if batch.is_empty() {
            break;
        }
        all.extend(batch);

        let Some(next_page) = next.filter(|s| !s.is_empty()) else {
            break;
        };
        match next_page.parse::<u32>() {
            Ok(n) if n > page => page = n,
            _ => break,
        }
    }

    Ok(all)
}

#[derive(Debug, Clone, Deserialize)]
pub struct CreatedMergeRequest {
    pub iid: u64,
    pub title: String,
    pub state: Option<String>,
    pub web_url: Option<String>,
}

/// `POST /projects/:id/merge_requests` (api-contract §5.4).
pub fn create_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    source_branch: &str,
    target_branch: &str,
    title: &str,
    description: Option<&str>,
) -> Result<CreatedMergeRequest> {
    let title = title.trim();
    if title.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-001", "Failed to create MR.")
                .with_detail("Title is required."),
        ));
    }
    let client = client_for(ssl_mode)?;
    let url = format!("{}/projects/{}/merge_requests", api_root(base_url), project_id);
    let mut body = serde_json::json!({
        "source_branch": source_branch.trim(),
        "target_branch": target_branch.trim(),
        "title": title,
    });
    if let Some(desc) = description {
        body["description"] = serde_json::Value::String(desc.to_string());
    }

    let resp = client
        .post(&url)
        .header("PRIVATE-TOKEN", pat)
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
        return Err(map_status(status, &text));
    }
    serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode merge_request: {e}")),
        )
    })
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabMergeRequest {
    pub iid: i64,
    pub title: Option<String>,
    pub state: Option<String>,
    pub web_url: Option<String>,
    pub source_branch: Option<String>,
    pub target_branch: Option<String>,
    pub updated_at: Option<String>,
}

/// Opened MRs for a project (`api-contract` §5.5).
pub fn list_project_merge_requests(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
) -> Result<Vec<GitLabMergeRequest>> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/merge_requests?state=opened&per_page=50&order_by=updated_at&sort=desc",
        api_root(base_url),
        project_id
    );
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
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
        return Err(map_status(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode merge_requests: {e}")),
        )
    })
}

/// Whether a branch exists on the remote project (`api-contract` §6.4).
/// Returns `Ok(true)` / `Ok(false)` for 200 / 404; other errors map to LabDesk codes.
pub fn remote_branch_exists(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    branch: &str,
) -> Result<bool> {
    let branch = branch.trim().trim_start_matches("refs/heads/");
    // Strip remote prefix like origin/ for API branch name.
    let branch = branch
        .strip_prefix("origin/")
        .unwrap_or(branch)
        .trim();
    if branch.is_empty() {
        return Ok(false);
    }
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/repository/branches/{}",
        api_root(base_url),
        project_id,
        urlencoding_ref(branch)
    );
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
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
    Err(map_status(status, &body))
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabPipeline {
    pub id: u64,
    pub status: Option<String>,
    #[serde(rename = "ref")]
    pub ref_: Option<String>,
    pub web_url: Option<String>,
    pub updated_at: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitLabJob {
    pub id: u64,
    pub name: Option<String>,
    pub status: Option<String>,
    pub stage: Option<String>,
    pub when: Option<String>,
    pub web_url: Option<String>,
}

/// Latest pipeline for a ref (`api-contract` §6.1).
pub fn latest_pipeline(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    ref_name: &str,
) -> Result<Option<GitLabPipeline>> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/pipelines?ref={}&per_page=1",
        api_root(base_url),
        project_id,
        urlencoding_ref(ref_name)
    );
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
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
        return Err(map_status(status, &body));
    }

    let batch: Vec<GitLabPipeline> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode pipelines: {e}")),
        )
    })?;
    Ok(batch.into_iter().next())
}

/// Jobs for a pipeline (`api-contract` §6.2).
pub fn list_pipeline_jobs(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    pipeline_id: u64,
) -> Result<Vec<GitLabJob>> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/pipelines/{}/jobs",
        api_root(base_url),
        project_id,
        pipeline_id
    );
    let resp = client
        .get(&url)
        .header("PRIVATE-TOKEN", pat)
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
        return Err(map_status(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode jobs: {e}")),
        )
    })
}

/// Play a manual job (`api-contract` §6.3).
pub fn play_job(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    job_id: u64,
) -> Result<GitLabJob> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/jobs/{}/play",
        api_root(base_url),
        project_id,
        job_id
    );
    let resp = client
        .post(&url)
        .header("PRIVATE-TOKEN", pat)
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
    if !status.is_success() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-JOB-001", "Failed to run CI job.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode played job: {e}")),
        )
    })
}

fn urlencoding_ref(s: &str) -> String {
    // Minimal query encoding for branch names.
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char);
            }
            b'/' => out.push_str("%2F"),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}
