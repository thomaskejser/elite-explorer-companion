use std::sync::mpsc::{self, Receiver, Sender};
use std::time::{Duration, SystemTime};

use serde_json::{Value, json};

use crate::log::utc_iso_at;
use crate::row::{ROW_CARRIER, Row};

const URL: &str = "https://spansh.co.uk/api/stations/search";
const AGENT: &str = concat!("explorers-companion/", env!("CARGO_PKG_VERSION"));
const CARRIER_TYPE: &str = "Drake-Class Carrier";
const DOCKING: &str = "All";
const UC: &str = "Universal Cartographics";
pub const FRESH_DAYS: u64 = 7;
const TIMEOUT: Duration = Duration::from_secs(30);

pub struct Carriers {
    tx: Sender<([f64; 3], usize)>,
    rx: Receiver<Result<Vec<Row>, String>>,
}

impl Carriers {
    pub fn start() -> Carriers {
        let (tx, rx_in) = mpsc::channel::<([f64; 3], usize)>();
        let (tx_out, rx) = mpsc::channel();
        let _ = std::thread::Builder::new().name("carriers".into()).spawn(move || {
            while let Ok(mut ask) = rx_in.recv() {
                while let Ok(newer) = rx_in.try_recv() {
                    ask = newer;
                }
                if tx_out.send(nearest(ask.0, ask.1)).is_err() {
                    break;
                }
            }
        });
        Carriers { tx, rx }
    }

    pub fn request(&self, pos: [f64; 3], limit: usize) {
        let _ = self.tx.send((pos, limit));
    }

    pub fn drain(&self) -> Option<Result<Vec<Row>, String>> {
        self.rx.try_iter().last()
    }
}

fn body(pos: [f64; 3], limit: usize, now: SystemTime) -> Value {
    let since = now - Duration::from_secs(FRESH_DAYS * 86_400);
    json!({
        "filters": {
            "type": {"value": [CARRIER_TYPE]},
            "carrier_docking_access": {"value": [DOCKING]},
            "updated_at": {"value": [utc_iso_at(since), utc_iso_at(now)], "comparison": "<=>"}
        },
        "sort": [{"distance": {"direction": "asc"}}],
        "size": limit,
        "page": 0,
        "reference_coords": {"x": pos[0], "y": pos[1], "z": pos[2]}
    })
}

pub fn nearest(pos: [f64; 3], limit: usize) -> Result<Vec<Row>, String> {
    let text = ureq::post(URL)
        .timeout(TIMEOUT)
        .set("User-Agent", AGENT)
        .set("Content-Type", "application/json")
        .send_string(&body(pos, limit, SystemTime::now()).to_string())
        .map_err(|e| e.to_string())?
        .into_string()
        .map_err(|e| e.to_string())?;
    let v: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let results = v["results"].as_array().ok_or_else(|| format!("no results in the reply: {}", v["error"]))?;
    Ok(results.iter().enumerate().filter_map(|(i, r)| row(i, r)).collect())
}

fn row(i: usize, r: &Value) -> Option<Row> {
    if r["carrier_docking_access"] != DOCKING {
        return None;
    }
    let callsign = r["name"].as_str()?.to_string();
    let uc = r["services"].as_array().is_some_and(|s| s.iter().any(|s| s["name"] == UC));
    Some(Row {
        rank: Some(i as i64 + 1),
        system: Some(r["system_name"].as_str()?.to_string()),
        type_label: Some("CARRIER".into()),
        dist_ly: r["distance"].as_f64(),
        row_grp: Some(ROW_CARRIER),
        wide_text: Some(format!("{}{callsign}", if uc { "+UC " } else { "" })),
        detail: Some(callsign),
        x: r["system_x"].as_f64(),
        y: r["system_y"].as_f64(),
        z: r["system_z"].as_f64(),
        ..Row::default()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn asks_for_the_nearest_recent_carriers_anyone_may_dock_at() {
        let b = body([1.0, 2.0, 3.0], 1, SystemTime::now());
        assert_eq!(b["filters"]["carrier_docking_access"]["value"][0], DOCKING);
        assert_eq!(b["filters"]["type"]["value"][0], CARRIER_TYPE);
        assert!(b["sort"][0].get("distance").is_some());
        assert_eq!(b["size"], 1);
    }

    #[test]
    fn keeps_only_open_carriers_and_marks_cartographics() {
        let open = json!({"name": "V4V-2XZ", "system_name": "Great Annihilator", "distance": 3289.0,
                          "system_x": 1.0, "system_y": 2.0, "system_z": 3.0, "carrier_docking_access": "All",
                          "services": [{"name": "Dock"}, {"name": UC}]});
        let shut = json!({"name": "W0K-BXZ", "system_name": "Dryaa", "carrier_docking_access": "Squadron Friends"});
        let r = row(0, &open).unwrap();
        assert_eq!(r.wide_text.as_deref(), Some("+UC V4V-2XZ"));
        assert_eq!(r.xyz(), Some([1.0, 2.0, 3.0]));
        assert!(row(1, &shut).is_none());
    }
}
