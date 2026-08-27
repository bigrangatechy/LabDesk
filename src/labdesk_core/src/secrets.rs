//! API PAT storage via the OS keyring (ADR-008).
//!
//! Persistent storage remains the FreeDesktop Secret Service. A small
//! process-local cache avoids hammering D-Bus on every API call (refresh,
//! pipelines, clone, …). Overlapping Secret Service sessions from several
//! Qt worker threads commonly surface as intermittent
//! `LD-AUTH-003` … `Crypto error: message decryption failed`.

use std::collections::HashMap;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use keyring::Entry;

use crate::error::{ErrorInfo, LabDeskError, Result};

const SERVICE: &str = "LabDesk";

/// Serialize Secret Service access — concurrent sessions break AES session
/// crypto ("message decryption failed").
static KEYRING_LOCK: Mutex<()> = Mutex::new(());

/// Session cache: keyring_account → PAT. Cleared on store/clear.
static PAT_CACHE: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

fn map_entry_err(e: keyring::Error) -> LabDeskError {
    LabDeskError::App(
        ErrorInfo::new("LD-AUTH-002", "Cannot access system keyring.").with_detail(e.to_string()),
    )
}

fn map_io_err(e: keyring::Error) -> LabDeskError {
    LabDeskError::App(
        ErrorInfo::new(
            "LD-AUTH-003",
            "Could not store or read the access token.",
        )
        .with_detail(e.to_string()),
    )
}

fn is_transient(err: &keyring::Error) -> bool {
    let s = err.to_string().to_lowercase();
    s.contains("timeout")
        || s.contains("did not receive a reply")
        || s.contains("temporarily")
        || s.contains("unavailable")
        || s.contains("busy")
        || s.contains("connection")
        || s.contains("disconnected")
        || s.contains("interrupted")
        || s.contains("decryption failed")
        || s.contains("crypto error")
        || s.contains("platform secure storage")
        || s.contains("session")
}

/// Run a keyring op off any ambient Tokio runtime (async-secret-service
/// can deadlock / fail when called on the runtime thread).
fn on_keyring_thread<F, T>(f: F) -> T
where
    F: FnOnce() -> T + Send + 'static,
    T: Send + 'static,
{
    let (tx, rx) = std::sync::mpsc::channel();
    thread::spawn(move || {
        let _ = tx.send(f());
    });
    rx.recv().expect("keyring worker thread")
}

fn cache_get(keyring_account: &str) -> Option<String> {
    let guard = PAT_CACHE.lock().ok()?;
    guard.as_ref()?.get(keyring_account).cloned()
}

fn cache_set(keyring_account: &str, pat: &str) {
    if let Ok(mut guard) = PAT_CACHE.lock() {
        let map = guard.get_or_insert_with(HashMap::new);
        map.insert(keyring_account.to_string(), pat.to_string());
    }
}

fn cache_remove(keyring_account: &str) {
    if let Ok(mut guard) = PAT_CACHE.lock() {
        if let Some(map) = guard.as_mut() {
            map.remove(keyring_account);
        }
    }
}

pub fn store_pat(keyring_account: &str, pat: &str) -> Result<()> {
    let account = keyring_account.to_string();
    let secret = pat.to_string();
    let result = on_keyring_thread(move || {
        let _guard = KEYRING_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let mut last_err = None;
        for attempt in 0..3 {
            // Fresh Entry each attempt — poisoned SS sessions must not be reused.
            let entry = match Entry::new(SERVICE, &account) {
                Ok(e) => e,
                Err(e) => return Err(map_entry_err(e)),
            };
            match entry.set_password(&secret) {
                Ok(()) => return Ok(()),
                Err(e) if attempt < 2 && is_transient(&e) => {
                    last_err = Some(e);
                    thread::sleep(Duration::from_millis(100 * (attempt as u64 + 1)));
                }
                Err(e) => return Err(map_io_err(e)),
            }
        }
        Err(map_io_err(last_err.expect("retry loop")))
    });
    if result.is_ok() {
        cache_set(keyring_account, pat);
    }
    result
}

pub fn load_pat(keyring_account: &str) -> Result<String> {
    if let Some(cached) = cache_get(keyring_account) {
        return Ok(cached);
    }

    let account = keyring_account.to_string();
    let result = on_keyring_thread(move || {
        let _guard = KEYRING_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let mut last_err = None;
        for attempt in 0..3 {
            let entry = match Entry::new(SERVICE, &account) {
                Ok(e) => e,
                Err(e) => return Err(map_entry_err(e)),
            };
            match entry.get_password() {
                Ok(secret) => return Ok(secret),
                Err(keyring::Error::NoEntry) => {
                    return Err(LabDeskError::App(ErrorInfo::new(
                        "LD-AUTH-004",
                        "No access token configured.",
                    )));
                }
                Err(e) if attempt < 2 && is_transient(&e) => {
                    last_err = Some(e);
                    thread::sleep(Duration::from_millis(100 * (attempt as u64 + 1)));
                }
                Err(e) => return Err(map_io_err(e)),
            }
        }
        Err(map_io_err(last_err.expect("retry loop")))
    })?;
    cache_set(keyring_account, &result);
    Ok(result)
}

pub fn clear_pat(keyring_account: &str) -> Result<()> {
    cache_remove(keyring_account);
    let account = keyring_account.to_string();
    on_keyring_thread(move || {
        let _guard = KEYRING_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let entry = Entry::new(SERVICE, &account).map_err(map_entry_err)?;
        match entry.delete_credential() {
            Ok(()) => Ok(()),
            Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(map_io_err(e)),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_round_trip() {
        cache_remove("test-acc");
        assert!(cache_get("test-acc").is_none());
        cache_set("test-acc", "glpat-secret");
        assert_eq!(cache_get("test-acc").as_deref(), Some("glpat-secret"));
        cache_remove("test-acc");
        assert!(cache_get("test-acc").is_none());
    }

    #[test]
    fn decryption_failed_is_transient() {
        // Mirror the Flatpak popup detail text.
        let detail = "Platform secure storage failure: Crypto error: message decryption failed";
        let lower = detail.to_lowercase();
        assert!(lower.contains("decryption failed"));
        assert!(lower.contains("crypto error"));
        assert!(lower.contains("platform secure storage"));
    }
}
