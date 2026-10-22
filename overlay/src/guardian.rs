use std::collections::BTreeMap;
use std::sync::OnceLock;

use crate::database::TradeRow;
use crate::route::dist;

const CSV: &str = include_str!("../assets/guardian_sites.csv");
const FIELDS: usize = 7;

struct Site {
    kind: String,
    system: String,
    body: String,
    pos: [f64; 3],
}

fn parse() -> Vec<Site> {
    CSV.lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|line| {
            let f: Vec<&str> = line.trim_end().split(',').collect();
            assert_eq!(f.len(), FIELDS, "assets/guardian_sites.csv: {line}");
            let num = |s: &str| s.parse::<f64>().unwrap_or_else(|_| panic!("assets/guardian_sites.csv: {line}"));
            Site { kind: f[0].to_string(), system: f[1].to_string(), body: f[2].to_string(), pos: [num(f[4]), num(f[5]), num(f[6])] }
        })
        .collect()
}

fn sites() -> &'static [Site] {
    static ALL: OnceLock<Vec<Site>> = OnceLock::new();
    ALL.get_or_init(parse)
}

pub fn nearest(pos: [f64; 3]) -> Vec<TradeRow> {
    let mut best: BTreeMap<&str, (f64, &Site)> = BTreeMap::new();
    for s in sites() {
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
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_nearest_site_per_kind() {
        let rows = nearest([0.0, 0.0, 0.0]);
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|r| r.dist_ly.unwrap() > 0.0 && !r.station.is_empty()));
    }
}
