#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Verdict {
    Green,
    GreenLowConfidence,
    NotGreen,
    Unpredictable,
}

impl Verdict {
    pub fn is_green(self) -> bool {
        matches!(self, Verdict::Green | Verdict::GreenLowConfidence)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Kind {
    ClassI,
    ClassII,
    ClassIII,
    ClassIV,
    ClassV,
    Helium,
    WaterGiant,
    AmmoniaLife,
    WaterLife,
}

const COLD_CRACKS: [f64; 7] = [115.0, 250.0, 270.0, 370.0, 700.0, 900.0, 1400.0];
const CRACKS: [f64; 7] = [114.0, 210.0, 270.0, 370.0, 700.0, 900.0, 1400.0];
const CEILINGS: [(f64, f64); 5] = [(75.0, 100.0), (330.0, 340.0), (680.0, 700.0), (900.0, 1200.0), (1400.0, 1500.0)];
const TOP_CEILING: f64 = 5000.0;
const CLASS_III_MIN_STEP: f64 = 30.0;
const NUDGE_FROM: f64 = 80.0;
const NUDGE_BELOW: f64 = 122.0;
const EARTH_KG: f64 = 5.97219e24;
const RUNGS: usize = 7;

fn kind(class: &str) -> Option<Kind> {
    let c = class.to_lowercase().replace('-', " ");
    Some(match () {
        _ if c.contains("helium") => Kind::Helium,
        _ if c.contains("water giant") => Kind::WaterGiant,
        _ if c.contains("ammonia") && c.contains("life") => Kind::AmmoniaLife,
        _ if c.contains("water") && c.contains("life") => Kind::WaterLife,
        _ if c.contains("class v") => Kind::ClassV,
        _ if c.contains("class iv") => Kind::ClassIV,
        _ if c.contains("class iii") => Kind::ClassIII,
        _ if c.contains("class ii") => Kind::ClassII,
        _ if c.contains("class i") => Kind::ClassI,
        _ => return None,
    })
}

fn cracks(kind: Kind) -> &'static [f64] {
    match kind {
        Kind::ClassI | Kind::AmmoniaLife => &COLD_CRACKS,
        _ => &CRACKS,
    }
}

fn ceiling(t: f64) -> f64 {
    CEILINGS.iter().find(|(below, _)| t < *below).map_or(TOP_CEILING, |(_, c)| *c)
}

fn min_step(kind: Kind) -> Option<f64> {
    (kind == Kind::ClassIII).then_some(CLASS_III_MIN_STEP)
}

fn nudged(kind: Kind, t: f64) -> bool {
    let cold_below = match kind {
        Kind::ClassII => 280.0,
        Kind::ClassIII => 415.0,
        Kind::ClassIV => 700.0,
        Kind::ClassV => 1500.0,
        _ => f64::NEG_INFINITY,
    };
    (NUDGE_FROM..NUDGE_BELOW).contains(&t) || t < cold_below
}

fn confirmed(kind: Kind) -> bool {
    !matches!(kind, Kind::ClassII | Kind::ClassV | Kind::Helium)
}

fn density(mass_em: f64, radius_m: f64) -> Option<f64> {
    (mass_em > 0.0 && radius_m > 0.0).then(|| mass_em * EARTH_KG / (4.0 / 3.0 * std::f64::consts::PI * radius_m.powi(3)))
}

fn depth(t: f64, density: f64) -> f64 {
    5.0 / 9.0 * 1300.0 * (t / 1300.0).powf(1.2) * density.powf(0.2)
}

#[derive(Clone, Copy, PartialEq)]
enum Landing {
    On,
    OneOff,
    Off,
}

fn ulps_to_nearest_crack(t: f64, top: f64, min_step: Option<f64>, cracks: &[f64]) -> u32 {
    let t = t as f32 as f64;
    let step = ((top - t) / RUNGS as f64).max(min_step.unwrap_or(f64::NEG_INFINITY));
    (0..RUNGS)
        .flat_map(|k| {
            let rung = (t + k as f64 * step) as f32;
            cracks.iter().map(move |&c| rung.to_bits().abs_diff((c as f32).to_bits()))
        })
        .min()
        .unwrap_or(u32::MAX)
}

fn landing(kind: Kind, t: f64, reach: f64) -> Landing {
    let ceiling = ceiling(t);
    let one_off_counts = t + reach < ceiling && min_step(kind).is_none();
    match ulps_to_nearest_crack(t, (t + reach).min(ceiling), min_step(kind), cracks(kind)) {
        0 => Landing::On,
        1 if one_off_counts => Landing::OneOff,
        _ => Landing::Off,
    }
}

pub fn predict(class: &str, temp_k: f64, mass_em: f64, radius_m: f64) -> Verdict {
    let Some(kind) = kind(class) else { return Verdict::Unpredictable };
    let Some(rho) = density(mass_em, radius_m) else { return Verdict::Unpredictable };
    let nudged = nudged(kind, temp_k);
    match (landing(kind, temp_k, depth(temp_k, rho)), nudged) {
        (Landing::On, false) if confirmed(kind) => Verdict::Green,
        (Landing::On | Landing::OneOff, _) => Verdict::GreenLowConfidence,
        (Landing::Off, true) => Verdict::Unpredictable,
        (Landing::Off, false) => Verdict::NotGreen,
    }
}

pub fn is_green_codex(name: &str) -> bool {
    name.starts_with("$Codex_Ent_Green_")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_nudged_giant_off_a_crack_is_unpredictable() {
        assert_eq!(predict("Sudarsky class II gas giant", 166.724182, 95.072899, 52542176.0), Verdict::Unpredictable);
        assert_eq!(predict("Sudarsky class I gas giant", 100.0, 300.0, 70_000_000.0), Verdict::Unpredictable);
        assert_eq!(predict("Sudarsky class V gas giant", 1000.0, 300.0, 70_000_000.0), Verdict::Unpredictable);
        assert_eq!(predict("High metal content body", 200.0, 1.0, 6_000_000.0), Verdict::Unpredictable);
    }

    #[test]
    fn a_rung_on_a_crack_is_green_and_one_off_it_is_not() {
        assert_eq!(predict("Sudarsky class III gas giant", 640.0, 400.0, 70_000_000.0), Verdict::Green);
        assert_eq!(predict("Sudarsky class III gas giant", 640.0001, 400.0, 70_000_000.0), Verdict::NotGreen);
        assert_eq!(predict("Gas giant with water based life", 176.666702, 408.532623, 75062848.0), Verdict::Green);
        assert_eq!(predict("Gas giant with water based life", 176.666626, 408.532623, 75062848.0), Verdict::NotGreen);
        assert_eq!(predict("Sudarsky class I gas giant", 136.361237, 28.92416, 34730648.0), Verdict::NotGreen);
    }

    #[test]
    fn a_nudged_giant_on_a_crack_could_be_green() {
        assert_eq!(predict("Sudarsky class III gas giant", 370.0, 400.0, 70_000_000.0), Verdict::GreenLowConfidence);
    }

    #[test]
    fn a_ladder_topping_out_at_its_reach_lands_exactly_on_its_crack() {
        assert_eq!(predict("Sudarsky class I gas giant", 133.998352, 220.366837, 66635716.0), Verdict::Green);
        assert_eq!(predict("Sudarsky class I gas giant", 133.998367, 220.366837, 66635716.0), Verdict::GreenLowConfidence);
        assert_eq!(predict("Sudarsky class I gas giant", 133.9984, 220.366837, 66635716.0), Verdict::NotGreen);
    }

    #[test]
    fn a_class_i_below_75_k_never_reaches_a_crack() {
        assert_eq!(predict("Sudarsky class I gas giant", 56.0, 4000.0, 30_000_000.0), Verdict::NotGreen);
    }

    #[test]
    fn every_catalogued_green_gas_giant_reads_green_or_could_be() {
        let rows: Vec<(String, Verdict)> = catalogue().into_iter().map(|(n, c, t, m, r)| (n, predict(&c, t, m, r))).collect();
        let missed: Vec<&str> = rows.iter().filter(|(_, v)| *v == Verdict::NotGreen).map(|(n, _)| n.as_str()).collect();
        let count = |v: Verdict| rows.iter().filter(|(_, r)| *r == v).count();
        assert!(missed.is_empty(), "of {} catalogued, read not green: {missed:?}", rows.len());
        assert_eq!(
            [count(Verdict::Green), count(Verdict::GreenLowConfidence), count(Verdict::Unpredictable)],
            [37, 6, 26],
            "green, low confidence, unpredictable"
        );
    }

    fn catalogue() -> Vec<(String, String, f64, f64, f64)> {
        include_str!("../assets/green_gas_giants.csv")
            .lines()
            .skip(1)
            .map(|line| {
                let (name, rest) = line.trim_start_matches('"').split_once("\",").unwrap();
                let f: Vec<&str> = rest.split(',').collect();
                let num = |i: usize| f[i].parse::<f64>().unwrap();
                (name.to_string(), f[0].to_string(), num(1), num(2), num(3) * 1000.0)
            })
            .collect()
    }

    fn label(v: Verdict) -> &'static str {
        match v {
            Verdict::Green => "GREEN",
            Verdict::GreenLowConfidence => "GREEN_LOW_CONFIDENCE",
            Verdict::NotGreen => "NOT_GREEN",
            Verdict::Unpredictable => "UNPREDICTABLE",
        }
    }

