use serde_json::Value;

const FSD: &[(&str, f64, f64, f64)] = &[
    ("int_hyperdrive_overcharge_size2_class1", 0.008, 2.0, 0.6),
    ("int_hyperdrive_overcharge_size2_class2", 0.012, 2.0, 0.9),
    ("int_hyperdrive_overcharge_size2_class3", 0.012, 2.0, 0.9),
    ("int_hyperdrive_overcharge_size2_class4", 0.012, 2.0, 0.9),
    ("int_hyperdrive_overcharge_size2_class5", 0.013, 2.0, 1.0),
    ("int_hyperdrive_overcharge_size3_class1", 0.008, 2.15, 1.2),
    ("int_hyperdrive_overcharge_size3_class2", 0.012, 2.15, 1.8),
    ("int_hyperdrive_overcharge_size3_class3", 0.012, 2.15, 1.8),
    ("int_hyperdrive_overcharge_size3_class4", 0.012, 2.15, 1.8),
    ("int_hyperdrive_overcharge_size3_class5", 0.013, 2.15, 1.9),
    ("int_hyperdrive_overcharge_size4_class1", 0.008, 2.3, 2.0),
    ("int_hyperdrive_overcharge_size4_class2", 0.012, 2.3, 3.0),
    ("int_hyperdrive_overcharge_size4_class3", 0.012, 2.3, 3.0),
    ("int_hyperdrive_overcharge_size4_class4", 0.012, 2.3, 3.0),
    ("int_hyperdrive_overcharge_size4_class5", 0.013, 2.3, 3.2),
    ("int_hyperdrive_overcharge_size5_class1", 0.008, 2.45, 3.3),
    ("int_hyperdrive_overcharge_size5_class2", 0.012, 2.45, 5.0),
    ("int_hyperdrive_overcharge_size5_class3", 0.012, 2.45, 5.0),
    ("int_hyperdrive_overcharge_size5_class4", 0.012, 2.45, 5.0),
    ("int_hyperdrive_overcharge_size5_class5", 0.012, 2.45, 5.2),
    ("int_hyperdrive_overcharge_size6_class1", 0.008, 2.6, 5.3),
    ("int_hyperdrive_overcharge_size6_class2", 0.012, 2.6, 8.0),
    ("int_hyperdrive_overcharge_size6_class3", 0.012, 2.6, 8.0),
    ("int_hyperdrive_overcharge_size6_class4", 0.012, 2.6, 8.0),
    ("int_hyperdrive_overcharge_size6_class5", 0.013, 2.6, 8.3),
    ("int_hyperdrive_overcharge_size7_class1", 0.008, 2.75, 8.5),
    ("int_hyperdrive_overcharge_size7_class2", 0.012, 2.75, 12.8),
    ("int_hyperdrive_overcharge_size7_class3", 0.012, 2.75, 12.8),
    ("int_hyperdrive_overcharge_size7_class4", 0.012, 2.75, 12.8),
    ("int_hyperdrive_overcharge_size7_class5", 0.013, 2.75, 13.1),
    ("int_hyperdrive_overcharge_size8_class1", 0.008, 2.9, 13.6),
    ("int_hyperdrive_overcharge_size8_class2", 0.012, 2.9, 20.4),
    ("int_hyperdrive_overcharge_size8_class3", 0.012, 2.9, 20.4),
    ("int_hyperdrive_overcharge_size8_class4", 0.012, 2.9, 20.4),
    ("int_hyperdrive_overcharge_size8_class5", 0.013, 2.9, 20.7),
    ("int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii", 0.011, 2.5025, 6.8),
    ("int_hyperdrive_size2_class1", 0.011, 2.0, 0.6),
    ("int_hyperdrive_size2_class2", 0.01, 2.0, 0.6),
    ("int_hyperdrive_size2_class3", 0.008, 2.0, 0.6),
    ("int_hyperdrive_size2_class4", 0.01, 2.0, 0.8),
    ("int_hyperdrive_size2_class5", 0.012, 2.0, 0.9),
    ("int_hyperdrive_size3_class1", 0.011, 2.15, 1.2),
    ("int_hyperdrive_size3_class2", 0.01, 2.15, 1.2),
    ("int_hyperdrive_size3_class3", 0.008, 2.15, 1.2),
    ("int_hyperdrive_size3_class4", 0.01, 2.15, 1.5),
    ("int_hyperdrive_size3_class5", 0.012, 2.15, 1.8),
    ("int_hyperdrive_size4_class1", 0.011, 2.3, 2.0),
    ("int_hyperdrive_size4_class2", 0.01, 2.3, 2.0),
    ("int_hyperdrive_size4_class3", 0.008, 2.3, 2.0),
    ("int_hyperdrive_size4_class4", 0.01, 2.3, 2.5),
    ("int_hyperdrive_size4_class5", 0.012, 2.3, 3.0),
    ("int_hyperdrive_size5_class1", 0.011, 2.45, 3.3),
    ("int_hyperdrive_size5_class2", 0.01, 2.45, 3.3),
    ("int_hyperdrive_size5_class3", 0.008, 2.45, 3.3),
    ("int_hyperdrive_size5_class4", 0.01, 2.45, 4.1),
    ("int_hyperdrive_size5_class5", 0.012, 2.45, 5.0),
    ("int_hyperdrive_size6_class1", 0.011, 2.6, 5.3),
    ("int_hyperdrive_size6_class2", 0.01, 2.6, 5.3),
    ("int_hyperdrive_size6_class3", 0.008, 2.6, 5.3),
    ("int_hyperdrive_size6_class4", 0.01, 2.6, 6.6),
    ("int_hyperdrive_size6_class5", 0.012, 2.6, 8.0),
    ("int_hyperdrive_size7_class1", 0.011, 2.75, 8.5),
    ("int_hyperdrive_size7_class2", 0.01, 2.75, 8.5),
    ("int_hyperdrive_size7_class3", 0.008, 2.75, 8.5),
    ("int_hyperdrive_size7_class4", 0.01, 2.75, 10.6),
    ("int_hyperdrive_size7_class5", 0.012, 2.75, 12.8),
    ("int_missing_hyperdrive", 0.0, 0.0, 0.0),
];

