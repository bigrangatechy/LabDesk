//! XDG / Flatpak-aware config and data paths.

use std::path::PathBuf;

use directories::{BaseDirs, ProjectDirs};

const QUALIFIER: &str = "com";
const ORGANIZATION: &str = "bigrangatech";
const APPLICATION: &str = "LabDesk";

/// Flatpak sandbox app id directory name under `~/.var/app/`.
const FLATPAK_APP_ID: &str = "com.bigrangatech.LabDesk";

#[derive(Debug, Clone)]
pub struct AppPaths {
    pub config_dir: PathBuf,
    pub data_dir: PathBuf,
}

impl AppPaths {
    pub fn detect() -> Self {
        if is_flatpak() {
            let home = BaseDirs::new()
                .map(|b| b.home_dir().to_path_buf())
                .unwrap_or_else(|| PathBuf::from("."));
            let root = home.join(".var/app").join(FLATPAK_APP_ID);
            return Self {
                config_dir: root.join("config/labdesk"),
                data_dir: root.join("data/labdesk"),
            };
        }

        if let Some(dirs) = ProjectDirs::from(QUALIFIER, ORGANIZATION, APPLICATION) {
            // ProjectDirs uses com/bigrangatech/LabDesk; we want ~/.config/labdesk
            // per data-model. Prefer XDG with short name "labdesk".
            let _ = dirs;
        }

        let home = BaseDirs::new();
        let config_home = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| home.as_ref().map(|b| b.home_dir().join(".config")))
            .unwrap_or_else(|| PathBuf::from(".config"));
        let data_home = std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| home.as_ref().map(|b| b.home_dir().join(".local/share")))
            .unwrap_or_else(|| PathBuf::from(".local/share"));

        Self {
            config_dir: config_home.join("labdesk"),
            data_dir: data_home.join("labdesk"),
        }
    }

    pub fn config_toml(&self) -> PathBuf {
        self.config_dir.join("config.toml")
    }

    pub fn known_good_toml(&self) -> PathBuf {
        self.config_dir.join("config.known-good.toml")
    }

    pub fn cache_db(&self) -> PathBuf {
        self.data_dir.join("cache.db")
    }

    pub fn ensure_dirs(&self) -> std::io::Result<()> {
        std::fs::create_dir_all(&self.config_dir)?;
        std::fs::create_dir_all(self.data_dir.join("logs"))?;
        Ok(())
    }
}

fn is_flatpak() -> bool {
    std::path::Path::new("/.flatpak-info").exists()
        || std::env::var_os("FLATPAK_ID").is_some()
}
