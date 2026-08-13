//! Imported CA helpers (`trusted_certs/` under the config dir).

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};

use crate::error::{ErrorInfo, LabDeskError, Result};
use crate::paths::AppPaths;

static GIT_SSL_CAINFO_LOCK: Mutex<()> = Mutex::new(());

impl AppPaths {
    pub fn trusted_certs_dir(&self) -> PathBuf {
        self.config_dir.join("trusted_certs")
    }

    pub fn trusted_ca_bundle(&self) -> PathBuf {
        self.trusted_certs_dir().join("labdesk-ca-bundle.pem")
    }
}

/// List `.pem` / `.crt` files in `trusted_certs/` (non-recursive, sorted).
pub fn list_cert_files(paths: &AppPaths) -> Result<Vec<PathBuf>> {
    let dir = paths.trusted_certs_dir();
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("read trusted_certs: {e}")),
        )
    })? {
        let entry = entry.map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail(e.to_string()),
            )
        })?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name.eq_ignore_ascii_case("labdesk-ca-bundle.pem") {
            continue;
        }
        let lower = name.to_ascii_lowercase();
        if lower.ends_with(".pem") || lower.ends_with(".crt") || lower.ends_with(".cer") {
            out.push(path);
        }
    }
    out.sort();
    Ok(out)
}

/// Copy a user-selected PEM/CRT into `trusted_certs/` and refresh the bundle.
pub fn import_cert_file(paths: &AppPaths, source: &Path) -> Result<PathBuf> {
    if !source.is_file() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("not a file: {}", source.display())),
        ));
    }
    let bytes = fs::read(source).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("read {}: {e}", source.display())),
        )
    })?;
    // Basic sanity: PEM markers or DER-ish length.
    let looks_pem = bytes.windows(11).any(|w| w == b"BEGIN CERTI")
        || std::str::from_utf8(&bytes)
            .map(|s| s.contains("BEGIN CERTIFICATE"))
            .unwrap_or(false);
    if !looks_pem {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail("file does not look like a PEM certificate"),
        ));
    }
    paths.ensure_dirs().map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(e.to_string()),
        )
    })?;
    let dir = paths.trusted_certs_dir();
    fs::create_dir_all(&dir).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("create trusted_certs: {e}")),
        )
    })?;
    let base = source
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("imported.pem");
    let mut dest = dir.join(base);
    if dest.exists() {
        let stem = Path::new(base)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("imported");
        let ext = Path::new(base)
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("pem");
        for i in 2..1000 {
            let candidate = dir.join(format!("{stem}-{i}.{ext}"));
            if !candidate.exists() {
                dest = candidate;
                break;
            }
        }
    }
    fs::write(&dest, &bytes).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("write {}: {e}", dest.display())),
        )
    })?;
    let _ = write_ca_bundle(paths)?;
    Ok(dest)
}

pub fn remove_cert_file(paths: &AppPaths, name: &str) -> Result<()> {
    let name = Path::new(name)
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or_else(|| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail("invalid certificate name"),
            )
        })?;
    if name.eq_ignore_ascii_case("labdesk-ca-bundle.pem") {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail("cannot remove internal CA bundle"),
        ));
    }
    let path = paths.trusted_certs_dir().join(name);
    if path.exists() {
        fs::remove_file(&path).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail(e.to_string()),
            )
        })?;
    }
    let _ = write_ca_bundle(paths)?;
    Ok(())
}

/// Concatenate imported PEMs into `labdesk-ca-bundle.pem` for libgit2 / OpenSSL.
pub fn write_ca_bundle(paths: &AppPaths) -> Result<PathBuf> {
    let files = list_cert_files(paths)?;
    if files.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(
                    "ssl_mode=imported_ca but no PEM/CRT files in trusted_certs/",
                ),
        ));
    }
    let dir = paths.trusted_certs_dir();
    fs::create_dir_all(&dir).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(e.to_string()),
        )
    })?;
    let mut bundle = Vec::new();
    for f in &files {
        let mut data = fs::read(f).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail(format!("read {}: {e}", f.display())),
            )
        })?;
        if !data.ends_with(b"\n") {
            data.push(b'\n');
        }
        bundle.extend_from_slice(&data);
    }
    let out = paths.trusted_ca_bundle();
    fs::write(&out, &bundle).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(format!("write bundle: {e}")),
        )
    })?;
    Ok(out)
}

/// Load certificates for reqwest (`add_root_certificate`).
pub fn load_reqwest_certs(paths: &AppPaths) -> Result<Vec<reqwest::Certificate>> {
    let files = list_cert_files(paths)?;
    if files.is_empty() {
        return Err(LabDeskError::App(
            ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                .with_detail(
                    "ssl_mode=imported_ca but no PEM/CRT files in trusted_certs/",
                ),
        ));
    }
    let mut out = Vec::new();
    for f in files {
        let bytes = fs::read(&f).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail(format!("read {}: {e}", f.display())),
            )
        })?;
        let cert = reqwest::Certificate::from_pem(&bytes).map_err(|e| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail(format!("parse {}: {e}", f.display())),
            )
        })?;
        out.push(cert);
    }
    Ok(out)
}

/// Hold `GIT_SSL_CAINFO` for the duration of a libgit2 HTTPS call.
pub struct GitSslCaInfoGuard {
    _lock: MutexGuard<'static, ()>,
    previous: Option<std::ffi::OsString>,
}

impl GitSslCaInfoGuard {
    pub fn apply(bundle: &Path) -> Result<Self> {
        let lock = GIT_SSL_CAINFO_LOCK.lock().map_err(|_| {
            LabDeskError::App(
                ErrorInfo::new("LD-NET-010", "Certificate not trusted. Import CA or allow.")
                    .with_detail("GIT_SSL_CAINFO lock poisoned"),
            )
        })?;
        let previous = std::env::var_os("GIT_SSL_CAINFO");
        std::env::set_var("GIT_SSL_CAINFO", bundle);
        Ok(Self {
            _lock: lock,
            previous,
        })
    }
}

impl Drop for GitSslCaInfoGuard {
    fn drop(&mut self) {
        match &self.previous {
            Some(v) => std::env::set_var("GIT_SSL_CAINFO", v),
            None => std::env::remove_var("GIT_SSL_CAINFO"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_paths() -> (PathBuf, AppPaths) {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("labdesk-tls-test-{stamp}"));
        let config_dir = root.join("config");
        let data_dir = root.join("data");
        fs::create_dir_all(&config_dir).unwrap();
        fs::create_dir_all(&data_dir).unwrap();
        (
            root,
            AppPaths {
                config_dir,
                data_dir,
            },
        )
    }

    // Minimal self-signed-looking PEM is hard; use a truncated invalid for parse fail
    // and a known-good test cert from rcgen... keep unit test to list/import path only
    // with a synthetic PEM header file that from_pem may reject — test list + empty error.

    #[test]
    fn empty_imported_ca_errors() {
        let (root, paths) = temp_paths();
        let err = write_ca_bundle(&paths).unwrap_err();
        assert_eq!(err.info().code, "LD-NET-010");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn import_rejects_non_pem() {
        let (root, paths) = temp_paths();
        let bogus = root.join("not-a-cert.txt");
        fs::write(&bogus, b"hello").unwrap();
        assert!(import_cert_file(&paths, &bogus).is_err());
        let _ = fs::remove_dir_all(root);
    }
}
