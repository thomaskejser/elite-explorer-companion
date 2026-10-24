use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use serde_json::Value;

pub const POS_EVENTS: [&str; 3] = ["FSDJump", "CarrierJump", "Location"];
pub const CLASS_EVENTS: [&str; 2] = ["FSDTarget", "StartJump"];
pub const SHIP_EVENTS: [&str; 1] = ["Loadout"];
pub const OUTCOME_EVENTS: [&str; 2] = ["Scan", "FSSAllBodiesFound"];
pub const CARRIER_EVENTS: [&str; 4] = ["CarrierLocation", "CarrierStats", "CarrierJumpRequest", "CarrierJumpCancelled"];
const INTEREST_KEYS: [&str; 9] = [
    "\"StarPos\"",
    "\"StarClass\"",
    "\"Loadout\"",
    "\"StarType\"",
    "\"FSSAllBodiesFound\"",
    "\"CarrierLocation\"",
    "\"CarrierStats\"",
    "\"CarrierJumpRequest\"",
    "\"CarrierJumpCancelled\"",
];
const CARRIER_FILES: usize = 60;
pub const CARRIER_CAPACITY_T: f64 = 25_000.0;
pub const CARRIER_COOLDOWN_S: i64 = 300;
const CARRIER_JUMP_S: i64 = 60;

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
        || OUTCOME_EVENTS.contains(&name)
        || CARRIER_EVENTS.contains(&name);
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

#[derive(Clone, Debug, Default)]
pub struct Carrier {
    pub callsign: Option<String>,
    pub name: Option<String>,
    pub system: Option<String>,
    pub address: Option<i64>,
    pub located_at: Option<String>,
    pub pos: Option<[f64; 3]>,
    pub fuel: Option<i64>,
    pub used_t: Option<i64>,
    pub stats_at: Option<String>,
    pub pending: Option<(String, Option<i64>)>,
    pub arrived_at: Option<i64>,
}

fn star_pos(e: &Value) -> Option<[f64; 3]> {
    let p = e.get("StarPos").and_then(Value::as_array)?;
    Some([p.first()?.as_f64()?, p.get(1)?.as_f64()?, p.get(2)?.as_f64()?])
}

pub fn iso_secs(iso: &str) -> Option<i64> {
    let num = |a: usize, b: usize| iso.get(a..b)?.parse::<i64>().ok();
    let (y, m, d) = (num(0, 4)?, num(5, 7)?, num(8, 10)?);
    let (h, mi, s) = (num(11, 13)?, num(14, 16)?, num(17, 19)?);
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let days = era * 146_097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719_468;
    Some(days * 86_400 + h * 3_600 + mi * 60 + s)
}

struct Request {
    at: String,
    system: String,
    address: Option<i64>,
    departs: Option<i64>,
}

pub fn read_carrier(dir: &Path, now: i64) -> Carrier {
    let mut files = journals(dir);
    files.sort_by(|a, b| b.1.cmp(&a.1));
    let mut c = Carrier::default();
    let mut request: Option<Request> = None;
    let mut cancelled_at: Option<String> = None;
    let mut locations: Vec<(String, String)> = Vec::new();
    let mut seen: std::collections::HashMap<i64, [f64; 3]> = std::collections::HashMap::new();
    for (path, _) in files.into_iter().take(CARRIER_FILES) {
        let Some(text) = read_lossy(&path) else { continue };
        for e in text.lines().rev().filter(|l| l.contains("\"Carrier") || l.contains("\"StarPos\"")).filter_map(parse) {
            let at = str_field(&e, "timestamp").map(String::from);
            match event_name(&e) {
                "CarrierLocation" => {
                    if c.system.is_none() {
                        c.system = str_field(&e, "StarSystem").map(String::from);
                        c.address = as_i64(&e["SystemAddress"]);
                        c.located_at = at.clone();
                    }
                    if let (Some(at), Some(system)) = (at, str_field(&e, "StarSystem")) {
                        locations.push((at, system.to_string()));
                    }
                }
                "CarrierStats" if c.stats_at.is_none() => {
                    c.callsign = str_field(&e, "Callsign").map(String::from);
                    c.name = str_field(&e, "Name").map(String::from);
                    c.fuel = as_i64(&e["FuelLevel"]);
                    let usage = &e["SpaceUsage"];
                    c.used_t = as_i64(&usage["TotalCapacity"]).zip(as_i64(&usage["FreeSpace"])).map(|(t, f)| t - f);
                    c.stats_at = at;
                }
                "CarrierJumpRequest" if request.is_none() => {
                    if let (Some(system), Some(at)) = (str_field(&e, "SystemName"), at) {
                        request = Some(Request {
                            at,
                            system: system.to_string(),
                            address: as_i64(&e["SystemAddress"]),
                            departs: str_field(&e, "DepartureTime").and_then(iso_secs),
                        });
                    }
                }
                "CarrierJumpCancelled" if cancelled_at.is_none() => cancelled_at = at,
                _ => {}
            }
            if let (Some(address), Some(pos)) = (as_i64(&e["SystemAddress"]), star_pos(&e)) {
                seen.entry(address).or_insert(pos);
            }
        }
        let located = c.address.is_some_and(|a| seen.contains_key(&a));
        if c.system.is_some() && c.stats_at.is_some() && located && request.is_some() {
            break;
        }
    }
    if let Some(r) = request
        && cancelled_at.as_ref().is_none_or(|x| *x < r.at)
    {
        let arrival = locations.iter().filter(|(at, s)| *s == r.system && *at > r.at).map(|(at, _)| at).min();
        match (arrival.and_then(|a| iso_secs(a)), r.departs) {
            (Some(arrived), _) => c.arrived_at = Some(arrived),
            (None, Some(departs)) if now > departs + CARRIER_JUMP_S => {
                c.system = Some(r.system.clone());
                c.address = r.address;
                c.arrived_at = Some(departs + CARRIER_JUMP_S);
            }
            (None, departs) => c.pending = Some((r.system.clone(), departs)),
        }
    }
    c.pos = c.address.and_then(|a| seen.get(&a).copied());
    c
}

