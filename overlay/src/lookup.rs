use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

use serde_json::Value;

const AGENT: &str = concat!("explorers-companion/", env!("CARGO_PKG_VERSION"));
const EDSM_BODIES: &str = "https://www.edsm.net/api-system-v1/bodies";
const EDSM_SYSTEM: &str = "https://www.edsm.net/api-v1/system";
const SPANSH_DUMP: &str = "https://spansh.co.uk/api/dump";
const TIMEOUT: Duration = Duration::from_secs(20);
const BIO: &str = "$SAA_SignalType_Biological;";
const GEO: &str = "$SAA_SignalType_Geological;";

#[derive(Clone, Debug, Default, PartialEq)]
pub struct SystemInfo {
    pub bodies: usize,
    pub discovered_by: Option<(String, String)>,
    pub bio: usize,
    pub bio_bodies: usize,
    pub geo: usize,
    pub worlds: [usize; 3],
    pub stations: usize,
    pub carriers: usize,
    pub open_carriers: usize,
    pub main_star: Option<String>,
    pub spectral: Option<String>,
    pub exo: Vec<BioBody>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct BioBody {
    pub id: i64,
    pub name: String,
    pub cls: Option<String>,
    pub atmo: Option<String>,
    pub temp: Option<f64>,
    pub bio: i64,
}

fn journal_atmosphere(spansh: &str) -> Option<String> {
    let a = spansh.to_lowercase().replace('-', " ").replace("sulphur", "sulfur");
    (a.starts_with("thin ")).then(|| format!("{a} atmosphere"))
}

struct Worker<Q, A> {
    tx: Sender<Q>,
    rx: Receiver<(String, A)>,
}

impl<Q: Send + 'static, A: Send + 'static> Worker<Q, A> {
    fn start(name: &str, work: fn(&Q) -> (String, A)) -> Worker<Q, A> {
        let (tx, rx_in) = mpsc::channel::<Q>();
        let (tx_out, rx) = mpsc::channel();
        let _ = std::thread::Builder::new().name(name.into()).spawn(move || {
            while let Ok(q) = rx_in.recv() {
                if tx_out.send(work(&q)).is_err() {
                    break;
                }
            }
        });
        Worker { tx, rx }
    }

    fn take(&self) -> Vec<(String, A)> {
        self.rx.try_iter().collect()
    }
}

pub struct Lookup(Worker<(String, Option<i64>), Result<SystemInfo, String>>);

impl Lookup {
    pub fn start() -> Lookup {
        Lookup(Worker::start("lookup", |(name, id64)| (name.clone(), fetch(name, *id64))))
    }

    pub fn ask(&self, name: &str, id64: Option<i64>) {
        let _ = self.0.tx.send((name.to_string(), id64));
    }

    pub fn take(&self) -> Vec<(String, Result<SystemInfo, String>)> {
        self.0.take()
    }
}

pub type Located = Result<Option<[f64; 3]>, String>;

pub struct Locate(Worker<String, Located>);

impl Locate {
    pub fn start() -> Locate {
        Locate(Worker::start("locate", |name| (name.clone(), locate(name))))
    }

    pub fn ask(&self, name: &str) {
        let _ = self.0.tx.send(name.to_string());
    }

    pub fn take(&self) -> Vec<(String, Located)> {
        self.0.take()
    }
}

fn locate(name: &str) -> Located {
    let got = get(&format!("{EDSM_SYSTEM}?systemName={}&showCoordinates=1", encode(name)))?;
    Ok(got.as_ref().and_then(coords))
}

fn coords(system: &Value) -> Option<[f64; 3]> {
    let c = system.get("coords")?;
    Some([c.get("x")?.as_f64()?, c.get("y")?.as_f64()?, c.get("z")?.as_f64()?])
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
    let is_carrier = |s: &&Value| s["type"].as_str().is_some_and(|t| t.contains("Carrier"));
    let carriers = stations.iter().filter(is_carrier).count();
    let open_carriers = stations.iter().filter(is_carrier).filter(|s| s["carrierDockingAccess"].as_str() == Some("All")).count();
    SystemInfo {
        bodies: e_count.max(e_bodies.len()).max(s_bodies.len()),
        discovered_by,
        bio: signals(BIO),
        bio_bodies: s_bodies.iter().filter(|b| b["signals"]["signals"][BIO].as_u64().unwrap_or(0) > 0).count(),
        geo: signals(GEO),
        worlds: ["Earth-like world", "Water world", "Ammonia world"].map(|t| s_bodies.iter().filter(|b| b["subType"].as_str() == Some(t)).count()),
        stations: stations.len() - carriers,
        carriers,
        open_carriers,
        main_star: main.and_then(|b| b["subType"].as_str()).map(String::from),
        spectral,
        exo: s_bodies
            .iter()
            .filter_map(|b| {
                let bio = b["signals"]["signals"][BIO].as_i64().filter(|n| *n > 0)?;
                Some(BioBody {
                    id: b["bodyId"].as_i64()?,
                    name: b["name"].as_str()?.to_string(),
                    cls: b["subType"].as_str().map(String::from),
                    atmo: b["atmosphereType"].as_str().and_then(journal_atmosphere),
                    temp: b["surfaceTemperature"].as_f64(),
                    bio,
                })
            })
            .collect(),
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
        let spansh = json!({"bodies": [{"bodyId": 4, "name": "X 1 a", "subType": "High metal content world",
                                        "atmosphereType": "Thin Sulphur dioxide", "surfaceTemperature": 171.5,
                                        "signals": {"signals": {BIO: 2, GEO: 1}}}, {}],
                            "stations": [{"type": "Drake-Class Carrier", "carrierDockingAccess": "All"},
                                         {"type": "Drake-Class Carrier", "carrierDockingAccess": "Friends"},
                                         {"type": "Outpost", "carrierDockingAccess": "All"}]});
        let i = merge(Some(&edsm), Some(&spansh));
        assert_eq!(i.bodies, 3);
        assert_eq!(i.discovered_by, Some(("harryboa".into(), "2021-04-22".into())));
        assert_eq!((i.bio, i.bio_bodies, i.geo, i.stations, i.carriers, i.open_carriers), (2, 1, 1, 1, 2, 1));
        assert_eq!(i.main_star.as_deref(), Some("A (Blue-White) Star"));
        assert_eq!(i.spectral.as_deref(), Some("A9 VI"));
        assert_eq!(i.exo.len(), 1);
        assert_eq!((i.exo[0].id, i.exo[0].bio), (4, 2));
        assert_eq!(i.exo[0].atmo.as_deref(), Some("thin sulfur dioxide atmosphere"));
        assert_eq!(journal_atmosphere("No atmosphere"), None);
        assert_eq!(journal_atmosphere("Thin Neon-rich").as_deref(), Some("thin neon rich atmosphere"));
    }

    #[test]
    fn reads_edsm_coordinates() {
        let found: Value = serde_json::from_str(r#"{"name":"Colonia","coords":{"x":-9530.5,"y":-910.28125,"z":19808.125}}"#).unwrap();
        assert_eq!(coords(&found), Some([-9530.5, -910.28125, 19808.125]));
        assert_eq!(coords(&serde_json::from_str::<Value>("[]").unwrap()), None);
    }

    #[test]
    fn an_unknown_system_has_nothing() {
        assert_eq!(merge(Some(&json!({})), None), SystemInfo::default());
        assert_eq!(encode("Thailoi RK-V d3-13"), "Thailoi%20RK-V%20d3-13");
    }
}
