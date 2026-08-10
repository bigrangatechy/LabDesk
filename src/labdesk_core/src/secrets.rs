//! API PAT storage via the OS keyring (ADR-008).

use keyring::Entry;

use crate::error::{ErrorInfo, LabDeskError, Result};

const SERVICE: &str = "LabDesk";

pub fn store_pat(keyring_account: &str, pat: &str) -> Result<()> {
    let entry = Entry::new(SERVICE, keyring_account).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-AUTH-002", "Cannot access system keyring.").with_detail(e.to_string()),
        )
    })?;
    entry.set_password(pat).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new(
                "LD-AUTH-003",
                "Could not store or read the access token.",
            )
            .with_detail(e.to_string()),
        )
    })?;
    Ok(())
}

pub fn load_pat(keyring_account: &str) -> Result<String> {
    let entry = Entry::new(SERVICE, keyring_account).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-AUTH-002", "Cannot access system keyring.").with_detail(e.to_string()),
        )
    })?;
    match entry.get_password() {
        Ok(secret) => Ok(secret),
        Err(keyring::Error::NoEntry) => Err(LabDeskError::App(ErrorInfo::new(
            "LD-AUTH-004",
            "No access token configured.",
        ))),
        Err(e) => Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-AUTH-003",
                "Could not store or read the access token.",
            )
            .with_detail(e.to_string()),
        )),
    }
}

pub fn clear_pat(keyring_account: &str) -> Result<()> {
    let entry = Entry::new(SERVICE, keyring_account).map_err(|e| {
        LabDeskError::App(
            ErrorInfo::new("LD-AUTH-002", "Cannot access system keyring.").with_detail(e.to_string()),
        )
    })?;
    match entry.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(LabDeskError::App(
            ErrorInfo::new(
                "LD-AUTH-003",
                "Could not store or read the access token.",
            )
            .with_detail(e.to_string()),
        )),
    }
}
