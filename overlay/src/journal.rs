use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use serde_json::Value;

pub const POS_EVENTS: [&str; 3] = ["FSDJump", "CarrierJump", "Location"];
pub const CLASS_EVENTS: [&str; 2] = ["FSDTarget", "StartJump"];
pub const SHIP_EVENTS: [&str; 1] = ["Loadout"];
pub const OUTCOME_EVENTS: [&str; 2] = ["Scan", "FSSAllBodiesFound"];
const INTEREST_KEYS: [&str; 5] = ["\"StarPos\"", "\"StarClass\"", "\"Loadout\"", "\"StarType\"", "\"FSSAllBodiesFound\""];

const NAVROUTE_FILE: &str = "NavRoute.json";
const STATUS_FILE: &str = "Status.json";

pub fn default_dir() -> PathBuf {
    let home = std::env::var_os("USERPROFILE").map(PathBuf::from).unwrap_or_default();
    home.join("Saved Games").join("Frontier Developments").join("Elite Dangerous")
}

pub fn event_name(e: &Value) -> &str {
    e.get("event").and_then(Value::as_str).unwrap_or("")
}

fn str_field<'a>(e: &'a Value, key: &str) -> Option<&'a str> {
    e.get(key).and_then(Value::as_str).filter(|s| !s.is_empty())
}

fn mtime(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|m| m.modified()).ok()
}

fn journals(dir: &Path) -> Vec<(PathBuf, SystemTime)> {
    let Ok(entries) = fs::read_dir(dir) else { return Vec::new() };
    entries
        .filter_map(Result::ok)
        .filter(|e| {
            let name = e.file_name().to_string_lossy().into_owned();
            name.starts_with("Journal.") && name.ends_with(".log")
        })
        .filter_map(|e| mtime(&e.path()).map(|t| (e.path(), t)))
        .collect()
}

pub fn latest_journal(dir: &Path) -> Option<PathBuf> {
    journals(dir).into_iter().max_by_key(|(_, t)| *t).map(|(p, _)| p)
}

fn read_lossy(path: &Path) -> Option<String> {
    fs::read(path).ok().map(|b| String::from_utf8_lossy(&b).into_owned())
}

fn parse(line: &str) -> Option<Value> {
    serde_json::from_str(line).ok()
}

fn interesting(line: &str) -> Option<Value> {
    if !INTEREST_KEYS.iter().any(|k| line.contains(k)) {
        return None;
    }
    let e = parse(line)?;
    let name = event_name(&e);
    let wanted = POS_EVENTS.contains(&name)
        || CLASS_EVENTS.contains(&name)
        || SHIP_EVENTS.contains(&name)
        || OUTCOME_EVENTS.contains(&name);
    if !wanted {
        return None;
    }
    if POS_EVENTS.contains(&name) && str_field(&e, "StarSystem").is_none() {
        return None;
    }
    Some(e)
}

pub struct StarScan {
    pub system: String,
    pub body: String,
    pub star_type: String,
}

pub fn star_scan(e: &Value) -> Option<StarScan> {
    Some(StarScan {
        system: str_field(e, "StarSystem")?.to_string(),
        body: str_field(e, "BodyName")?.to_string(),
        star_type: str_field(e, "StarType")?.to_string(),
    })
}

pub fn all_bodies_found(e: &Value) -> Option<String> {
    str_field(e, "SystemName").map(String::from)
}

pub struct ClassRow {
    pub system: Option<String>,
    pub star_class: Option<String>,
    pub id64: Option<i64>,
}

pub fn class_of(e: &Value) -> ClassRow {
    ClassRow {
        system: str_field(e, "Name").or_else(|| str_field(e, "StarSystem")).map(String::from),
        star_class: str_field(e, "StarClass").map(String::from),
        id64: e.get("SystemAddress").and_then(as_i64),
    }
}

fn as_i64(v: &Value) -> Option<i64> {
    v.as_i64().or_else(|| v.as_u64().map(|u| u as i64))
}

pub struct JournalReader {
    dir: PathBuf,
    path: Option<PathBuf>,
    file: Option<File>,
    pending: Vec<u8>,
}

impl JournalReader {
    pub fn new(dir: PathBuf) -> JournalReader {
        JournalReader { dir, path: None, file: None, pending: Vec::new() }
    }

    pub fn prime(&mut self) -> Option<Value> {
        self.path = latest_journal(&self.dir);
        let path = self.path.clone()?;
        let text = read_lossy(&path).unwrap_or_default();
        let last = text
            .lines()
            .filter(|l| l.contains("\"StarPos\""))
            .filter_map(parse)
            .filter(|e| POS_EVENTS.contains(&event_name(e)) && str_field(e, "StarSystem").is_some())
            .next_back();
        self.open_at_end(&path);
        last
    }

    fn open_at_end(&mut self, path: &Path) {
        self.pending.clear();
        self.file = File::open(path).ok().and_then(|mut f| f.seek(SeekFrom::End(0)).ok().map(|_| f));
    }

    pub fn harvest_classes(&mut self) -> Vec<ClassRow> {
        if self.path.is_none() {
            self.path = latest_journal(&self.dir);
        }
        let Some(path) = self.path.clone() else { return Vec::new() };
        let Some(text) = read_lossy(&path) else { return Vec::new() };
        text.lines()
            .filter_map(interesting)
            .filter(|e| CLASS_EVENTS.contains(&event_name(e)))
            .map(|e| class_of(&e))
            .filter(|r| r.system.is_some() && r.star_class.is_some())
            .collect()
    }

