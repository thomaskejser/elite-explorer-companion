use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

const ROTATE_BYTES: u64 = 16 << 20;

static SINK: Mutex<Option<File>> = Mutex::new(None);

pub fn start(path: &Path) -> std::io::Result<PathBuf> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    if fs::metadata(path).is_ok_and(|m| m.len() >= ROTATE_BYTES) {
        fs::rename(path, path.with_extension("1.log"))?;
    }
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    let argv: Vec<String> = std::env::args().collect();
    writeln!(file, "\n=== {}  {}", utc_stamp(), argv.join(" "))?;
    file.flush()?;
    *SINK.lock().unwrap() = Some(file);
    Ok(path.to_path_buf())
}

pub fn stop() {
    if let Some(mut file) = SINK.lock().unwrap().take() {
        let _ = writeln!(file, "=== ended {}", utc_stamp());
    }
}

pub fn say(line: &str) {
    println!("{line}");
    if let Some(file) = SINK.lock().unwrap().as_mut() {
        let _ = writeln!(file, "{line}");
        let _ = file.flush();
    }
}

#[macro_export]
macro_rules! say {
    ($($arg:tt)*) => { $crate::log::say(&format!($($arg)*)) };
}

pub fn utc_stamp() -> String {
    let (y, mo, d, h, mi, s) = utc_parts(SystemTime::now());
    format!("{y:04}-{mo:02}-{d:02} {h:02}:{mi:02}:{s:02}Z")
}

pub fn utc_iso_at(t: SystemTime) -> String {
    let (y, mo, d, h, mi, s) = utc_parts(t);
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}Z")
}

pub fn utc_iso_seconds() -> String {
    let (y, mo, d, h, mi, s) = utc_parts(SystemTime::now());
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}+00:00")
}

pub fn utc_hms() -> String {
    let (_, _, _, h, mi, s) = utc_parts(SystemTime::now());
    format!("{h:02}:{mi:02}:{s:02}")
}

fn utc_parts(t: SystemTime) -> (i64, u32, u32, u32, u32, u32) {
    let secs = t.duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0);
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400) as u32;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    (y, m, d, rem / 3600, rem % 3600 / 60, rem % 60)
}
