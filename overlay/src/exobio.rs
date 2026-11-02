use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Value, json};

use crate::bands::Family;
use crate::database::{ExoSystemRow, GenusOdds, SystemBodyRow, SystemMap};
use crate::lookup::KnownBody;
use crate::table::light_years;
use crate::theme::{CLOCK_TEXT, Rgb, Role};

const BIO: &str = "$SAA_SignalType_Biological;";
const GEO: &str = "$SAA_SignalType_Geological;";
pub const NEARBY_ROWS: i64 = 8;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Body {
    pub name: String,
    pub cls: Option<String>,
    pub atmo: Option<String>,
    pub temp: Option<f64>,
    pub ls: Option<f64>,
    pub landable: Option<bool>,
    pub volcanism: Option<String>,
    pub known: bool,
    pub bio: i64,
    pub geo: i64,
    pub genera: BTreeSet<String>,
    pub logged: BTreeSet<String>,
    pub logged_genera: BTreeSet<String>,
    pub footfalled: Option<bool>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Here {
    pub address: Option<i64>,
    pub system: Option<String>,
    pub star: Option<String>,
    pending: Option<(i64, String)>,
    pub bodies: BTreeMap<i64, Body>,
    pub body_count: Option<i64>,
    pub complete: bool,
}

fn id(e: &Value, key: &str) -> Option<i64> {
    e.get(key).and_then(Value::as_i64)
}

fn text<'a>(e: &'a Value, key: &str) -> Option<&'a str> {
    e.get(key).and_then(Value::as_str)
}