    pub fn poll(&mut self) -> Vec<Value> {
        if self.file.is_none() {
            return self.prime().into_iter().collect();
        }
        let mut events = Vec::new();
        let mut chunk = Vec::new();
        if let Some(f) = self.file.as_mut() {
            let _ = f.read_to_end(&mut chunk);
        }
        self.pending.extend_from_slice(&chunk);
        if let Some(end) = self.pending.iter().rposition(|&b| b == b'\n') {
            let complete: Vec<u8> = self.pending.drain(..=end).collect();
            let text = String::from_utf8_lossy(&complete);
            events.extend(text.lines().filter_map(interesting));
        }
        let newest = latest_journal(&self.dir);
        if let Some(newest) = newest.filter(|n| Some(n) != self.path.as_ref()) {
            self.path = Some(newest.clone());
            if let Some(text) = read_lossy(&newest) {
                events.extend(text.lines().filter_map(interesting));
            }
            self.open_at_end(&newest);
        }
        events
    }
}

pub fn read_loadout(dir: &Path) -> Option<Value> {
    let mut files = journals(dir);
    files.sort_by(|a, b| b.1.cmp(&a.1));
    for (path, _) in files {
        let Some(text) = read_lossy(&path) else { continue };
        let last = text
            .lines()
            .filter(|l| l.contains("\"Loadout\""))
            .filter_map(parse)
            .filter(|e| event_name(e) == "Loadout")
            .next_back();
        if last.is_some() {
            return last;
        }
    }
    None
}

#[derive(Clone, Debug)]
pub struct Hop {
    pub system: String,
    pub star_class: Option<String>,
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub z: Option<f64>,
    pub id64: Option<i64>,
}

pub enum Gated<T> {
    Unchanged,
    Changed(T),
}

pub fn read_navroute(dir: &Path, last: &mut Option<SystemTime>) -> Gated<Vec<Hop>> {
    let path = dir.join(NAVROUTE_FILE);
    let Some(t) = mtime(&path) else { return Gated::Unchanged };
    if last.is_some_and(|l| t <= l) {
        return Gated::Unchanged;
    }
    *last = Some(t);
    let Some(data) = read_lossy(&path).and_then(|s| parse(&s)) else {
        return Gated::Unchanged;
    };
    let hops = data
        .get("Route")
        .and_then(Value::as_array)
        .map(|route| {
            route
                .iter()
                .filter_map(|hop| {
                    let system = str_field(hop, "StarSystem")?.to_string();
                    let pos = hop.get("StarPos").and_then(Value::as_array);
                    let at = |i: usize| pos.and_then(|p| p.get(i)).and_then(Value::as_f64);
                    Some(Hop {
                        system,
                        star_class: str_field(hop, "StarClass").map(String::from),
                        x: at(0),
                        y: at(1),
                        z: at(2),
                        id64: hop.get("SystemAddress").and_then(as_i64),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    Gated::Changed(hops)
}

pub fn read_status(dir: &Path, last: &mut Option<SystemTime>) -> Gated<Value> {
    let path = dir.join(STATUS_FILE);
    let Some(t) = mtime(&path) else { return Gated::Unchanged };
    if last.is_some_and(|l| t <= l) {
        return Gated::Unchanged;
    }
    match read_lossy(&path).and_then(|s| parse(&s)) {
        Some(v) => {
            *last = Some(t);
            Gated::Changed(v)
        }
        None => Gated::Unchanged,
    }
}

const STATUS_FLAGS: [(&str, u32); 32] = [
    ("Docked", 0),
    ("Landed", 1),
    ("LandingGearDown", 2),
    ("ShieldsUp", 3),
    ("Supercruise", 4),
    ("FlightAssistOff", 5),
    ("HardpointsDeployed", 6),
    ("InWing", 7),
    ("LightsOn", 8),
    ("CargoScoopDeployed", 9),
    ("SilentRunning", 10),
    ("ScoopingFuel", 11),
    ("SrvHandbrake", 12),
    ("SrvTurretView", 13),
    ("SrvTurretRetracted", 14),
    ("SrvDriveAssist", 15),
    ("FsdMassLocked", 16),
    ("FsdCharging", 17),
    ("FsdCooldown", 18),
    ("LowFuel", 19),
    ("OverHeating", 20),
    ("HasLatLong", 21),
    ("IsInDanger", 22),
    ("BeingInterdicted", 23),
    ("InMainShip", 24),
    ("InFighter", 25),
    ("InSRV", 26),
    ("HudAnalysisMode", 27),
    ("NightVision", 28),
    ("AltitudeFromAverageRadius", 29),
    ("FsdJump", 30),
    ("SrvHighBeam", 31),
];

pub fn flag(status: Option<&Value>, name: &str) -> Option<bool> {
    let flags = status?.get("Flags")?.as_u64()?;
    let bit = STATUS_FLAGS.iter().find(|(n, _)| *n == name).expect("unknown status flag").1;
    Some(flags >> bit & 1 == 1)
}

pub struct Position {
    pub system: Option<String>,
    pub xyz: Option<[f64; 3]>,
    pub timestamp: Option<String>,
}

pub fn position_of(e: &Value) -> Position {
    let pos = e.get("StarPos").and_then(Value::as_array);
    let xyz = pos.and_then(|p| {
        let v: Vec<f64> = p.iter().filter_map(Value::as_f64).collect();
        (v.len() == 3).then(|| [v[0], v[1], v[2]])
    });
    Position {
        system: str_field(e, "StarSystem").map(String::from),
        xyz,
        timestamp: str_field(e, "timestamp").map(String::from),
    }
}
