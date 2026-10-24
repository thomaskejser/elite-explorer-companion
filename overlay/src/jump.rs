use crate::journal::Hop;
use crate::kinds;
use crate::lookup::SystemInfo;
use crate::table::thousands;
use crate::theme::Role;

const SCOOPABLE: &str = "KGBFOAM";

#[derive(Clone, Debug, PartialEq)]
pub struct Leg {
    pub ly: f64,
    pub scoopable: bool,
    pub boosted: bool,
    pub flown: bool,
    pub next: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Panel {
    pub target: String,
    pub class: Option<String>,
    pub class_role: Role,
    pub star: String,
    pub hop: usize,
    pub hops: usize,
    pub total_ly: f64,
    pub legs: Vec<Leg>,
    pub lines: Vec<(String, Role)>,
}

pub fn scoopable(class: Option<&str>) -> bool {
    class.and_then(|c| c.chars().next()).is_some_and(|c| SCOOPABLE.contains(c))
}

fn dist(a: &Hop, b: &Hop) -> Option<f64> {
    let d = [b.x? - a.x?, b.y? - a.y?, b.z? - a.z?];
    Some((d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt())
}

pub fn class_role(class: Option<&str>) -> Role {
    match class {
        Some(c) if kinds::is_rare_class(c) => Role::Confirmed,
        Some("N") => Role::Neutron,
        Some(c) if scoopable(Some(c)) => Role::Carrier,
        _ => Role::Warn,
    }
}

pub fn star_name(class: &str) -> String {
    let named = match class {
        "O" => "O (Blue-White) Star",
        "B" => "B (Blue-White) Star",
        "A" => "A (Blue-White) Star",
        "F" => "F (White) Star",
        "G" => "G (White-Yellow) Star",
        "K" => "K (Yellow-Orange) Star",
        "M" => "M (Red dwarf) Star",
        "L" => "L (Brown dwarf) Star",
        "T" => "T (Brown dwarf) Star",
        "Y" => "Y (Brown dwarf) Star",
        "TTS" => "T Tauri Star",
        "AeBe" => "Herbig Ae/Be Star",
        "W" => "Wolf-Rayet Star",
        "WN" => "Wolf-Rayet N Star",
        "WNC" => "Wolf-Rayet NC Star",
        "WC" => "Wolf-Rayet C Star",
        "WO" => "Wolf-Rayet O Star",
        "C" => "C Star",
        "CN" => "CN Star",
        "CJ" => "CJ Star",
        "CH" => "CH Star",
        "CHd" => "CHd Star",
        "CS" => "CS Star",
        "MS" => "MS-type Star",
        "S" => "S-type Star",
        "N" => "Neutron Star",
        "H" => "Black Hole",
        "SupermassiveBlackHole" => "Supermassive Black Hole",
        "X" => "Exotic",
        "O_BlueWhiteSuperGiant" => "O (Blue-White super giant) Star",
        "B_BlueWhiteSuperGiant" => "B (Blue-White super giant) Star",
        "A_BlueWhiteSuperGiant" => "A (Blue-White super giant) Star",
        "F_WhiteSuperGiant" => "F (White super giant) Star",
        "G_WhiteSuperGiant" => "G (White-Yellow super giant) Star",
        "K_OrangeGiant" => "K (Yellow-Orange giant) Star",
        "M_RedGiant" => "M (Red giant) Star",
        "M_RedSuperGiant" => "M (Red super giant) Star",
        c if c.starts_with('D') => return format!("White Dwarf ({c}) Star"),
        c => return c.to_string(),
    };
    named.to_string()
}

pub fn star_text(class: Option<&str>, info: Option<&SystemInfo>) -> String {
    let name = info.and_then(|i| i.main_star.clone()).or_else(|| class.map(star_name)).unwrap_or_default();
    match info.and_then(|i| i.spectral.as_deref()) {
        Some(s) => format!("{name}  {s}"),
        None => name,
    }
}

pub fn build(route: &[Hop], target: &str, target_class: Option<&str>, max_jump: Option<f64>) -> Panel {
    let at = route.iter().skip(1).position(|h| h.system == target).map(|i| i + 1);
    let class = target_class.map(String::from).or_else(|| at.and_then(|i| route[i].star_class.clone()));
    let mut panel = Panel {
        target: target.to_string(),
        class_role: class_role(class.as_deref()),
        star: class.as_deref().map(star_name).unwrap_or_default(),
        class,
        hop: 1,
        hops: 1,
        total_ly: 0.0,
        legs: Vec::new(),
        lines: Vec::new(),
    };
    let Some(at) = at else {
        panel.legs.push(Leg { ly: 1.0, scoopable: scoopable(target_class), boosted: false, flown: false, next: true });
        return panel;
    };
    panel.legs = route
        .windows(2)
        .enumerate()
        .filter_map(|(i, w)| {
            let ly = dist(&w[0], &w[1])?;
            Some(Leg {
                ly,
                scoopable: scoopable(w[1].star_class.as_deref()),
                boosted: max_jump.is_some_and(|m| ly > m + 0.01),
                flown: i + 1 < at,
                next: i + 1 == at,
            })
        })
        .collect();
    panel.hop = at;
    panel.hops = route.len() - 1;
    panel.total_ly = panel.legs.iter().map(|l| l.ly).sum();
    panel
}

pub fn info_lines(info: Option<&SystemInfo>, class: Option<&str>) -> Vec<(String, Role)> {
    let rare = class.filter(|c| kinds::is_rare_class(c)).and_then(kinds::key_of_class).map(|k| kinds::by_key(k).abbr.to_string());
    let Some(info) = info else {
        return rare.map(|r| vec![(format!("{r} -- looking up whether anybody has scanned it"), Role::Confirmed)]).unwrap_or_default();
    };
    let mut lines = Vec::new();
    match (&info.discovered_by, info.bodies) {
        (_, 0) => lines.push((
            match &rare {
                Some(r) => format!("Undiscovered system -- {r}, a first discovery"),
                None => "Undiscovered system".to_string(),
            },
            if rare.is_some() { Role::Confirmed } else { Role::Neutron },
        )),
        (Some((cmdr, date)), _) => lines.push((format!("Discovered by {cmdr} {date}"), Role::Carrier)),
        (None, _) => lines.push(("Scanned, discoverer not reported".to_string(), Role::Carrier)),
    }
    let counts: Vec<String> = [
        ("Bodies", info.bodies),
        ("Bio", info.bio),
        ("Geo", info.geo),
        ("Stations", info.stations),
        ("Carriers", info.carriers),
    ]
    .into_iter()
    .filter(|(_, n)| *n > 0)
    .map(|(k, n)| format!("{k}: {n}"))
    .collect();
    if let Some([day, week, total]) = info.traffic {
        lines.push((format!("Traffic last 24 hours: {day}, week: {week}, ever: {total} (EDSM)"), Role::Carrier));
    }
    if !counts.is_empty() {
        lines.push((counts.join("  \u{00B7}  "), Role::Dim));
    }
    lines
}

pub fn total_text(ly: f64) -> String {
    format!("{}ly", thousands(ly, 1))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hop(name: &str, class: &str, x: f64) -> Hop {
        Hop { system: name.into(), star_class: Some(class.into()), x: Some(x), y: Some(0.0), z: Some(0.0), id64: None }
    }

    #[test]
    fn places_the_target_and_marks_legs() {
        let route = vec![hop("A", "K", 0.0), hop("B", "N", 60.0), hop("C", "M", 300.0), hop("D", "L", 340.0)];
        let p = build(&route, "C", None, Some(50.0));
        assert_eq!((p.hop, p.hops), (2, 3));
        assert_eq!(p.total_ly, 340.0);
        assert_eq!(p.class.as_deref(), Some("M"));
        assert_eq!(p.legs.iter().map(|l| (l.flown, l.next, l.boosted, l.scoopable)).collect::<Vec<_>>(), vec![
            (true, false, true, false),
            (false, true, true, true),
            (false, false, false, false),
        ]);
    }

    #[test]
    fn spells_out_the_star() {
        assert_eq!(star_name("DA"), "White Dwarf (DA) Star");
        assert_eq!(star_name("AeBe"), "Herbig Ae/Be Star");
        assert_eq!(star_text(Some("K"), None), "K (Yellow-Orange) Star");
        let info = SystemInfo { spectral: Some("A9 VI".into()), ..SystemInfo::default() };
        assert_eq!(star_text(Some("N"), Some(&info)), "Neutron Star  A9 VI");
    }

    #[test]
    fn a_target_off_the_route_is_one_leg() {
        let p = build(&[hop("A", "K", 0.0)], "Z", Some("H"), None);
        assert_eq!((p.hop, p.hops, p.legs.len()), (1, 1, 1));
        assert_eq!(p.class_role, Role::Confirmed);
    }

    #[test]
    fn an_unscanned_rare_star_reads_as_a_find() {
        let info = SystemInfo::default();
        let lines = info_lines(Some(&info), Some("H"));
        assert!(lines[0].0.starts_with("Undiscovered system"));
        assert_eq!(lines[0].1, Role::Confirmed);
        let seen = SystemInfo { bodies: 5, discovered_by: Some(("x".into(), "2021-04-22".into())), ..SystemInfo::default() };
        assert_eq!(info_lines(Some(&seen), Some("K"))[0].0, "Discovered by x 2021-04-22");
    }
}
