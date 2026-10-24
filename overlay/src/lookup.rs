use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

use serde_json::Value;

const AGENT: &str = concat!("explorers-companion/", env!("CARGO_PKG_VERSION"));
const EDSM_BODIES: &str = "https://www.edsm.net/api-system-v1/bodies";
const SPANSH_DUMP: &str = "https://spansh.co.uk/api/dump";
const TIMEOUT: Duration = Duration::from_secs(20);
const BIO: &str = "$SAA_SignalType_Biological;";
const GEO: &str = "$SAA_SignalType_Geological;";

#[derive(Clone, Debug, Default, PartialEq)]
pub struct SystemInfo {
    pub bodies: usize,
    pub discovered_by: Option<(String, String)>,
    pub bio: usize,
    pub geo: usize,
    pub stations: usize,
    pub carriers: usize,
    pub main_star: Option<String>,
    pub spectral: Option<String>,
}

pub struct Lookup {
    tx: Sender<(String, Option<i64>)>,
    rx: Receiver<(String, Result<SystemInfo, String>)>,
}

impl Lookup {
    pub fn start() -> Lookup {
        let (tx, rx_in) = mpsc::channel::<(String, Option<i64>)>();
        let (tx_out, rx) = mpsc::channel();
        let _ = std::thread::Builder::new().name("lookup".into()).spawn(move || {
            while let Ok((name, id64)) = rx_in.recv() {
                let got = fetch(&name, id64);
                if tx_out.send((name, got)).is_err() {
                    break;
                }
            }
        });
        Lookup { tx, rx }
    }

    pub fn ask(&self, name: &str, id64: Option<i64>) {
        let _ = self.tx.send((name.to_string(), id64));
    }

    pub fn take(&self) -> Vec<(String, Result<SystemInfo, String>)> {
        self.rx.try_iter().collect()
    }
}

fn get(url: &str) -> Result<Option<Value>, String> {
    match ureq::get(url).timeout(TIMEOUT).set("User-Agent", AGENT).call() {
        Ok(r) => r.into_string().map_err(|e| e.to_string()).and_then(|t| {
            serde_json::from_str(&t).map(Some).map_err(|e| e.to_string())
        }),
        Err(ureq::Error::Status(404, _)) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

fn fetch(name: &str, id64: Option<i64>) -> Result<SystemInfo, String> {
    let edsm = get(&format!("{EDSM_BODIES}?systemName={}", encode(name)))?;
    let spansh = match id64 {
        Some(id) => get(&format!("{SPANSH_DUMP}/{id}/"))?.map(|v| v["system"].clone()),
        None => None,
    };
    Ok(merge(edsm.as_ref(), spansh.as_ref()))
}

fn encode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => (b as char).to_string(),
            _ => format!("%{b:02X}"),
        })
        .collect()
}

pub fn merge(edsm: Option<&Value>, spansh: Option<&Value>) -> SystemInfo {
    let empty = Vec::new();
    let e_bodies = edsm.and_then(|v| v["bodies"].as_array()).unwrap_or(&empty);
    let s_bodies = spansh.and_then(|v| v["bodies"].as_array()).unwrap_or(&empty);
    let e_count = edsm.and_then(|v| v["bodyCount"].as_u64()).unwrap_or(0) as usize;
    let discovered_by = e_bodies.iter().find_map(|b| {
        let d = &b["discovery"];
        Some((d["commander"].as_str()?.to_string(), d["date"].as_str()?.chars().take(10).collect()))
    });
    let main = e_bodies
        .iter()
        .find(|b| b["isMainStar"].as_bool() == Some(true))
        .or_else(|| s_bodies.iter().find(|b| b["mainStar"].as_bool() == Some(true)));
    let spectral = main.and_then(|b| {
        let parts: Vec<&str> = [b["spectralClass"].as_str(), b["luminosity"].as_str()].into_iter().flatten().collect();
        (!parts.is_empty()).then(|| parts.join(" "))
    });
    let signals = |key: &str| s_bodies.iter().map(|b| b["signals"]["signals"][key].as_u64().unwrap_or(0) as usize).sum();
    let stations = spansh.and_then(|v| v["stations"].as_array()).unwrap_or(&empty);
    let carriers = stations.iter().filter(|s| s["type"].as_str().is_some_and(|t| t.contains("Carrier"))).count();
    SystemInfo {
        bodies: e_count.max(e_bodies.len()).max(s_bodies.len()),
        discovered_by,
        bio: signals(BIO),
        geo: signals(GEO),
        stations: stations.len() - carriers,
        carriers,
        main_star: main.and_then(|b| b["subType"].as_str()).map(String::from),
        spectral,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn merges_both_feeds() {
        let edsm = json!({"bodyCount": 3, "bodies": [
            {"name": "A", "isMainStar": true, "subType": "A (Blue-White) Star", "spectralClass": "A9", "luminosity": "VI"},
            {"discovery": {"commander": "harryboa", "date": "2021-04-22 22:24:24"}}]});
        let spansh = json!({"bodies": [{"signals": {"signals": {BIO: 2, GEO: 1}}}, {}],
                            "stations": [{"type": "Drake-Class Carrier"}, {"type": "Outpost"}]});
        let i = merge(Some(&edsm), Some(&spansh));
        assert_eq!(i.bodies, 3);
        assert_eq!(i.discovered_by, Some(("harryboa".into(), "2021-04-22".into())));
        assert_eq!((i.bio, i.geo, i.stations, i.carriers), (2, 1, 1, 1));
        assert_eq!(i.main_star.as_deref(), Some("A (Blue-White) Star"));
        assert_eq!(i.spectral.as_deref(), Some("A9 VI"));
    }

    #[test]
    fn an_unknown_system_has_nothing() {
        assert_eq!(merge(Some(&json!({})), None), SystemInfo::default());
        assert_eq!(encode("Thailoi RK-V d3-13"), "Thailoi%20RK-V%20d3-13");
    }
}
