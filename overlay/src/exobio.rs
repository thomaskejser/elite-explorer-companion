use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Value, json};

use crate::database::{ExoBodyRow, ExoSystemRow};
use crate::lookup::BioBody;
use crate::table::light_years;
use crate::theme::Role;

const BIO: &str = "$SAA_SignalType_Biological;";
pub const NEARBY_ROWS: i64 = 8;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Body {
    pub name: String,
    pub cls: Option<String>,
    pub atmo: Option<String>,
    pub temp: Option<f64>,
    pub bio: i64,
    pub logged: BTreeSet<String>,
    pub footfalled: Option<bool>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Here {
    pub address: Option<i64>,
    pub system: Option<String>,
    pub star: Option<String>,
    pending: Option<(i64, String)>,
    pub bodies: BTreeMap<i64, Body>,
}

fn id(e: &Value, key: &str) -> Option<i64> {
    e.get(key).and_then(Value::as_i64)
}

fn text<'a>(e: &'a Value, key: &str) -> Option<&'a str> {
    e.get(key).and_then(Value::as_str)
}

impl Here {
    fn body(&mut self, e: &Value, key: &str) -> Option<&mut Body> {
        if id(e, "SystemAddress").is_none() || id(e, "SystemAddress") != self.address {
            return None;
        }
        let body = self.bodies.entry(id(e, key)?).or_default();
        if let Some(name) = text(e, "BodyName") {
            body.name = name.to_string();
        }
        Some(body)
    }

    pub fn fold(&mut self, e: &Value) -> bool {
        match text(e, "event").unwrap_or("") {
            "StartJump" if text(e, "JumpType") == Some("Hyperspace") => {
                if let (Some(a), Some(c)) = (id(e, "SystemAddress"), text(e, "StarClass")) {
                    self.pending = Some((a, c.to_string()));
                }
                false
            }
            "FSDJump" | "CarrierJump" | "Location" => {
                let address = id(e, "SystemAddress");
                if address.is_none() || address == self.address {
                    return false;
                }
                let star = self.pending.take().filter(|(a, _)| Some(*a) == address).map(|(_, c)| c);
                *self = Here { address, system: text(e, "StarSystem").map(String::from), star, ..Here::default() };
                true
            }
            "Scan" if text(e, "StarType").is_some() => {
                let arrival = e.get("DistanceFromArrivalLS").and_then(Value::as_f64).is_some_and(|d| d < 1e-3);
                if !arrival || id(e, "SystemAddress") != self.address || self.address.is_none() {
                    return false;
                }
                let star = text(e, "StarType").map(String::from);
                let changed = star != self.star;
                self.star = star;
                changed
            }
            "Scan" if text(e, "PlanetClass").is_some() => {
                let Some(body) = self.body(e, "BodyID") else { return false };
                let before = body.clone();
                body.cls = text(e, "PlanetClass").map(String::from);
                body.atmo = text(e, "Atmosphere").filter(|a| !a.is_empty()).map(String::from);
                body.temp = e.get("SurfaceTemperature").and_then(Value::as_f64);
                body.footfalled = e.get("WasFootfalled").and_then(Value::as_bool);
                *body != before
            }
            "FSSBodySignals" | "SAASignalsFound" => {
                let count = e.get("Signals").and_then(Value::as_array).and_then(|s| {
                    s.iter().find(|s| text(s, "Type") == Some(BIO)).and_then(|s| id(s, "Count"))
                });
                let Some(body) = self.body(e, "BodyID") else { return false };
                let bio = count.unwrap_or(0);
                let changed = body.bio != bio;
                body.bio = bio;
                changed
            }
            "ScanOrganic" if text(e, "ScanType") == Some("Analyse") => {
                let species = text(e, "Species").map(String::from);
                let Some(body) = self.body(e, "Body") else { return false };
                species.is_some_and(|s| body.logged.insert(s))
            }
            _ => false,
        }
    }

    pub fn seed(&mut self, known: &[BioBody]) -> bool {
        let mut changed = false;
        for k in known {
            let body = self.bodies.entry(k.id).or_default();
            let before = body.clone();
            if body.name.is_empty() {
                body.name = k.name.clone();
            }
            if body.cls.is_none() {
                body.cls = k.cls.clone();
                body.atmo = k.atmo.clone();
                body.temp = k.temp;
            }
            if body.bio == 0 {
                body.bio = k.bio;
            }
            changed |= *body != before;
        }
        changed
    }

    pub fn json(&self) -> String {
        let prefix = self.system.as_deref().map(|s| format!("{s} ")).unwrap_or_default();
        let bodies: Vec<Value> = self
            .bodies
            .values()
            .filter(|b| b.bio > 0)
            .map(|b| {
                let short = b.name.strip_prefix(&prefix).unwrap_or(&b.name);
                json!({
                    "body": short,
                    "cls": b.cls,
                    "atmo": b.atmo,
                    "temp": b.temp,
                    "bio": b.bio,
                    "logged": b.logged.len(),
                    "footfalled": b.footfalled,
                })
            })
            .collect();
        Value::Array(bodies).to_string()
    }
}

