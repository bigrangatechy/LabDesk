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
