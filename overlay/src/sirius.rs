use std::sync::OnceLock;

use crate::database::TradeRow;

const CSV: &str = include_str!("../assets/sirius_brokers.csv");
const FIELDS: usize = 6;
pub const KIND: &str = "Sirius tech broker";

struct Broker {
    system: String,
    station: String,
    arrival_ls: f64,
    pos: [f64; 3],
}

fn parse() -> Vec<Broker> {
    CSV.lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|line| {
            let f: Vec<&str> = line.trim_end().split(',').collect();
            assert_eq!(f.len(), FIELDS, "assets/sirius_brokers.csv: {line}");
            let num = |s: &str| s.parse::<f64>().unwrap_or_else(|_| panic!("assets/sirius_brokers.csv: {line}"));
            Broker {
                system: f[0].to_string(),
                station: f[1].to_string(),
                arrival_ls: num(f[2]),
                pos: [num(f[3]), num(f[4]), num(f[5])],
            }
        })
        .collect()
}

fn brokers() -> &'static [Broker] {
    static ALL: OnceLock<Vec<Broker>> = OnceLock::new();
    ALL.get_or_init(parse)
}

pub fn nearest(pos: [f64; 3]) -> Option<TradeRow> {
    let dist = |b: &Broker| b.pos.iter().zip(pos).map(|(a, p)| (a - p).powi(2)).sum::<f64>().sqrt();
    brokers().iter().min_by(|a, b| dist(a).total_cmp(&dist(b))).map(|b| TradeRow {
        kind: KIND.to_string(),
        system: b.system.clone(),
        station: b.station.clone(),
        dist_ly: Some(dist(b)),
        arrival_ls: Some(b.arrival_ls),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nearest_to_sol_is_luytens_star() {
        assert_eq!(brokers().len(), 7);
        assert_eq!(nearest([0.0, 0.0, 0.0]).unwrap().system, "Luyten's Star");
        assert_eq!(nearest([360.0, -380.0, -710.0]).unwrap().system, "Siniang");
    }
}