fn clock(secs: i64) -> String {
    let secs = secs.max(0);
    format!("{}:{:02}", secs / 60, secs % 60)
}

pub fn carrier_ready(c: &Carrier, now: i64) -> bool {
    c.system.is_some() && c.pending.is_none() && c.arrived_at.is_none_or(|a| now >= a + CARRIER_COOLDOWN_S)
}

pub fn carrier_phase(c: &Carrier, now: i64) -> String {
    if let Some((to, departs)) = &c.pending {
        return match departs {
            Some(d) if *d > now => format!("jumping to {to} in {}", clock(d - now)),
            _ => format!("jumping to {to} now"),
        };
    }
    match c.arrived_at {
        Some(arrived) if now < arrived + CARRIER_COOLDOWN_S => {
            format!("cooling down, ready in about {}", clock(arrived + CARRIER_COOLDOWN_S - now))
        }
        _ => "ready to jump".to_string(),
    }
}

pub fn carrier_line(c: &Carrier, now: i64) -> [String; 3] {
    let Some(system) = &c.system else { return Default::default() };
    let sep = "  \u{00B7}  ";
    let callsign = format!("CARRIER {}", c.callsign.clone().unwrap_or_default()).trim_end().to_string();
    let tail = c.fuel.map_or(String::new(), |fuel| format!("{sep}Tritium {fuel} t"));
    [format!("{callsign}{sep}{system}{sep}"), carrier_phase(c, now), tail]
}