impl Here {
    pub fn at(address: i64, system: &str) -> Here {
        Here { address: Some(address), system: Some(system.to_string()), ..Here::default() }
    }

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
                body.ls = e.get("DistanceFromArrivalLS").and_then(Value::as_f64);
                body.landable = e.get("Landable").and_then(Value::as_bool);
                body.volcanism = text(e, "Volcanism").filter(|v| !v.is_empty()).map(String::from);
                body.known = true;
                body.footfalled = e.get("WasFootfalled").and_then(Value::as_bool);
                *body != before
            }
            "FSSBodySignals" | "SAASignalsFound" => {
                let count = |kind: &str| {
                    e.get("Signals")
                        .and_then(Value::as_array)
                        .and_then(|s| s.iter().find(|s| text(s, "Type") == Some(kind)).and_then(|s| id(s, "Count")))
                        .unwrap_or(0)
                };
                let (bio, geo) = (count(BIO), count(GEO));
                let genera: BTreeSet<String> = e
                    .get("Genuses")
                    .and_then(Value::as_array)
                    .map(|g| g.iter().filter_map(|g| text(g, "Genus_Localised").or_else(|| text(g, "Genus"))).map(String::from).collect())
                    .unwrap_or_default();
                let Some(body) = self.body(e, "BodyID") else { return false };
                let before = body.clone();
                (body.bio, body.geo, body.known) = (bio, geo, true);
                if !genera.is_empty() {
                    body.genera = genera;
                }
                *body != before
            }
            "FSSAllBodiesFound" if id(e, "SystemAddress") == self.address && self.address.is_some() => {
                let changed = !self.complete;
                self.complete = true;
                changed
            }
            "FSSDiscoveryScan" if id(e, "SystemAddress") == self.address && self.address.is_some() => {
                let count = id(e, "BodyCount");
                let changed = count != self.body_count;
                self.body_count = count;
                changed
            }
            "CodexEntry" => id(e, "SystemAddress").is_some() && id(e, "SystemAddress") == self.address,
            "ScanOrganic" if text(e, "ScanType") == Some("Analyse") => {
                let species = text(e, "Species").map(String::from);
                let genus = text(e, "Genus_Localised").or_else(|| text(e, "Genus")).map(String::from);
                let Some(body) = self.body(e, "Body") else { return false };
                let added = genus.is_some_and(|g| body.logged_genera.insert(g));
                species.is_some_and(|s| body.logged.insert(s)) || added
            }
            _ => false,
        }
    }

    pub fn scanned_with_atmosphere(&self) -> Vec<&str> {
        self.bodies.values().filter(|b| b.atmo.as_deref().is_some_and(|a| !a.is_empty())).filter_map(|b| b.cls.as_deref()).collect()
    }

    pub fn worlds(&self) -> [usize; 3] {
        ["Earthlike body", "Water world", "Ammonia world"].map(|c| self.bodies.values().filter(|b| b.cls.as_deref() == Some(c)).count())
    }

    pub fn signals(&self) -> (usize, i64, i64) {
        let bio_bodies = self.bodies.values().filter(|b| b.bio > 0).count();
        (bio_bodies, self.bodies.values().map(|b| b.bio).sum(), self.bodies.values().map(|b| b.geo).sum())
    }

    pub fn seed(&mut self, known: &[KnownBody]) -> bool {
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
                body.landable = k.landable;
                body.volcanism = k.volcanism.clone();
            }
            body.ls = body.ls.or(k.ls);
            body.known |= k.known;
            if body.bio == 0 {
                body.bio = k.bio;
            }
            if body.geo == 0 {
                body.geo = k.geo;
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
            .map(|b| {
                let short = b.name.strip_prefix(&prefix).unwrap_or(&b.name);
                json!({
                    "body": short,
                    "cls": b.cls,
                    "atmo": b.atmo,
                    "temp": b.temp,
                    "ls": b.ls,
                    "landable": b.landable,
                    "volcanism": b.volcanism,
                    "known": b.known,
                    "bio": b.bio,
                    "geo": b.geo,
                    "genera": b.genera,
                    "logged": b.logged.len(),
                    "logged_genera": b.logged_genera,
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
    pub tints: Vec<(usize, usize, Rgb)>,
}

impl Sheet {
    pub fn rgb(&self, row: usize, col: usize) -> Rgb {
        self.tints.iter().find(|(r, c, _)| (*r, *c) == (row, col)).map_or(self.rows[row].1.rgb(), |(.., rgb)| *rgb)
    }
}

pub fn geo_rgb(new: bool) -> Rgb {
    if new { Role::Confirmed.rgb() } else { CLOCK_TEXT }
}

fn bio_text(r: &SystemBodyRow) -> Option<String> {
    (r.genera.is_empty() && r.bio > r.logged).then(|| if r.logged == 0 { r.bio.to_string() } else { format!("{}/{}", r.logged, r.bio) })
}

fn genus_text(g: &GenusOdds) -> String {
    match g.chance {
        Some(p) => format!("{:.0}%", p * 100.0),
        None => credits(g.cr),
    }
}

fn family_of(kind: &str) -> Family {
    match kind {
        "Earth-like" => Family::EarthLike,
        "Water world" => Family::Water,
        "Ammonia world" => Family::Ammonia,
        "Icy" | "Rocky ice" => Family::Ice,
        k if k.contains("giant") => Family::Gas,
        _ => Family::Rock,
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct BodyLine {
    pub family: Family,
    pub name: String,
    pub flag: bool,
    pub genera: Vec<(String, String)>,
    pub bio: Option<String>,
    pub geo: Option<(String, Rgb)>,
    pub value: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct BodyList {
    pub title: String,
    pub total: String,
    pub lines: Vec<BodyLine>,
}

pub fn body_list(system: Option<&str>, map: &SystemMap) -> Option<BodyList> {
    if map.bodies.is_empty() {
        return None;
    }
    let lines = map
        .bodies
        .iter()
        .map(|r| BodyLine {
            family: family_of(&r.kind),
            name: r.body.to_uppercase(),
            flag: r.first_footfall,
            genera: r.genera.iter().map(|g| (g.genus.clone(), genus_text(g))).collect(),
            bio: bio_text(r),
            geo: (r.geo > 0).then(|| (r.geo.to_string(), geo_rgb(r.geo_new == Some(true)))),
            value: r.cr.filter(|v| *v > 0.0).map_or_else(String::new, |v| credits(Some(v))),
        })
        .collect();
    let total: f64 = map.bodies.iter().filter_map(|r| r.cr).sum();
    Some(BodyList { title: format!("Targets: {}", system.unwrap_or("")), total: credits(Some(total)), lines })
}

pub fn system_sheets(map: &SystemMap) -> Vec<Sheet> {
    if map.pois.is_empty() {
        return Vec::new();
    }
    vec![Sheet {
        title: "Points of interest".to_string(),
        heads: vec!["POI", "CLASS"],
        right: vec![false, false],
        rows: map.pois.iter().map(|(poi, class)| (vec![poi.clone(), class.clone()], Role::Poi)).collect(),
        tints: Vec::new(),
    }]
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
        heads: vec!["SEEN", "BODIES", "VALUE", "SYSTEM", "LY"],
        right: vec![true, true, true, false, true],
        rows: rows
            .iter()
            .map(|r| {
                (
                    vec![
                        r.reported.map_or(String::new(), |y| y.to_string()),
                        bodies_text(r),
                        credits(Some(r.cr as f64)),
                        r.system.clone(),
                        r.ly.map_or(String::new(), light_years),
                    ],
                    system_role(r),
                )
            })
            .collect(),
        tints: Vec::new(),
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
        let known = |id: i64, name: &str| KnownBody {
            id,
            name: name.into(),
            cls: Some("Icy body".into()),
            atmo: Some("thin neon atmosphere".into()),
            temp: Some(60.0),
            ls: Some(410.0),
            known: true,
            bio: 2,
            geo: 1,
            ..KnownBody::default()
        };
        assert!(h.seed(&[known(3, "X 1 a"), known(5, "X 2")]));
        assert_eq!(h.bodies[&3].cls.as_deref(), Some("Rocky body"));
        assert_eq!(h.bodies[&3].bio, 2);
        assert_eq!(h.bodies[&5].name, "X 2");
        assert_eq!((h.bodies[&5].geo, h.bodies[&5].ls, h.bodies[&5].known), (1, Some(410.0), true));
        assert!(!h.seed(&[known(3, "X 1 a"), known(5, "X 2")]));
        assert!(h.json().contains(r#""body":"2""#));
    }

    #[test]
    fn the_honk_counts_bodies_in_this_system_only() {
        let mut h = Here::default();
        h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"X","SystemAddress":7}"#));
        assert!(h.fold(&ev(r#"{"event":"FSSDiscoveryScan","SystemAddress":7,"BodyCount":12}"#)));
        assert_eq!(h.body_count, Some(12));
        h.fold(&ev(r#"{"event":"FSSBodySignals","BodyID":3,"SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":2},{"Type":"$SAA_SignalType_Geological;","Count":3}]}"#));
        h.fold(&ev(r#"{"event":"FSSBodySignals","BodyID":4,"SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Geological;","Count":1}]}"#));
        assert_eq!(h.signals(), (1, 2, 4));
        h.fold(&ev(r#"{"event":"Scan","BodyName":"X 2","BodyID":5,"SystemAddress":7,"PlanetClass":"Water world"}"#));
        assert_eq!(h.worlds(), [0, 1, 0]);
        assert!(h.fold(&ev(r#"{"event":"FSSAllBodiesFound","SystemAddress":7,"Count":12}"#)));
        assert!(h.complete);
        assert!(!h.fold(&ev(r#"{"event":"FSSDiscoveryScan","SystemAddress":8,"BodyCount":3}"#)));
        h.fold(&ev(r#"{"event":"FSDJump","StarSystem":"Y","SystemAddress":8}"#));
        assert_eq!(h.body_count, None);
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
    fn keeps_volcanism_and_wakes_on_a_codex_entry_here() {
        let mut h = Here::at(7, "X");
        h.fold(&ev(r#"{"event":"Scan","BodyName":"X 1","BodyID":3,"SystemAddress":7,"PlanetClass":"Icy body","Volcanism":"major water geysers volcanism"}"#));
        h.fold(&ev(r#"{"event":"Scan","BodyName":"X 2","BodyID":4,"SystemAddress":7,"PlanetClass":"Icy body","Volcanism":""}"#));
        assert_eq!(h.bodies[&3].volcanism.as_deref(), Some("major water geysers volcanism"));
        assert_eq!(h.bodies[&4].volcanism, None);
        assert!(h.fold(&ev(r#"{"event":"CodexEntry","Name":"$Codex_Ent_IceGeysers_WaterGeysers_Name;","SystemAddress":7}"#)));
        assert!(!h.fold(&ev(r#"{"event":"CodexEntry","Name":"$Codex_Ent_IceGeysers_WaterGeysers_Name;","SystemAddress":8}"#)));
    }

    #[test]
    fn keeps_the_genera_a_surface_scan_names() {
        let mut h = Here::at(7, "X");
        assert!(h.fold(&ev(r#"{"event":"SAASignalsFound","BodyName":"X 1","BodyID":3,"SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":2}],"Genuses":[{"Genus":"$Codex_Ent_Bacterial_Genus_Name;","Genus_Localised":"Bacterium"},{"Genus":"$Codex_Ent_Stratum_Genus_Name;","Genus_Localised":"Stratum"}]}"#)));
        let b = &h.bodies[&3];
        assert_eq!((b.bio, b.known), (2, true));
        assert_eq!(b.genera.iter().cloned().collect::<Vec<_>>(), vec!["Bacterium", "Stratum"]);
        assert!(!h.fold(&ev(r#"{"event":"FSSBodySignals","BodyName":"X 1","BodyID":3,"SystemAddress":7,"Signals":[{"Type":"$SAA_SignalType_Biological;","Count":2}]}"#)));
        assert_eq!(h.bodies[&3].genera.len(), 2);
        let j: Value = serde_json::from_str(&h.json()).unwrap();
        assert_eq!(j[0]["genera"], json!(["Bacterium", "Stratum"]));
    }

    fn target(body: &str) -> SystemBodyRow {
        SystemBodyRow { body: body.into(), kind: "Rocky".into(), ls: Some(1234.4), ..SystemBodyRow::default() }
    }

    #[test]
    fn lists_each_body_with_its_genera_flag_geology_and_value() {
        let g = |genus: &str, chance: Option<f64>, cr: Option<f64>| GenusOdds { genus: genus.into(), chance, cr };
        let map = SystemMap {
            bodies: vec![
                SystemBodyRow {
                    bio: 3,
                    logged: 1,
                    first_footfall: true,
                    cr: Some(14_500_000.0),
                    genera: vec![g("Stratum", None, Some(12_400_000.0)), g("Bacterium", None, Some(2_100_000.0))],
                    ..target("1 a")
                },
                SystemBodyRow { chance: Some(0.6), kind: "Icy".into(), genera: vec![g("Bacterium", Some(0.53), Some(1_000_000.0))], ..target("2") },
                SystemBodyRow { geo: 4, geo_new: Some(true), kind: "HMC".into(), ..target("4") },
                SystemBodyRow { bio: 2, kind: "Water world".into(), cr: Some(3_000_000.0), ..target("6") },
            ],
            pois: vec![("Guardian Codex".into(), "guardian, on a surface".into())],
        };
        let list = body_list(Some("X"), &map).unwrap();
        assert_eq!((list.title.as_str(), list.total.as_str()), ("Targets: X", "17.5M"));
        let l = &list.lines;
        assert_eq!((l[0].family, l[0].name.as_str(), l[0].flag), (Family::Rock, "1 A", true));
        assert_eq!(l[0].genera, vec![("Stratum".to_string(), "12.4M".to_string()), ("Bacterium".to_string(), "2.1M".to_string())]);
        assert_eq!((l[0].bio.clone(), l[0].value.as_str()), (None, "14.5M"));
        assert_eq!((l[1].family, l[1].genera.clone(), l[1].value.as_str()), (Family::Ice, vec![("Bacterium".to_string(), "53%".to_string())], ""));
        assert_eq!((l[2].family, l[2].geo.clone()), (Family::Rock, Some(("4".into(), Role::Confirmed.rgb()))));
        assert_eq!((l[3].family, l[3].bio.as_deref()), (Family::Water, Some("2")));
        assert_eq!(system_sheets(&map)[0].rows[0].1, Role::Poi);
        assert_eq!(body_list(Some("X"), &SystemMap::default()), None);
        assert!(system_sheets(&SystemMap::default()).is_empty());
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
        assert_eq!(s.rows[0].0, vec!["2019", "2/5", "45.0M", "S", "12"]);
        assert_eq!(s.rows[0].1, Role::Fg);
        assert_eq!(s.rows[1].0[1], "5");
        assert_eq!(s.rows[1].1, Role::Dim);
        assert!(nearby_sheet(&[], 250.0).is_none());
        let (line, role) = target_line(&system(0, 2));
        assert_eq!(role, Role::Fg);
        assert!(line.starts_with("Biology 45.0M in 2/5 bodies"), "{line}");
        assert!(line.ends_with("last seen 2019"), "{line}");
        assert_eq!(target_line(&system(1, 0)).1, Role::Dim);
    }
}
