use std::fs::{self, File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

use crate::bands;
use crate::log::utc_file_stamp;
use crate::say;
use crate::spectrum::{self, Bar, Icon, Tip};
use crate::win::screen;

pub const OPEN_SETTLE: Duration = Duration::from_millis(1500);
pub const HONK_SETTLE: Duration = Duration::from_millis(1000);
pub const OPEN: &str = "open";
pub const HONK: &str = "honk";
pub const SCAN_SETTLE: Duration = Duration::from_millis(1500);
pub const WATCH_EVERY: Duration = Duration::from_secs(2);
pub const WATCH: &str = "watch";
const TUNED_FILE: &str = "tuned.csv";
const LAST_FILE: &str = "last.png";
pub const KEEP_SETTING: &str = "fss.keep_captures";

static KEEP_ALL: AtomicBool = AtomicBool::new(false);

pub fn keep_all() -> bool {
    KEEP_ALL.load(Ordering::Relaxed)
}

pub fn set_keep_all(on: bool) {
    KEEP_ALL.store(on, Ordering::Relaxed);
}
const TUNED_HEADER: &str = "stamp,address,body,class,icon";
const FRAMES_PER_CLASS: usize = 3;
const SAME_ICON: f64 = 0.01;
const STRIP_SIDE: f64 = 0.06;
const STRIP_ABOVE: f64 = 0.12;
const STRIP_BELOW: f64 = 0.08;

pub struct Frame {
    pub width: usize,
    pub height: usize,
    pub rgb: Vec<u8>,
}

pub struct Resolved {
    pub body: String,
    pub class: String,
}

pub struct Shot {
    pub settle: Duration,
    pub address: Option<i64>,
    pub reason: &'static str,
    pub resolved: Option<Resolved>,
}

#[derive(Default)]
struct Seen {
    address: Option<i64>,
    icons: Vec<f64>,
    record: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ScreenBar {
    pub left: i32,
    pub top: i32,
    pub length: i32,
}

pub struct Sighting {
    pub tips: Vec<Tip>,
    pub slots: Vec<usize>,
    pub icons: Vec<f64>,
    pub bar: ScreenBar,
}

pub struct Watch {
    pub reason: &'static str,
    pub address: Option<i64>,
    pub sighting: Option<Sighting>,
}

struct Outcome {
    note: String,
    seen: Option<Sighting>,
}

pub struct Fss {
    tx: Sender<Shot>,
    rx: Receiver<Watch>,
}

impl Fss {
    pub fn start(dir: PathBuf) -> Fss {
        let (tx, rx_in) = mpsc::channel::<Shot>();
        let (tx_out, rx) = mpsc::channel::<Watch>();
        let _ = std::thread::Builder::new().name("fss".into()).spawn(move || {
            let mut seen = Seen::default();
            while let Ok(shot) = rx_in.recv() {
                std::thread::sleep(shot.settle);
                let seen_now = match capture(&dir, &shot, &mut seen) {
                    Ok(out) => {
                        if !out.note.is_empty() {
                            say!("fss: {} {}", shot.reason, out.note);
                        }
                        out.seen
                    }
                    Err(e) => {
                        if shot.reason != WATCH {
                            say!("fss: {} capture skipped: {e}", shot.reason);
                        }
                        None
                    }
                };
                let _ = tx_out.send(Watch { reason: shot.reason, address: shot.address, sighting: seen_now });
            }
        });
        Fss { tx, rx }
    }

    pub fn shoot(&self, shot: Shot) {
        let _ = self.tx.send(shot);
    }

    pub fn drain(&self) -> Vec<Watch> {
        self.rx.try_iter().collect()
    }
}

fn slug(text: &str) -> String {
    text.chars().map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '_' }).collect()
}

fn frames_of(dir: &Path, tag: &str) -> usize {
    fs::read_dir(dir).map_or(0, |d| d.flatten().filter(|e| e.file_name().to_string_lossy().ends_with(&format!("-{tag}.png"))).count())
}

fn fresh(seen: &[f64], icons: &[Icon]) -> Vec<Icon> {
    icons.iter().filter(|i| seen.iter().all(|s| (s - i.at).abs() > SAME_ICON)).copied().collect()
}

fn crop(frame: &Frame, x0: usize, y0: usize, x1: usize, y1: usize) -> Frame {
    let (x1, y1) = (x1.min(frame.width), y1.min(frame.height));
    let rgb = (y0..y1).flat_map(|y| frame.rgb[(y * frame.width + x0) * 3..(y * frame.width + x1) * 3].iter().copied()).collect();
    Frame { width: x1 - x0, height: y1 - y0, rgb }
}

fn strip(frame: &Frame, bar: &Bar) -> (usize, usize, Frame) {
    let (x0, y0) = (bar.left.saturating_sub(bar.px(STRIP_SIDE)), bar.top.saturating_sub(bar.px(STRIP_ABOVE)));
    (x0, y0, crop(frame, x0, y0, bar.right + bar.px(STRIP_SIDE), bar.bottom + bar.px(STRIP_BELOW)))
}

fn on_screen(reading: &spectrum::Reading, origin: (i32, i32)) -> Sighting {
    let bar = &reading.bar;
    Sighting {
        tips: reading.tips.clone(),
        slots: reading.slots(),
        icons: reading.icons.iter().map(|i| i.at).collect(),
        bar: ScreenBar { left: origin.0 + bar.left as i32, top: origin.1 + bar.top as i32, length: (bar.right - bar.left) as i32 },
    }
}