const BOOSTER: &[(&str, f64)] = &[
    ("int_guardianfsdbooster_size1", 4.0),
    ("int_guardianfsdbooster_size2", 6.0),
    ("int_guardianfsdbooster_size3", 7.75),
    ("int_guardianfsdbooster_size4", 9.25),
    ("int_guardianfsdbooster_size5", 10.5),
];

const DEFAULT_NEUTRON_BOOST: f64 = 4.0;
const SHIP_NEUTRON_BOOST: &[(&str, f64)] = &[("explorer_nx", 6.0)];

pub fn neutron_boost(loadout: Option<&Value>) -> f64 {
    let ship = loadout.and_then(|l| l.get("Ship")).and_then(Value::as_str);
    SHIP_NEUTRON_BOOST
        .iter()
        .find(|(s, _)| Some(*s) == ship)
        .map_or(DEFAULT_NEUTRON_BOOST, |(_, b)| *b)
}

fn modules(loadout: &Value) -> impl Iterator<Item = &Value> {
    loadout.get("Modules").and_then(Value::as_array).into_iter().flatten()
}

fn item(module: &Value) -> String {
    module.get("Item").and_then(Value::as_str).unwrap_or("").to_lowercase()
}

pub fn jump_range(loadout: &Value) -> Option<f64> {
    let mut spec = None;
    let mut optmass = None;
    let mut boost = 0.0;
    for m in modules(loadout) {
        let name = item(m);
        if let Some(&(_, fuelmul, fuelpower, maxfuel)) = FSD.iter().find(|(n, ..)| *n == name) {
            spec = Some((fuelmul, fuelpower, maxfuel));
            optmass = m
                .get("Engineering")
                .and_then(|e| e.get("Modifiers"))
                .and_then(Value::as_array)
                .and_then(|mods| {
                    mods.iter()
                        .find(|d| d.get("Label").and_then(Value::as_str) == Some("FSDOptimalMass"))
                })
                .and_then(|d| d.get("Value"))
                .and_then(Value::as_f64);
        }
        boost += BOOSTER.iter().find(|(n, _)| *n == name).map_or(0.0, |(_, b)| *b);
    }
    let (fuelmul, fuelpower, maxfuel) = spec?;
    let optmass = optmass?;
    let capacity = loadout.get("FuelCapacity");
    let tank = capacity.and_then(|c| c.get("Main")).and_then(Value::as_f64)?;
    let reserve = capacity.and_then(|c| c.get("Reserve")).and_then(Value::as_f64).unwrap_or(0.0);
    let unladen = loadout.get("UnladenMass").and_then(Value::as_f64).filter(|m| *m != 0.0)?;
    let fuel = tank;
    let mass = unladen + fuel + reserve;
    Some(optmass / mass * (maxfuel.min(fuel) / fuelmul).powf(1.0 / fuelpower) + boost)
}

pub fn summary(loadout: &Value) -> Option<String> {
    let laden = jump_range(loadout)?;
    let boost = neutron_boost(Some(loadout));
    let ship = loadout.get("Ship").and_then(Value::as_str).unwrap_or("None");
    Some(format!(
        "jump {laden:.1} ly   neutron {:.0} ly (x{}, {ship})",
        laden * boost,
        fmt_g(boost)
    ))
}

fn fmt_g(v: f64) -> String {
    if v.fract() == 0.0 { format!("{v:.0}") } else { format!("{v}") }
}

pub fn has_shields(loadout: Option<&Value>) -> bool {
    loadout.is_some_and(|l| {
        modules(l).any(|m| m.get("Item").and_then(Value::as_str).unwrap_or("").contains("shieldgenerator"))
    })
}
