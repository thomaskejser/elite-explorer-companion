use crate::journal::Hop;
use crate::kinds;
use crate::lookup::SystemInfo;
use crate::theme::{Rgb, Role, kind_colour, star_colour};

const SCOOPABLE: &str = "KGBFOAM";

#[derive(Clone, Debug, PartialEq)]
pub struct Leg {
    pub system: String,
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
    pub class_rgb: Rgb,
    pub star: String,
    pub counts: String,
    pub legs: Vec<Leg>,
    pub discovery: Option<(String, Role)>,
    pub bio: Option<(String, Role)>,
    pub carrier: Option<bool>,
    pub here: Option<String>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct MapRoute {
    pub stops: Vec<[f64; 2]>,
    pub legs: Vec<Leg>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RoutePopup {
    pub title: String,
    pub rows: Vec<(String, String, Rgb)>,
}

pub fn route_popup(route: &[Hop]) -> Option<RoutePopup> {
    let rows: Vec<(String, String, Rgb)> = route
        .iter()
        .skip(1)
        .filter_map(|h| {
            let class = kinds::arrival_class(h.star_class.as_deref()?, &h.system);
            kinds::is_rare_class(class).then(|| (h.system.clone(), star_name(class), target_rgb(Some(class), &h.system)))
        })
        .collect();
    if rows.is_empty() {
        return None;
    }
    let title = match rows.len() {
        1 => "1 target on this route".to_string(),
        n => format!("{n} targets on this route"),
    };
    Some(RoutePopup { title, rows })
}

pub fn scoopable(class: Option<&str>) -> bool {
    class.and_then(|c| c.chars().next()).is_some_and(|c| SCOOPABLE.contains(c))
}

fn dist(a: &Hop, b: &Hop) -> Option<f64> {
    let d = [b.x? - a.x?, b.y? - a.y?, b.z? - a.z?];
    Some((d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt())
}

pub fn target_rgb(class: Option<&str>, system: &str) -> Rgb {
    class
        .map(|c| kinds::arrival_class(c, system))
        .and_then(kinds::key_of_class)
        .and_then(kind_colour)
        .unwrap_or_else(|| class_rgb(class))
}

pub fn class_rgb(class: Option<&str>) -> Rgb {
    match class {
        Some(c) if let Some(rgb) = star_colour(c) => rgb,
        _ => Role::Warn.rgb(),
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
    let text = match info.and_then(|i| i.spectral.as_deref()) {
        Some(s) => format!("{name} {s}"),
        None => name,
    };
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub fn build(route: &[Hop], target: &str, target_class: Option<&str>, max_jump: Option<f64>) -> Panel {
    let at = route.iter().skip(1).position(|h| h.system == target).map(|i| i + 1);
    let class = target_class.map(String::from).or_else(|| at.and_then(|i| route[i].star_class.clone()));
    let mut panel = Panel {
        target: target.to_string(),
        class_rgb: target_rgb(class.as_deref(), target),
        star: class.as_deref().map(star_name).unwrap_or_default(),
        counts: String::new(),
        class,
        legs: Vec::new(),
        discovery: None,
        bio: None,
        carrier: None,
        here: None,
    };
    let Some(at) = at else {
        panel.legs.push(Leg { system: target.to_string(), ly: 0.0, scoopable: scoopable(target_class), boosted: false, flown: false, next: true });
        return panel;
    };
    panel.legs = route
        .windows(2)
        .enumerate()
        .filter_map(|(i, w)| {
            let ly = dist(&w[0], &w[1])?;
            Some(Leg {
                system: w[1].system.clone(),
                ly,
                scoopable: scoopable(w[1].star_class.as_deref()),
                boosted: max_jump.is_some_and(|m| ly > m + 0.01),
                flown: i + 1 < at,
                next: i + 1 == at,
            })
        })
        .collect();
    panel
}

pub fn map_route(route: &[Hop], here: Option<&str>, max_jump: Option<f64>) -> MapRoute {
    let placed: Vec<(&Hop, [f64; 3])> = route.iter().filter_map(|h| Some((h, [h.x?, h.y?, h.z?]))).collect();
    let at = here.and_then(|s| placed.iter().position(|(h, _)| h.system == s)).map_or(1, |i| i + 1);
    let legs = placed
        .windows(2)
        .enumerate()
        .map(|(i, w)| {
            let ly = crate::route::dist(&w[0].1, &w[1].1);
            Leg {
                system: w[1].0.system.clone(),
                ly,
                scoopable: scoopable(w[1].0.star_class.as_deref()),
                boosted: max_jump.is_some_and(|m| ly > m + 0.01),
                flown: i + 1 < at,
                next: i + 1 == at,
            }
        })
        .collect();
    MapRoute { stops: placed.iter().map(|(_, p)| [p[0], p[2]]).collect(), legs }
}

pub fn discovery_line(info: Option<&SystemInfo>, class: Option<&str>) -> Option<(String, Role)> {
    let rare = class.filter(|c| kinds::is_rare_class(c)).and_then(kinds::key_of_class).map(|k| kinds::by_key(k).abbr.to_string());
    let Some(info) = info else {
        return rare.map(|r| (format!("{r} -- looking up whether anybody has scanned it"), Role::Confirmed));
    };
    Some(match (&info.discovered_by, info.bodies) {
        (_, 0) => (
            "Undiscovered".to_string(),
            if rare.is_some() { Role::Confirmed } else { Role::Neutron },
        ),
        (Some((cmdr, date)), _) => (format!("Discovered by {cmdr} {date}"), Role::Carrier),
        (None, _) => ("Scanned, discoverer not reported".to_string(), Role::Carrier),
    })
}

pub fn carrier(info: Option<&SystemInfo>) -> Option<bool> {
    info.filter(|i| i.carriers > 0).map(|i| i.open_carriers > 0)
}

pub fn counts_text(info: Option<&SystemInfo>) -> String {
    let Some(info) = info else { return String::new() };
    let bodies = match (info.bodies, info.bio_bodies) {
        (0, _) => None,
        (n, 0) => Some(format!("Bodies: {n}")),
        (n, b) => Some(format!("Bodies: {n} ({b} bio)")),
    };
    let rest = [
        ("Bio", info.bio),
        ("Geo", info.geo),
        ("Stations", info.stations),
        ("Carriers", info.carriers),
    ]
    .into_iter()
    .filter(|(_, n)| *n > 0)
    .map(|(k, n)| format!("{k}: {n}"));
    bodies.into_iter().chain(rest).collect::<Vec<_>>().join(" \u{00B7} ")
}

pub fn ahead(p: &Panel) -> &[Leg] {
    let at = p.legs.iter().position(|l| l.next).unwrap_or(0);
    &p.legs[at.min(p.legs.len())..]
}

pub fn ahead_ly(p: &Panel) -> f64 {
    ahead(p).iter().map(|l| l.ly).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hop(name: &str, class: &str, x: f64) -> Hop {
        Hop { system: name.into(), star_class: Some(class.into()), x: Some(x), y: Some(0.0), z: Some(0.0), id64: None }
    }

    #[test]
    fn map_route_marks_flown_next_and_boosted_legs() {
        let route = vec![hop("A", "K", 0.0), hop("B", "N", 40.0), hop("C", "K", 140.0), hop("D", "M", 180.0)];
        let m = map_route(&route, Some("B"), Some(50.0));
        assert_eq!(m.stops, [[0.0, 0.0], [40.0, 0.0], [140.0, 0.0], [180.0, 0.0]]);
        let flags: Vec<(bool, bool, bool)> = m.legs.iter().map(|l| (l.flown, l.next, l.boosted)).collect();
        assert_eq!(flags, [(true, false, false), (false, true, true), (false, false, false)]);
        assert!(map_route(&route, None, None).legs[0].next);
    }

    #[test]
    fn route_popup_lists_rare_hops_after_the_origin() {
        let route = vec![hop("Origin", "N", 0.0), hop("B", "K", 50.0), hop("C", "N", 100.0), hop("D", "H", 150.0)];
        let p = route_popup(&route).expect("two rare hops");
        assert_eq!(p.title, "2 targets on this route");
        let named: Vec<(&str, &str)> = p.rows.iter().map(|(n, s, _)| (n.as_str(), s.as_str())).collect();
        assert_eq!(named, [("C", "Neutron Star"), ("D", "Black Hole")]);
    }

    #[test]
    fn route_popup_reads_a_supergiant_from_the_mass_code() {
        let route = vec![hop("Origin", "K", 0.0), hop("Eord Blao AA-A h0", "B", 50.0), hop("Eord Blao AA-A e0", "B", 90.0)];
        let p = route_popup(&route).expect("one supergiant");
        assert_eq!(p.rows.len(), 1);
        assert_eq!(p.rows[0].1, "B (Blue-White super giant) Star");
    }

    #[test]
    fn route_popup_is_none_without_a_rare_hop() {
        assert_eq!(route_popup(&[hop("Origin", "N", 0.0), hop("B", "K", 50.0)]), None);
    }

    #[test]
    fn places_the_target_and_marks_legs() {
        let route = vec![hop("A", "K", 0.0), hop("B", "N", 60.0), hop("C", "M", 300.0), hop("D", "L", 340.0)];
        let p = build(&route, "C", None, Some(50.0));
        assert_eq!(p.class.as_deref(), Some("M"));
        assert_eq!(p.legs.iter().map(|l| (l.flown, l.next, l.boosted, l.scoopable)).collect::<Vec<_>>(), vec![
            (true, false, true, false),
            (false, true, true, true),
            (false, false, false, false),
        ]);
    }

    #[test]
    fn ahead_starts_at_the_next_stop_and_measures_beyond_it() {
        let route: Vec<Hop> = (0..6).map(|i| hop(&format!("S{i}"), "K", i as f64 * 10.0)).collect();
        let p = build(&route, "S2", None, None);
        let names: Vec<&str> = ahead(&p).iter().map(|l| l.system.as_str()).collect();
        assert_eq!(names, ["S2", "S3", "S4", "S5"]);
        assert_eq!(ahead_ly(&p), 40.0);
        let p = build(&route, "S5", None, None);
        assert_eq!(ahead(&p).len(), 1);
        assert_eq!(ahead_ly(&p), 10.0);
    }

    #[test]
    fn marks_a_carrier_by_its_access() {
        let carrier = |carriers, open_carriers| carrier(Some(&SystemInfo { carriers, open_carriers, ..SystemInfo::default() }));
        assert_eq!(carrier(0, 0), None);
        assert_eq!(carrier(2, 0), Some(false));
        assert_eq!(carrier(2, 1), Some(true));
        assert_eq!(super::carrier(None), None);
    }

    #[test]
    fn spells_out_the_star() {
        assert_eq!(star_name("DA"), "White Dwarf (DA) Star");
        assert_eq!(star_name("AeBe"), "Herbig Ae/Be Star");
        assert_eq!(star_text(Some("K"), None), "K (Yellow-Orange) Star");
        let info = SystemInfo { spectral: Some("A9 VI".into()), ..SystemInfo::default() };
        assert_eq!(star_text(Some("N"), Some(&info)), "Neutron Star A9 VI");
    }

    #[test]
    fn counts_put_the_biology_bodies_beside_the_bodies() {
        let info = SystemInfo { bodies: 24, bio_bodies: 3, bio: 7, ..SystemInfo::default() };
        assert_eq!(counts_text(Some(&info)), "Bodies: 24 (3 bio) \u{00B7} Bio: 7");
        let bare = SystemInfo { bodies: 5, ..SystemInfo::default() };
        assert_eq!(counts_text(Some(&bare)), "Bodies: 5");
        assert_eq!(counts_text(None), "");
    }

    #[test]
    fn a_target_off_the_route_is_one_leg() {
        let p = build(&[hop("A", "K", 0.0)], "Z", Some("H"), None);
        assert_eq!(p.legs.len(), 1);
        assert_eq!(p.class_rgb, crate::theme::STAR_BLACK_HOLE);
        assert_eq!(class_rgb(Some("Q")), Role::Warn.rgb());
        assert_eq!(target_rgb(Some("WC"), "Z"), crate::theme::STAR_WOLF_RAYET);
        assert_eq!(target_rgb(Some("K"), "Z"), class_rgb(Some("K")));
        assert_eq!(class_rgb(None), Role::Warn.rgb());
    }

    #[test]
    fn an_unscanned_rare_star_reads_as_a_find() {
        let info = SystemInfo::default();
        let (text, role) = discovery_line(Some(&info), Some("H")).unwrap();
        assert_eq!(text, "Undiscovered");
        assert_eq!(role, Role::Confirmed);
        let seen = SystemInfo { bodies: 5, discovered_by: Some(("x".into(), "2021-04-22".into())), ..SystemInfo::default() };
        assert_eq!(discovery_line(Some(&seen), Some("K")).unwrap().0, "Discovered by x 2021-04-22");
        assert_eq!(discovery_line(None, Some("K")), None);
    }
}
