//! GitLab REST API v4 client (`PRIVATE-TOKEN`).

use serde::Deserialize;

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::forge_types::{
    CreatedPullRequest, ForgeJob, ForgePipeline, ForgeProject, ForgePullRequest, ForgeUser,
    ForgeVersion,
};
use crate::http_client::{client_for, map_status, truncate, urlencoding_ref};

pub use crate::forge_types::{
    CreatedMergeRequest, GitLabJob, GitLabMergeRequest, GitLabPipeline, GitLabProject, GitLabUser,
    GitLabVersion,
};

fn api_root(base_url: &str) -> String {
    format!("{}/api/v4", base_url.trim_end_matches('/'))
}

fn err_map(status: reqwest::StatusCode, body: &str) -> LabDeskError {
    map_status(status, body, "GitLab")
}

pub fn get_user(base_url: &str, pat: &str, ssl_mode: &str) -> Result<ForgeUser> {
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
        return Err(err_map(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode /user: {e}")),
        )
    })
}

pub fn get_version(base_url: &str, pat: &str, ssl_mode: &str) -> Result<Option<ForgeVersion>> {
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
            return Err(err_map(status, &body));
        }

        let batch: Vec<ForgeProject> = serde_json::from_str(&body).map_err(|e| {
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

pub fn create_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    source_branch: &str,
    target_branch: &str,
    title: &str,
    description: Option<&str>,
    draft: bool,
) -> Result<CreatedPullRequest> {
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
        "draft": draft,
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
        return Err(err_map(status, &text));
    }
    serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode merge_request: {e}")),
        )
    })
}

pub fn list_project_merge_requests(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
) -> Result<Vec<ForgePullRequest>> {
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
        return Err(err_map(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode merge_requests: {e}")),
        )
    })
}

pub fn remote_branch_exists(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    branch: &str,
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
    Err(err_map(status, &body))
}

pub fn latest_pipeline(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    ref_name: &str,
) -> Result<Option<ForgePipeline>> {
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
        return Err(err_map(status, &body));
    }

    let batch: Vec<ForgePipeline> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode pipelines: {e}")),
        )
    })?;
    Ok(batch.into_iter().next())
}

pub fn list_pipeline_jobs(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    pipeline_id: u64,
) -> Result<Vec<ForgeJob>> {
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
        return Err(err_map(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode jobs: {e}")),
        )
    })
}

pub fn play_job(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    job_id: u64,
) -> Result<ForgeJob> {
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

/// Resolve path_with_namespace for a numeric project id (GitLab-only helper unused by others).
#[allow(dead_code)]
pub fn project_path_hint(_project_id: i64) -> Option<String> {
    None
}

#[derive(Debug, Deserialize)]
struct RawMrDetail {
    iid: i64,
    title: Option<String>,
    description: Option<String>,
    state: Option<String>,
    web_url: Option<String>,
    source_branch: Option<String>,
    target_branch: Option<String>,
    updated_at: Option<String>,
    draft: Option<bool>,
    work_in_progress: Option<bool>,
    author: Option<RawAuthor>,
}

#[derive(Debug, Deserialize)]
struct RawAuthor {
    username: Option<String>,
    name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawNote {
    id: i64,
    body: Option<String>,
    created_at: Option<String>,
    author: Option<RawAuthor>,
}

pub fn get_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/merge_requests/{}",
        api_root(base_url),
        project_id,
        mr_iid
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
        return Err(err_map(status, &body));
    }
    let raw: RawMrDetail = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode mr: {e}")),
        )
    })?;
    let draft = raw.draft.unwrap_or(false) || raw.work_in_progress.unwrap_or(false);
    let author = raw.author.and_then(|a| a.username.or(a.name));
    Ok(crate::forge_types::ForgePullRequestDetail {
        iid: raw.iid,
        title: raw.title,
        description: raw.description,
        state: raw.state,
        web_url: raw.web_url,
        source_branch: raw.source_branch,
        target_branch: raw.target_branch,
        author,
        draft,
        updated_at: raw.updated_at,
    })
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
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/merge_requests/{}",
        api_root(base_url),
        project_id,
        mr_iid
    );
    let mut body = serde_json::Map::new();
    if let Some(t) = title {
        body.insert("title".into(), serde_json::Value::String(t.to_string()));
    }
    if let Some(d) = description {
        body.insert(
            "description".into(),
            serde_json::Value::String(d.to_string()),
        );
    }
    if let Some(t) = target_branch {
        body.insert(
            "target_branch".into(),
            serde_json::Value::String(t.to_string()),
        );
    }
    let resp = client
        .put(&url)
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
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-002", "Failed to update MR.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid)
}

pub fn merge_merge_request(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    merge_method: Option<&str>,
) -> Result<crate::forge_types::ForgePullRequestDetail> {
    let client = client_for(ssl_mode)?;
    let url = format!(
        "{}/projects/{}/merge_requests/{}/merge",
        api_root(base_url),
        project_id,
        mr_iid
    );
    let mut body = serde_json::json!({});
    if let Some(m) = merge_method {
        // GitLab uses merge_commit / squash / etc via squash + merge_commit_message;
        // accept "merge" | "squash" loosely.
        if m.eq_ignore_ascii_case("squash") {
            body["squash"] = serde_json::Value::Bool(true);
        }
    }
    let resp = client
        .put(&url)
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
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-MR-003", "Failed to merge MR.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    get_merge_request(base_url, pat, ssl_mode, project_id, mr_iid)
}