    #[test]
    fn the_sql_macros_the_etl_predicts_with_agree_with_this_predictor() {
        let con = duckdb::Connection::open_in_memory().unwrap();
        con.execute_batch(include_str!("../../schema/macro/ggg.sql")).unwrap();
        let classes = [
            "Sudarsky class I gas giant", "Sudarsky class II gas giant", "Sudarsky class III gas giant", "Sudarsky class IV gas giant",
            "Sudarsky class V gas giant", "Helium rich gas giant", "Water giant", "Gas giant with ammonia based life",
            "Gas giant with water based life", "Class III gas giant", "Gas giant with water-based life",
        ];
        let borders = [114.0, 115.0, 130.0, 158.0, 176.666702, 210.0, 217.5, 242.0, 250.0, 270.0, 370.0, 520.0, 550.0, 580.0, 610.0, 640.0, 670.0, 700.0, 780.0, 900.0, 1150.0, 1400.0];
        let mut seed: u64 = 7;
        let mut next = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 11) as f64 / (1u64 << 53) as f64
        };
        let mut cases: Vec<(String, f64, f64, f64)> = catalogue().into_iter().map(|(_, c, t, m, r)| (c, t, m, r)).collect();
        for i in 0..4000 {
            let class = classes[i % classes.len()].to_string();
            let t = if i % 2 == 0 { 50.0 + next() * 1550.0 } else { borders[(next() * borders.len() as f64) as usize] + [0.0, 0.0, 1e-5, -1e-5, 0.5][i % 5] };
            cases.push((class, t, 5.0 + next() * 4000.0, 2.0e7 + next() * 6.0e7));
        }
        con.execute_batch("CREATE TABLE cases (i INTEGER, class VARCHAR, t DOUBLE, m DOUBLE, r DOUBLE)").unwrap();
        {
            let mut app = con.appender("cases").unwrap();
            for (i, (class, t, m, r)) in cases.iter().enumerate() {
                app.append_row(duckdb::params![i as i32, class, t, m, r]).unwrap();
            }
        }
        let mut stmt = con.prepare("SELECT ggg_verdict(class, t, m, r) FROM cases ORDER BY i").unwrap();
        let sql: Vec<String> = stmt.query_map([], |row| row.get(0)).unwrap().map(Result::unwrap).collect();
        let mut seen = std::collections::BTreeMap::new();
        for ((class, t, m, r), sql) in cases.iter().zip(&sql) {
            let rust = label(predict(class, *t, *m, *r));
            assert_eq!(sql, rust, "{class} {t} K {m} EM {r} m");
            *seen.entry(rust).or_insert(0) += 1;
        }
        assert_eq!(sql.len(), cases.len());
        assert_eq!(seen.len(), 4, "every verdict exercised: {seen:?}");
    }

    #[test]
    fn the_green_codex_entries_are_recognised_by_name() {
        assert!(is_green_codex("$Codex_Ent_Green_Sudarsky_Class_II_Name;"));
        assert!(!is_green_codex("$Codex_Ent_Sudarsky_Class_II_Name;"));
    }
}
