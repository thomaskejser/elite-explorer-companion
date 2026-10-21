use std::fs::{self, File};
use std::io::{self, BufWriter};
use std::path::{Path, PathBuf};

use flate2::read::ZlibDecoder;

const PACKED: &[u8] = include_bytes!("../bundle/model.duckdb.z");
const ID: &str = include_str!("../bundle/model.id");

pub fn id() -> &'static str {
    ID.trim()
}

pub fn data_dir() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    base.join("ed-overlay")
}

pub fn extract(dir: &Path) -> io::Result<PathBuf> {
    fs::create_dir_all(dir)?;
    let target = dir.join(format!("model-{}.duckdb", id()));
    if target.exists() {
        return Ok(target);
    }
    let tmp = dir.join(format!("model-{}.partial", id()));
    {
        let mut out = BufWriter::new(File::create(&tmp)?);
        io::copy(&mut ZlibDecoder::new(PACKED), &mut out)?;
        out.into_inner()?.sync_all()?;
    }
    fs::rename(&tmp, &target)?;
    for entry in fs::read_dir(dir)?.filter_map(Result::ok) {
        let name = entry.file_name().to_string_lossy().into_owned();
        let stale = name.starts_with("model-") && entry.path() != target;
        if stale {
            let _ = fs::remove_file(entry.path());
        }
    }
    Ok(target)
}