pub fn list_merge_request_notes(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    mr_iid: i64,
    page: u32,
) -> Result<Vec<crate::forge_types::ForgeNote>> {
    let client = client_for(ssl_mode)?;
    let page = page.max(1);
    let url = format!(
        "{}/projects/{}/merge_requests/{}/notes?per_page=50&page={page}&sort=asc&order_by=created_at",
        api_root(base_url),
        project_id,
        mr_iid
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
        return Err(err_map(status, &body));
    }
    let raw: Vec<RawNote> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode notes: {e}")),
        )
    })?;
    Ok(raw
        .into_iter()
        .map(|n| crate::forge_types::ForgeNote {
            id: n.id,
            body: n.body,
            author: n.author.and_then(|a| a.username.or(a.name)),
            created_at: n.created_at,
        })
        .collect())
}

// --- Slice J: runners + admin users ---

#[derive(Debug, Deserialize)]
struct RawRunner {
    id: i64,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    active: Option<bool>,
    #[serde(default)]
    paused: Option<bool>,
    #[serde(default)]
    online: Option<bool>,
    #[serde(default)]
    is_shared: Option<bool>,
    #[serde(default)]
    runner_type: Option<String>,
    #[serde(default)]
    tag_list: Vec<String>,
}

fn map_runner(r: RawRunner, base_url: &str, scope: &str) -> crate::forge_types::ForgeRunner {
    let paused = r.paused.or_else(|| r.active.map(|a| !a));
    let active = match (r.active, r.paused) {
        (Some(a), _) => a,
        (None, Some(p)) => !p,
        _ => true,
    };
    let id = r.id.to_string();
    let web = format!(
        "{}/admin/runners/{}",
        base_url.trim_end_matches('/'),
        id
    );
    crate::forge_types::ForgeRunner {
        id,
        description: r.description,
        active,
        online: r.online,
        paused,
        is_shared: r.is_shared,
        tag_list: r.tag_list,
        runner_type: r.runner_type,
        web_url: Some(web),
        scope: Some(scope.into()),
    }
}

fn fetch_runners_json(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    path_and_query: &str,
) -> Result<Vec<RawRunner>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}{}", api_root(base_url), path_and_query);
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
        return Err(err_map(status, &body));
    }
    serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode runners: {e}")),
        )
    })
}

/// Instance runners (`/runners/all`, fallback `/runners` on 403).
pub fn list_instance_runners(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<crate::forge_types::ForgeRunner>> {
    match fetch_runners_json(base_url, pat, ssl_mode, "/runners/all?per_page=100") {
        Ok(raw) => Ok(raw
            .into_iter()
            .map(|r| map_runner(r, base_url, "instance"))
            .collect()),
        Err(LabDeskError::App(info)) if info.code == "LD-API-403" => {
            let raw = fetch_runners_json(base_url, pat, ssl_mode, "/runners?per_page=100")?;
            Ok(raw
                .into_iter()
                .map(|r| map_runner(r, base_url, "owned"))
                .collect())
        }
        Err(e) => Err(e),
    }
}

pub fn list_project_runners(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    project_id: i64,
    path_hint: Option<&str>,
) -> Result<Vec<crate::forge_types::ForgeRunner>> {
    let _ = path_hint;
    let path = format!("/projects/{project_id}/runners?per_page=100");
    let raw = fetch_runners_json(base_url, pat, ssl_mode, &path)?;
    Ok(raw
        .into_iter()
        .map(|r| map_runner(r, base_url, "project"))
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
    let _ = (project_id, path_hint);
    let client = client_for(ssl_mode)?;
    let url = format!("{}/runners/{}", api_root(base_url), urlencoding_ref(runner_id));
    let body = serde_json::json!({ "paused": paused });
    let resp = client
        .put(&url)
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
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-API-RUN-001", "Failed to update runner.")
                .with_detail(truncate(&text, 200)),
        ));
    }
    let raw: RawRunner = serde_json::from_str(&text).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode runner: {e}")),
        )
    })?;
    Ok(map_runner(raw, base_url, "instance"))
}

pub fn delete_runner(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
    runner_id: &str,
    project_id: Option<i64>,
    path_hint: Option<&str>,
) -> Result<()> {
    let _ = (project_id, path_hint);
    let client = client_for(ssl_mode)?;
    let url = format!("{}/runners/{}", api_root(base_url), urlencoding_ref(runner_id));
    let resp = client
        .delete(&url)
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
    username: String,
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    state: Option<String>,
    #[serde(default)]
    is_admin: Option<bool>,
    #[serde(default)]
    web_url: Option<String>,
}

pub fn list_admin_users(
    base_url: &str,
    pat: &str,
    ssl_mode: &str,
) -> Result<Vec<crate::forge_types::ForgeAdminUser>> {
    let client = client_for(ssl_mode)?;
    let url = format!("{}/users?per_page=100&order_by=id", api_root(base_url));
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
        return Err(err_map(status, &body));
    }
    let raw: Vec<RawAdminUser> = serde_json::from_str(&body).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-API-001", "GitLab API error.")
                .with_detail(format!("decode users: {e}")),
        )
    })?;
    Ok(raw
        .into_iter()
        .map(|u| crate::forge_types::ForgeAdminUser {
            id: u.id,
            username: u.username,
            name: u.name,
            email: u.email,
            is_admin: u.is_admin,
            state: u.state,
            web_url: u.web_url,
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn api_root_trims_slash() {
        assert_eq!(api_root("https://git.example.com/"), "https://git.example.com/api/v4");
    }

    #[test]
    fn decode_user_fixture() {
        let raw = r#"{"id":1,"username":"jessie","name":"Jessie","web_url":"https://git.example/jessie"}"#;
        let u: ForgeUser = serde_json::from_str(raw).unwrap();
        assert_eq!(u.username, "jessie");
    }
}
