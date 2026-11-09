use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

use crate::fss::write_png;
use crate::log::utc_file_stamp;
use crate::stars;
use crate::win::screen;

pub const SETTLE: Duration = Duration::from_millis(150);
const CAPTURES_FILE: &str = "captures.csv";
const CAPTURES_HEADER: &str = "file,address,system,x,y,z";

pub struct Shot {
    pub system: Option<String>,
    pub address: Option<i64>,
    pub pos: Option<[f64; 3]>,
}

pub struct Giants {
    pub origin: (i32, i32),
    pub size: (i32, i32),
    pub rings: Vec<Ring>,
    pub holes: Vec<(i32, i32, f64)>,
}

pub struct Ring {
    pub x: i32,
    pub y: i32,
    pub disc: i32,
    pub dim: bool,
}

pub struct Capture {
    pub path: PathBuf,
    pub stars: usize,
    pub giants: Giants,
}

pub struct Galaxy {
    tx: Sender<Shot>,
    rx: Receiver<Result<Capture, String>>,
}

impl Galaxy {
    pub fn start(dir: PathBuf) -> Galaxy {
        let (tx, rx_in) = mpsc::channel::<Shot>();
        let (tx_out, rx) = mpsc::channel();
        let _ = std::thread::Builder::new().name("galaxy".into()).spawn(move || {
            while let Ok(shot) = rx_in.recv() {
                std::thread::sleep(SETTLE);
                let _ = tx_out.send(capture(&dir, &shot));
            }
        });
        Galaxy { tx, rx }
    }

    pub fn shoot(&self, shot: Shot) {
        let _ = self.tx.send(shot);
    }

    pub fn drain(&self) -> Vec<Result<Capture, String>> {
        self.rx.try_iter().collect()
    }
}

fn capture(dir: &Path, shot: &Shot) -> Result<Capture, String> {
    let (frame, origin) = screen::grab_game()?;
    let scan = stars::scan(&frame);
    let found = scan.stars;
    let holes = scan.holes.iter().map(|h| (h.x as i32, h.y as i32, h.radius)).collect();
    let rings = found
        .iter()
        .filter(|s| s.giant)
        .map(|s| Ring { x: s.x as i32, y: s.y as i32, disc: s.disc as i32, dim: !s.white_filled() })
        .collect();
    let giants = Giants { origin, size: (frame.width as i32, frame.height as i32), rings, holes };
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let address = shot.address.map_or("unknown".to_string(), |a| a.to_string());
    let name = format!("{}-{address}-galaxy.png", utc_file_stamp());
    let path = dir.join(&name);
    write_png(&frame, &path)?;
    let csv = dir.join(CAPTURES_FILE);
    let fresh = !csv.exists();
    let mut file = OpenOptions::new().create(true).append(true).open(&csv).map_err(|e| e.to_string())?;
    if fresh {
        writeln!(file, "{CAPTURES_HEADER}").map_err(|e| e.to_string())?;
    }
    let system = shot.system.as_deref().unwrap_or("").replace('"', "\"\"");
    let pos = shot.pos.map_or(",,".to_string(), |p| format!("{},{},{}", p[0], p[1], p[2]));
    writeln!(file, "{name},{},\"{system}\",{pos}", shot.address.map_or(String::new(), |a| a.to_string()))
        .map_err(|e| e.to_string())?;
    Ok(Capture { path, stars: found.len(), giants })
}