pub fn credits(cr: Option<f64>) -> String {
    match cr {
        Some(v) if v >= 1e9 => format!("{:.1}G", v / 1e9),
        Some(v) if v >= 1e6 => format!("{:.1}M", v / 1e6),
        Some(v) if v > 0.0 => format!("{:.0}k", v / 1e3),
        _ => "-".to_string(),
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Sheet {
    pub title: String,
    pub heads: Vec<&'static str>,
    pub right: Vec<bool>,
    pub rows: Vec<(Vec<String>, Role)>,
}

pub fn here_sheet(system: Option<&str>, rows: &[ExoBodyRow]) -> Option<Sheet> {
    if rows.is_empty() {
        return None;
    }
    Some(Sheet {
        title: format!("Here: {}", system.unwrap_or("")),
        heads: vec!["BODY", "BIO", "VALUE", "LIKELY"],
        right: vec![false, true, true, false],
        rows: rows
            .iter()
            .map(|r| {
                let role = match (r.logged >= r.bio, r.footfalled) {
                    (true, _) => Role::Dim,
                    (false, Some(false)) => Role::Confirmed,
                    _ => Role::Fg,
                };
                let bio = if r.logged > 0 { format!("{}/{}", r.logged, r.bio) } else { r.bio.to_string() };
                let body = if r.footfalled == Some(false) { format!("{} FF", r.body) } else { r.body.clone() };
                (vec![body, bio, credits(r.cr), r.likely.clone().unwrap_or_default()], role)
            })
            .collect(),
    })
}

fn bodies_text(r: &ExoSystemRow) -> String {
    if r.unmapped > 0 { format!("{}/{}", r.unmapped, r.candidates) } else { r.candidates.to_string() }
}

fn system_role(r: &ExoSystemRow) -> Role {
    if r.worked > 0 { Role::Dim } else { Role::Fg }
}

pub fn target_line(r: &ExoSystemRow) -> (String, Role) {
    let mut parts = vec![format!("Biology {} in {} bodies", credits(Some(r.cr as f64)), bodies_text(r))];
    if let Some(best) = &r.best_body {
        match &r.best_species {
            Some(s) => parts.push(format!("best {best}: {s}")),
            None => parts.push(format!("best {best}")),
        }
    }
    if let Some(y) = r.reported {
        parts.push(format!("last seen {y}"));
    }
    (parts.join(" -- "), system_role(r))
}

pub fn nearby_sheet(rows: &[ExoSystemRow], range_ly: f64) -> Option<Sheet> {
    if rows.is_empty() {
        return None;
    }
    Some(Sheet {
        title: format!("Unlogged biology within {} ly", light_years(range_ly)),
        heads: vec!["SYSTEM", "LY", "VALUE", "BODIES", "SEEN"],
        right: vec![false, true, true, true, true],
        rows: rows
            .iter()
            .map(|r| {
                (
                    vec![
                        r.system.clone(),
                        r.ly.map_or(String::new(), light_years),
                        credits(Some(r.cr as f64)),
                        bodies_text(r),
                        r.reported.map_or(String::new(), |y| y.to_string()),
                    ],
                    system_role(r),
                )
            })
            .collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ev(s: &str) -> Value {
        serde_json::from_str(s).unwrap()
    }

    #[test]
    fn seeds_unscanned_bodies_and_lets_the_journal_win() {
        let mut h = Here::default();
        assert!(h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"X","SystemAddress":7}"#)));
        assert!(h.fold(&ev(r#"{"event":"Scan","BodyName":"X 1 a","BodyID":3,"SystemAddress":7,"PlanetClass":"Rocky body","Atmosphere":"thin ammonia atmosphere","SurfaceTemperature":165.0,"WasFootfalled":false}"#)));
        let known = |id: i64, name: &str| BioBody {
            id,
            name: name.into(),
            cls: Some("Icy body".into()),
            atmo: Some("thin neon atmosphere".into()),
            temp: Some(60.0),
            bio: 2,
        };
        assert!(h.seed(&[known(3, "X 1 a"), known(5, "X 2")]));
        assert_eq!(h.bodies[&3].cls.as_deref(), Some("Rocky body"));
        assert_eq!(h.bodies[&3].bio, 2);
        assert_eq!(h.bodies[&5].name, "X 2");
        assert!(!h.seed(&[known(3, "X 1 a"), known(5, "X 2")]));
        assert!(h.json().contains(r#""body":"2""#));
    }

    #[test]
    fn folds_a_system_from_jump_to_logged_species() {
        let mut h = Here::default();
        assert!(!h.fold(&ev(r#"{"event":"StartJump","JumpType":"Hyperspace","StarSystem":"X","SystemAddress":7,"StarClass":"K"}"#)));
        assert!(h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"X","SystemAddress":7}"#)));
        assert_eq!(h.star.as_deref(), Some("K"));
        assert!(h.fold(&ev(r#"{"event":"FSSBodySignals","BodyName":"X 1 a","BodyID":3,"SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":2}]}"#)));
        assert!(h.fold(&ev(r#"{"event":"Scan","BodyName":"X 1 a","BodyID":3,"SystemAddress":7,"PlanetClass":"Rocky body","Atmosphere":"thin carbon dioxide atmosphere","SurfaceTemperature":171.5,"WasFootfalled":false}"#)));
        assert!(h.fold(&ev(r#"{"event":"ScanOrganic","ScanType":"Analyse","Species":"$Codex_Ent_Stratum_07_Name;","SystemAddress":7,"Body":3}"#)));
        assert!(!h.fold(&ev(r#"{"event":"ScanOrganic","ScanType":"Analyse","Species":"$Codex_Ent_Stratum_07_Name;","SystemAddress":7,"Body":3}"#)));
        let b = &h.bodies[&3];
        assert_eq!((b.bio, b.logged.len(), b.footfalled), (2, 1, Some(false)));
        let j: Value = serde_json::from_str(&h.json()).unwrap();
        assert_eq!(j[0]["body"], "1 a");
        assert_eq!(j[0]["atmo"], "thin carbon dioxide atmosphere");
    }

    #[test]
    fn ignores_other_systems_and_keeps_bodies_on_a_relog() {
        let mut h = Here::default();
        h.fold(&ev(r#"{"event":"Location","StarSystem":"X","SystemAddress":7}"#));
        h.fold(&ev(r#"{"event":"FSSBodySignals","BodyID":3,"BodyName":"X 3","SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":1}]}"#));
        assert!(!h.fold(&ev(r#"{"event":"FSSBodySignals","BodyID":4,"BodyName":"Y 4","SystemAddress":8,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":5}]}"#)));
        assert!(!h.fold(&ev(r#"{"event":"Location","StarSystem":"X","SystemAddress":7}"#)));
        assert_eq!(h.bodies.len(), 1);
        assert!(h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"Z","SystemAddress":9}"#)));
        assert!(h.bodies.is_empty());
        assert_eq!(h.star, None);
        assert_eq!(h.json(), "[]");
    }

    #[test]
    fn takes_the_arrival_star_from_its_scan() {
        let mut h = Here::default();
        h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"X","SystemAddress":7}"#));
        assert!(!h.fold(&ev(r#"{"event":"Scan","StarType":"M","DistanceFromArrivalLS":120.0,"SystemAddress":7}"#)));
        assert!(h.fold(&ev(r#"{"event":"Scan","StarType":"F","DistanceFromArrivalLS":0.0,"SystemAddress":7}"#)));
        assert_eq!(h.star.as_deref(), Some("F"));
    }

    #[test]
    fn formats_credits() {
        assert_eq!(credits(Some(19_010_800.0)), "19.0M");
        assert_eq!(credits(Some(1_260_000_000.0)), "1.3G");
        assert_eq!(credits(Some(119_037.0)), "119k");
        assert_eq!(credits(None), "-");
    }

    fn system(worked: i64, unmapped: i64) -> ExoSystemRow {
        ExoSystemRow {
            system: "S".into(),
            ly: Some(12.4),
            cr: 45_000_000,
            candidates: 5,
            unmapped,
            worked,
            best_body: None,
            best_species: None,
            reported: Some(2019),
        }
    }

    #[test]
    fn dims_a_worked_system_and_shows_known_signals() {
        let s = nearby_sheet(&[system(0, 2), system(1, 0)], 250.0).unwrap();
        assert_eq!(s.rows[0].0, vec!["S", "12", "45.0M", "2/5", "2019"]);
        assert_eq!(s.rows[0].1, Role::Fg);
        assert_eq!(s.rows[1].0[3], "5");
        assert_eq!(s.rows[1].1, Role::Dim);
        assert!(nearby_sheet(&[], 250.0).is_none());
        let (line, role) = target_line(&system(0, 2));
        assert_eq!(role, Role::Fg);
        assert!(line.starts_with("Biology 45.0M in 2/5 bodies"), "{line}");
        assert!(line.ends_with("last seen 2019"), "{line}");
        assert_eq!(target_line(&system(1, 0)).1, Role::Dim);
    }

    #[test]
    fn marks_first_footfall_and_finished_bodies() {
        let row = |logged, footfalled| ExoBodyRow {
            body: "1 a".into(),
            bio: 2,
            logged,
            footfalled,
            cr: Some(30e6),
            likely: Some("Stratum Tectonicas 60%".into()),
        };
        let s = here_sheet(Some("X"), &[row(0, Some(false)), row(1, Some(true)), row(2, Some(false))]).unwrap();
        assert_eq!(s.rows[0].0[0], "1 a FF");
        assert_eq!(s.rows[0].1, Role::Confirmed);
        assert_eq!((s.rows[1].0[1].as_str(), s.rows[1].1), ("1/2", Role::Fg));
        assert_eq!(s.rows[2].1, Role::Dim);
        assert!(here_sheet(Some("X"), &[]).is_none());
    }
}