pub fn carrier_tritium(jump_ly: f64, used_t: i64, fuel: i64) -> i64 {
    (5.0 + jump_ly / 8.0 * (1.0 + (used_t + fuel) as f64 / CARRIER_CAPACITY_T)).round() as i64
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_pending_jump_counts_down_and_a_login_at_the_origin_does_not_end_it() {
        let dir = std::env::temp_dir().join(format!("ed-carrier-pending-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("Journal.2026-10-24T110000.01.log"),
            [
                r#"{ "timestamp":"2026-10-24T11:24:03Z", "event":"CarrierJumpRequest", "SystemName":"Col 359 Sector CH-K c9-9", "SystemAddress":2556679951162, "DepartureTime":"2026-10-24T11:39:10Z" }"#,
                r#"{ "timestamp":"2026-10-24T11:30:00Z", "event":"CarrierLocation", "StarSystem":"Col 359 Sector FK-Y c1-13", "SystemAddress":3656795558650 }"#,
            ]
            .join("\n"),
        )
        .unwrap();
        let at = |s: &str| iso_secs(s).unwrap();
        let counting = read_carrier(&dir, at("2026-10-24T11:31:10Z"));
        let assumed = read_carrier(&dir, at("2026-10-24T11:45:00Z"));
        fs::write(
            dir.join("Journal.2026-10-24T113100.01.log"),
            r#"{ "timestamp":"2026-10-24T11:32:00Z", "event":"CarrierJumpCancelled" }"#,
        )
        .unwrap();
        let cancelled = read_carrier(&dir, at("2026-10-24T11:33:00Z"));
        let _ = fs::remove_dir_all(&dir);
        assert_eq!(carrier_phase(&counting, at("2026-10-24T11:31:10Z")), "jumping to Col 359 Sector CH-K c9-9 in 8:00");
        assert!(!carrier_ready(&counting, at("2026-10-24T11:31:10Z")));
        assert_eq!(assumed.system.as_deref(), Some("Col 359 Sector CH-K c9-9"));
        assert_eq!(assumed.arrived_at, Some(at("2026-10-24T11:40:10Z")));
        assert!(cancelled.pending.is_none() && cancelled.arrived_at.is_none());
        assert_eq!(cancelled.system.as_deref(), Some("Col 359 Sector FK-Y c1-13"));
        assert_eq!(carrier_phase(&cancelled, at("2026-10-24T11:33:00Z")), "ready to jump");
    }

    #[test]
    fn carrier_tritium_matches_logged_jumps() {
        assert_eq!(carrier_tritium(157.5, 6_426, 500), 30);
        assert_eq!(carrier_tritium(132.3, 8_374, 1_000), 28);
        assert_eq!(carrier_tritium(488.8, 12_508, 972), 99);
    }

    #[test]
    fn reads_the_latest_carrier_state_and_its_position() {
        let dir = std::env::temp_dir().join(format!("ed-carrier-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("Journal.2026-10-24T100000.01.log"),
            [
                r#"{ "timestamp":"2026-10-24T10:00:00Z", "event":"FSDJump", "StarSystem":"Xinca", "SystemAddress":4408557439331, "StarPos":[123.90625,-6.40625,-48.9375] }"#,
                r#"{ "timestamp":"2026-10-24T10:35:22Z", "event":"CarrierStats", "Callsign":"N1X-G2F", "Name":"SS DRUUNA", "FuelLevel":972, "SpaceUsage":{ "TotalCapacity":25000, "FreeSpace":12492 } }"#,
                r#"{ "timestamp":"2026-10-24T10:40:00Z", "event":"CarrierLocation", "StarSystem":"Xinca", "SystemAddress":4408557439331 }"#,
                r#"{ "timestamp":"2026-10-24T10:46:17Z", "event":"CarrierJumpRequest", "SystemName":"Col 359 Sector FK-Y c1-13", "DepartureTime":"2026-10-24T11:01:00Z" }"#,
                r#"{ "timestamp":"2026-10-24T11:02:10Z", "event":"CarrierLocation", "StarSystem":"Col 359 Sector FK-Y c1-13", "SystemAddress":3656795558650 }"#,
                r#"{ "timestamp":"2026-10-24T11:03:10Z", "event":"CarrierJump", "StarSystem":"Col 359 Sector FK-Y c1-13", "SystemAddress":3656795558650, "StarPos":[-304.40625,-11.3125,186.46875] }"#,
            ]
            .join("\n"),
        )
        .unwrap();
        let c = read_carrier(&dir, iso_secs("2026-10-24T11:10:00Z").unwrap());
        let _ = fs::remove_dir_all(&dir);
        assert_eq!(c.system.as_deref(), Some("Col 359 Sector FK-Y c1-13"));
        assert_eq!(c.callsign.as_deref(), Some("N1X-G2F"));
        assert_eq!(c.fuel, Some(972));
        assert_eq!(c.used_t, Some(12_508));
        assert_eq!(c.pos, Some([-304.40625, -11.3125, 186.46875]));
        assert!(c.pending.is_none());
        assert_eq!(c.arrived_at, iso_secs("2026-10-24T11:02:10Z"));
        let now = iso_secs("2026-10-24T11:05:10Z").unwrap();
        assert_eq!(carrier_phase(&c, now), "cooling down, ready in about 2:00");
        assert_eq!(carrier_phase(&c, now + 600), "ready to jump");
        assert!(!carrier_ready(&c, now));
        assert!(carrier_ready(&c, now + 600));
        let [lead, phase, tail] = carrier_line(&c, now + 600);
        assert_eq!(lead, "CARRIER N1X-G2F  \u{00B7}  Col 359 Sector FK-Y c1-13  \u{00B7}  ");
        assert_eq!(phase, "ready to jump");
        assert_eq!(tail, "  \u{00B7}  Tritium 972 t");
    }
}
