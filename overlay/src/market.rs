use std::sync::mpsc::{self, Receiver, Sender};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};

use crate::log::utc_iso_at;

const URL: &str = "https://spansh.co.uk/api/stations/search";
const AGENT: &str = concat!("explorers-companion/", env!("CARGO_PKG_VERSION"));
const COMMODITY: &str = "Tritium";
const STATION_TYPES: [&str; 10] = [
    "Coriolis Starport",
    "Orbis Starport",
    "Ocellus Starport",
    "Dodec Starport",
    "Outpost",
    "Asteroid base",
    "Planetary Port",
    "Planetary Outpost",
    "Settlement",
    "Mega ship",
];
pub const RADIUS_LY: u32 = 250;
pub const FRESH_DAYS: u64 = 30;
const TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone, Debug)]
pub struct Quote {
    pub station: String,
    pub station_type: String,
    pub system: String,
    pub dist_ly: f64,
    pub price: i64,
    pub supply: i64,
    pub age_days: Option<i64>,
}

#[derive(Clone, Debug)]
pub enum Tritium {
    Waiting,
    Searching,
    Found(Quote),
    NoneNear,
    Failed(String),
}

pub struct Market {
    tx: Sender<[f64; 3]>,
    rx: Receiver<Tritium>,
}

impl Market {
    pub fn start() -> Market {
        let (tx, rx_in) = mpsc::channel::<[f64; 3]>();
        let (tx_out, rx) = mpsc::channel();
        let _ = std::thread::Builder::new().name("market".into()).spawn(move || {
            while let Ok(mut pos) = rx_in.recv() {
                while let Ok(newer) = rx_in.try_recv() {
                    pos = newer;
                }
                if tx_out.send(fetch(pos)).is_err() {
                    break;
                }
            }
        });
        Market { tx, rx }
    }

    pub fn request(&self, pos: [f64; 3]) {
        let _ = self.tx.send(pos);
    }

    pub fn drain(&self) -> Option<Tritium> {
        self.rx.try_iter().last()
    }
}

fn fetch(pos: [f64; 3]) -> Tritium {
    match query(pos) {
        Ok(Some(q)) => Tritium::Found(q),
        Ok(None) => Tritium::NoneNear,
        Err(e) => Tritium::Failed(e),
    }
}

fn query(pos: [f64; 3]) -> Result<Option<Quote>, String> {
    let now = SystemTime::now();
    let since = now - Duration::from_secs(FRESH_DAYS * 86_400);
    let body = json!({
        "filters": {
            "market": [{"name": COMMODITY, "supply": {"value": ["1", "999999999"], "comparison": "<=>"}}],
            "distance": {"min": "0", "max": RADIUS_LY.to_string()},
            "market_updated_at": {"value": [utc_iso_at(since), utc_iso_at(now)], "comparison": "<=>"},
            "type": {"value": STATION_TYPES}
        },
        "sort": [{"market_buy_price": [{"name": COMMODITY, "direction": "asc"}]}, {"distance": {"direction": "asc"}}],
        "size": 1,
        "page": 0,
        "reference_coords": {"x": pos[0], "y": pos[1], "z": pos[2]}
    });
    let text = ureq::post(URL)
        .timeout(TIMEOUT)
        .set("User-Agent", AGENT)
        .set("Content-Type", "application/json")
        .send_string(&body.to_string())
        .map_err(|e| e.to_string())?
        .into_string()
        .map_err(|e| e.to_string())?;
    let v: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let Some(r) = v["results"].as_array().and_then(|a| a.first()) else { return Ok(None) };
    let Some(m) = r["market"].as_array().and_then(|m| m.iter().find(|c| c["commodity"] == COMMODITY)) else {
        return Ok(None);
    };
    let now_days = now.duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64 / 86_400).unwrap_or(0);
    Ok(Some(Quote {
        station: r["name"].as_str().unwrap_or_default().to_string(),
        station_type: r["type"].as_str().unwrap_or_default().to_string(),
        system: r["system_name"].as_str().unwrap_or_default().to_string(),
        dist_ly: r["distance"].as_f64().unwrap_or(0.0),
        price: m["buy_price"].as_i64().unwrap_or(0),
        supply: m["supply"].as_i64().unwrap_or(0),
        age_days: r["market_updated_at"].as_str().and_then(days_since_epoch).map(|d| now_days - d),
    }))
}

fn days_since_epoch(iso: &str) -> Option<i64> {
    let y: i64 = iso.get(0..4)?.parse().ok()?;
    let m: i64 = iso.get(5..7)?.parse().ok()?;
    let d: i64 = iso.get(8..10)?.parse().ok()?;
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    Some(era * 146_097 + doe - 719_468)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts_days_from_the_epoch() {
        assert_eq!(days_since_epoch("1970-01-01T00:00:00Z"), Some(0));
        assert_eq!(days_since_epoch("2026-10-17T06:20:20Z"), Some(20_743));
        assert_eq!(days_since_epoch("2000-03-01"), Some(11_017));
    }
}
