use std::collections::BTreeMap;
use std::sync::OnceLock;

use crate::database::TradeRow;
use crate::route::dist;
use crate::table::thousands_i;

const CSV: &str = include_str!("../assets/alien_sites.csv");
const FIELDS: usize = 9;
pub const GUARDIAN: &str = "Guardian";
pub const THARGOID: &str = "Thargoid";

struct Site {
    category: String,
    kind: String,
    system: String,
    body: String,
    reports: i64,
    last_reported: String,
    pos: [f64; 3],
}

fn parse() -> Vec<Site> {
    CSV.lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|line| {
            let f: Vec<&str> = line.trim_end().split(',').collect();
            assert_eq!(f.len(), FIELDS, "assets/alien_sites.csv: {line}");
            let num = |s: &str| s.parse::<f64>().unwrap_or_else(|_| panic!("assets/alien_sites.csv: {line}"));
            Site {
                category: f[0].to_string(),
                kind: f[1].to_string(),
                system: f[2].to_string(),
                body: f[3].to_string(),
                reports: num(f[4]) as i64,
                last_reported: f[5].to_string(),
                pos: [num(f[6]), num(f[7]), num(f[8])],
            }
        })
        .collect()
}

fn sites() -> &'static [Site] {
    static ALL: OnceLock<Vec<Site>> = OnceLock::new();
    ALL.get_or_init(parse)
}

pub fn nearest(pos: [f64; 3], category: &str) -> Vec<TradeRow> {
    let mut best: BTreeMap<&str, (f64, &Site)> = BTreeMap::new();
    for s in sites().iter().filter(|s| s.category == category) {
        let d = dist(&s.pos, &pos);
        if best.get(s.kind.as_str()).is_none_or(|(old, _)| d < *old) {
            best.insert(&s.kind, (d, s));
        }
    }
    best.into_values()
        .map(|(d, s)| TradeRow {
            kind: s.kind.clone(),
            system: s.system.clone(),
            station: s.body.clone(),
            dist_ly: Some(d),
            arrival_ls: None,
            note: Some(format!("{} report(s), last {}", thousands_i(s.reports), s.last_reported)),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_nearest_site_per_kind_in_each_category() {
        for category in [GUARDIAN, THARGOID] {
            let kinds: std::collections::BTreeSet<&str> =
                sites().iter().filter(|s| s.category == category).map(|s| s.kind.as_str()).collect();
            let rows = nearest([0.0, 0.0, 0.0], category);
            assert!(!rows.is_empty());
            assert_eq!(rows.len(), kinds.len());
            assert!(rows.iter().all(|r| r.dist_ly.unwrap() >= 0.0 && !r.station.is_empty()));
        }
        let guardian = nearest([0.0, 0.0, 0.0], GUARDIAN);
        assert!(guardian.iter().any(|r| r.kind == "Guardian Data Terminal (blueprints)"));
        assert!(guardian.iter().all(|r| r.kind.starts_with("Guardian")));
        assert!(nearest([0.0, 0.0, 0.0], "Nothing").is_empty());
    }
}
