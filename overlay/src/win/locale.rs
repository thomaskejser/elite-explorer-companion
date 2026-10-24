use windows::Win32::Globalization::{GetLocaleInfoEx, LOCALE_SGROUPING, LOCALE_STHOUSAND};
use windows::core::PCWSTR;

pub struct Grouping {
    pub separator: String,
    pub sizes: Vec<usize>,
    pub repeat: bool,
}

fn user_value(lctype: u32) -> Option<String> {
    let mut buf = [0u16; 16];
    let n = unsafe { GetLocaleInfoEx(PCWSTR::null(), lctype, Some(&mut buf)) };
    (n > 0).then(|| String::from_utf16_lossy(&buf[..n as usize - 1]))
}

pub fn parse_grouping(separator: String, spec: &str) -> Grouping {
    let mut sizes: Vec<usize> = spec.split(';').filter_map(|s| s.trim().parse().ok()).collect();
    let repeat = sizes.last() == Some(&0);
    if repeat {
        sizes.pop();
    }
    Grouping { separator, sizes, repeat }
}

pub fn user_grouping() -> Grouping {
    let separator = user_value(LOCALE_STHOUSAND).unwrap_or_else(|| ",".into());
    let spec = user_value(LOCALE_SGROUPING).unwrap_or_else(|| "3;0".into());
    parse_grouping(separator, &spec)
}
