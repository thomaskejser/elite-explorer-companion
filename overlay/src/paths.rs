use std::path::PathBuf;

use windows::Win32::System::Com::CoTaskMemFree;
use windows::Win32::UI::Shell::{FOLDERID_LocalAppData, FOLDERID_SavedGames, KF_FLAG_DEFAULT, SHGetKnownFolderPath};
use windows::core::GUID;

const APP: &str = "explorers-companion";
const LEGACY_APP: &str = "ed-overlay";
pub const SEED_FILE: &str = "elite_mapping_seed.duckdb";
pub const STATE_FILE: &str = "state.duckdb";
pub const LOG_FILE: &str = "explorers-companion.log";
pub const LEGACY_BINDINGS: &str = "keybindings.json";

fn known_folder(id: &GUID) -> Option<PathBuf> {
    unsafe {
        let p = SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, None).ok()?;
        let path = p.to_string().ok().map(PathBuf::from);
        CoTaskMemFree(Some(p.0 as *const _));
        path
    }
}

fn local_app_data() -> PathBuf {
    known_folder(&FOLDERID_LocalAppData).unwrap_or_else(std::env::temp_dir)
}

pub fn data_dir() -> PathBuf {
    local_app_data().join(APP)
}

pub fn adopt_legacy_data_dir() {
    let (old, new) = (local_app_data().join(LEGACY_APP), data_dir());
    if new.exists() || !old.exists() || std::fs::rename(&old, &new).is_err() {
        return;
    }
    for entry in std::fs::read_dir(&new).into_iter().flatten().flatten() {
        if entry.file_name().to_string_lossy().starts_with("model-") {
            let _ = std::fs::remove_file(entry.path());
        }
    }
}

pub fn journal_dir() -> PathBuf {
    known_folder(&FOLDERID_SavedGames)
        .or_else(|| std::env::var_os("USERPROFILE").map(|home| PathBuf::from(home).join("Saved Games")))
        .unwrap_or_default()
        .join("Frontier Developments")
        .join("Elite Dangerous")
}

fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|exe| exe.parent().map(PathBuf::from))
}

pub fn screenshot_dir() -> PathBuf {
    exe_dir().unwrap_or_else(data_dir).join("screenshots")
}

pub fn log_file() -> PathBuf {
    exe_dir().unwrap_or_else(data_dir).join("log").join(LOG_FILE)
}

pub fn default_seed() -> PathBuf {
    exe_dir()
        .map(|dir| dir.join(SEED_FILE))
        .filter(|p| p.exists())
        .unwrap_or_else(|| data_dir().join(SEED_FILE))
}