fn capture(dir: &Path, shot: &Shot, seen: &mut Seen) -> Result<Outcome, String> {
    let (frame, origin) = screen::grab_game()?;
    if seen.address != shot.address {
        *seen = Seen { address: shot.address, ..Seen::default() };
    }
    let reading = spectrum::read(&frame);
    let mut notes = Vec::new();
    if let Some(r) = reading.as_ref().filter(|_| shot.resolved.is_none()) {
        let at: Vec<String> = r.spikes.iter().map(|s| format!("{:.3}", s.at)).collect();
        let unknown = bands::unknown(&bands::marks(&r.slots(), &r.icons.iter().map(|i| i.at).collect::<Vec<_>>()));
        if shot.reason != WATCH {
            notes.push(format!("{} spike(s) at {}", at.len(), at.join(" ")));
        }
        if unknown > 0 && !seen.record {
            notes.push(format!("{unknown} unknown slot(s)"));
            seen.record = true;
        }
    }
    let new = reading.as_ref().map_or(Vec::new(), |r| fresh(&seen.icons, &r.icons));
    seen.icons.extend(new.iter().map(|i| i.at));
    if keep_all() {
        notes.extend(save(dir, shot, &frame, reading.as_ref(), &new)?);
    } else if shot.reason != WATCH {
        fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        write_png(&frame, &dir.join(LAST_FILE))?;
    }
    if reading.is_none() && shot.reason != WATCH {
        notes.push("no spectrum bar".into());
    }
    Ok(Outcome { note: notes.join(", "), seen: reading.as_ref().map(|r| on_screen(r, origin)) })
}

fn save(dir: &Path, shot: &Shot, frame: &Frame, reading: Option<&spectrum::Reading>, new: &[Icon]) -> Result<Vec<String>, String> {
    if shot.reason == WATCH && reading.is_none() {
        return Ok(Vec::new());
    }
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let stamp = utc_file_stamp();
    let address = shot.address.map_or("unknown".to_string(), |a| a.to_string());
    let tag = shot.resolved.as_ref().map_or(shot.reason.to_string(), |r| format!("{}-{}", shot.reason, slug(&r.class)));
    let mut notes = Vec::new();
    match reading {
        Some(r) if shot.resolved.is_some() && frames_of(dir, &tag) >= FRAMES_PER_CLASS => {
            let (x0, y0, part) = strip(frame, &r.bar);
            write_png(&part, &dir.join(format!("{stamp}-{address}-{tag}-strip-{x0}-{y0}-{}x{}.png", frame.width, frame.height)))?;
        }
        _ => {
            let path = dir.join(format!("{stamp}-{address}-{tag}.png"));
            write_png(frame, &path)?;
            if shot.reason != WATCH {
                notes.push(format!("saved {}", path.display()));
            }
        }
    }
    if let Some(r) = &shot.resolved {
        let icon = match new {
            [one] => Some(*one),
            _ => None,
        };
        let icon_at = icon.map_or(String::new(), |i| format!("{:.4}", i.at));
        let line = format!("{stamp},{address},\"{}\",\"{}\",{icon_at}", r.body, r.class);
        append(&dir.join(TUNED_FILE), TUNED_HEADER, &[line]).map_err(|e| e.to_string())?;
        notes.push(format!("{} ({})", r.body, r.class));
        match icon {
            Some(_) => notes.push(format!("new icon at {icon_at}")),
            None => notes.push(format!("{} new icon(s), no label", new.len())),
        }
    }
    Ok(notes)
}

fn append(path: &Path, header: &str, lines: &[String]) -> std::io::Result<()> {
    let fresh = !path.exists();
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    if fresh {
        writeln!(file, "{header}")?;
    }
    for line in lines {
        writeln!(file, "{line}")?;
    }
    Ok(())
}

fn write_png(frame: &Frame, path: &Path) -> Result<(), String> {
    let file = File::create(path).map_err(|e| e.to_string())?;
    let mut encoder = png::Encoder::new(BufWriter::new(file), frame.width as u32, frame.height as u32);
    encoder.set_color(png::ColorType::Rgb);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_compression(png::Compression::Fast);
    let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
    writer.write_image_data(&frame.rgb).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn icon(at: f64) -> Icon {
        Icon { at, x: 0, y: 0 }
    }

    #[test]
    fn an_icon_is_new_only_where_none_was_seen() {
        let seen = [0.364, 0.394];
        let found = fresh(&seen, &[icon(0.365), icon(0.394), icon(0.423)]);
        assert_eq!(found.iter().map(|i| i.at).collect::<Vec<_>>(), [0.423]);
    }

    #[test]
    fn a_strip_keeps_the_bar_with_room_for_spikes_and_icons() {
        let frame = Frame { width: 5120, height: 1440, rgb: vec![0; 5120 * 1440 * 3] };
        let bar = Bar { top: 1112, bottom: 1113, left: 2064, right: 3056 };
        let (x0, y0, part) = strip(&frame, &bar);
        assert_eq!((x0, y0), (2064 - 60, 1112 - 119));
        assert_eq!((part.width, part.height), (3056 + 60 - x0, 1113 + 79 - y0));
    }
}
