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

fn client_for(ssl_mode: &str) -> Result<reqwest::blocking::Client> {
    let mut b = reqwest::blocking::Client::builder()
        .user_agent(format!("LabDesk/{}", env!("CARGO_PKG_VERSION")))
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
