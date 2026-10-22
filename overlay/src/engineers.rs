use std::collections::BTreeMap;
use std::sync::OnceLock;

use crate::database::TradeRow;

const CSV: &str = include_str!("../assets/engineers.csv");
const FIELDS: usize = 8;
const GRADE: &str = "G5";

struct Engineer {
    module: String,
    engineer: String,
    system: String,
    station: String,
    arrival_ls: f64,
    pos: [f64; 3],
}

fn parse() -> Vec<Engineer> {
    CSV.lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|line| {
            let f: Vec<&str> = line.trim_end().split(',').collect();
            assert_eq!(f.len(), FIELDS, "assets/engineers.csv: {line}");
            let num = |s: &str| s.parse::<f64>().unwrap_or_else(|_| panic!("assets/engineers.csv: {line}"));
            Engineer {
                module: f[0].to_string(),
                engineer: f[1].to_string(),
                system: f[2].to_string(),
                station: f[3].to_string(),
                arrival_ls: num(f[4]),
                pos: [num(f[5]), num(f[6]), num(f[7])],
            }
        })
        .collect()
}

fn engineers() -> &'static [Engineer] {
    static ALL: OnceLock<Vec<Engineer>> = OnceLock::new();
    ALL.get_or_init(parse)
}

pub fn nearest(pos: [f64; 3]) -> Vec<TradeRow> {
    let mut best: BTreeMap<&str, (f64, &Engineer)> = BTreeMap::new();
    for e in engineers() {
        let d = e.pos.iter().zip(pos).map(|(a, b)| (a - b).powi(2)).sum::<f64>().sqrt();
        if best.get(e.module.as_str()).is_none_or(|(old, _)| d < *old) {
            best.insert(&e.module, (d, e));
        }
    }
    best.into_values()
        .map(|(d, e)| TradeRow {
            kind: format!("{GRADE} {}", e.module),
            system: e.system.clone(),
            station: format!("{} ({})", e.engineer, e.station),
            dist_ly: Some(d),
            arrival_ls: Some(e.arrival_ls),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_row_parses_and_each_module_gets_one_engineer() {
        let all = engineers();
        assert!(all.len() > 40);
        let modules: std::collections::BTreeSet<&str> = all.iter().map(|e| e.module.as_str()).collect();
        let rows = nearest([0.0, 0.0, 0.0]);
        assert_eq!(rows.len(), modules.len());
        let fsd = rows.iter().find(|r| r.kind == "G5 Frame shift drive").unwrap();
        assert_eq!(fsd.system, "Deciat");
        let colonia = nearest([-9530.5, -910.28125, 19808.125]);
        let fsd = colonia.iter().find(|r| r.kind == "G5 Frame shift drive").unwrap();
        assert_eq!(fsd.system, "Luchtaine");
    }
}
