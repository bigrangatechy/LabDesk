//! Shared HTTPS client helpers for forge backends.

use crate::error::{ErrorInfo, LabDeskError, Result};

pub fn labdesk_user_agent() -> String {
    let ver = option_env!("LABDESK_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"));
    format!("LabDesk/{ver}")
}

pub fn client_for(ssl_mode: &str) -> Result<reqwest::blocking::Client> {
    let mut b = reqwest::blocking::Client::builder()
        .user_agent(labdesk_user_agent())
        .timeout(std::time::Duration::from_secs(30));

    match ssl_mode {
        "allow_self_signed" => {
            b = b.danger_accept_invalid_certs(true);
        }
        "imported_ca" => {
            let paths = crate::paths::AppPaths::detect();
            let certs = crate::tls::load_reqwest_certs(&paths)?;
            for cert in certs {
                b = b.add_root_certificate(cert);
            }
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

pub fn truncate(s: &str, max: usize) -> String {
    let t = s.trim();
    if t.len() <= max {
        t.to_string()
    } else {
        format!("{}…", &t[..max])
    }
}

pub fn map_status(status: reqwest::StatusCode, body: &str, forge_label: &str) -> LabDeskError {
    let summary = truncate(body, 200);
    match status.as_u16() {
        401 => LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-001",
            "Authentication failed. Check your token.",
        )),
        403 => LabDeskError::App(
            ErrorInfo::new("LD-API-403", format!("Access denied by {forge_label}."))
                .with_detail(summary),
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
            ErrorInfo::new("LD-API-5XX", format!("{forge_label} server error ({s})."))
                .with_detail(summary)
                .retryable(),
        ),
        _ => LabDeskError::App(
            ErrorInfo::new("LD-API-001", format!("{forge_label} API error."))
                .with_detail(format!("{status}: {summary}")),
        ),
    }
}

pub fn urlencoding_ref(s: &str) -> String {
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

pub fn split_owner_repo(path_with_namespace: &str) -> Option<(String, String)> {
    let p = path_with_namespace.trim().trim_matches('/');
    let (owner, repo) = p.rsplit_once('/')?;
    if owner.is_empty() || repo.is_empty() {
        return None;
    }
    Some((owner.to_string(), repo.to_string()))
}
