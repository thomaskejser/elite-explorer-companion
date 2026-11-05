use std::collections::{BTreeMap, HashMap};
use std::sync::Mutex;

use crate::kinds::KINDS;

const SOUND: &str = "hud.sound";
const LIGHTS: &str = "hud.lights";
const HOTKEYS: &str = "hud.hotkeys";
const ALWAYS_VISIBLE: &str = "hud.always_visible";
const DRAGGABLE: &str = "hud.draggable";
const OPACITY: &str = "hud.opacity_pct";
const SIZE: &str = "hud.size_pct";
const PLACE_PREFIX: &str = "hud.place.";
const MAP_KIND_PREFIX: &str = "hud.map_kind.";

pub const OPACITY_CHOICES: [u32; 7] = [50, 60, 70, 80, 85, 90, 100];
pub const SIZE_CHOICES: [u32; 9] = [70, 80, 90, 100, 110, 120, 135, 150, 175];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Prefs {
    pub sound: bool,
    pub lights: bool,
    pub hotkeys: bool,
    pub always_visible: bool,
    pub draggable: bool,
    pub opacity: u32,
    pub size: u32,
    pub map_kinds: [bool; KINDS.len()],
}

pub const DEFAULT: Prefs = Prefs {
    sound: true,
    lights: true,
    hotkeys: true,
    always_visible: false,
    draggable: true,
    opacity: 85,
    size: 100,
    map_kinds: [true; KINDS.len()],
};

static CURRENT: Mutex<Prefs> = Mutex::new(DEFAULT);
static PLACES: Mutex<BTreeMap<String, (i32, i32)>> = Mutex::new(BTreeMap::new());

pub fn get() -> Prefs {
    *CURRENT.lock().unwrap()
}

pub fn set(p: Prefs) {
    *CURRENT.lock().unwrap() = p;
}

pub fn place(pane: &str) -> Option<(i32, i32)> {
    PLACES.lock().unwrap().get(pane).copied()
}

pub fn set_place(pane: &str, at: (i32, i32)) -> (String, String) {
    PLACES.lock().unwrap().insert(pane.to_string(), at);
    (format!("{PLACE_PREFIX}{pane}"), format!("{},{}", at.0, at.1))
}

pub fn load_places(saved: &HashMap<String, String>) -> Vec<String> {
    let mut warnings = Vec::new();
    let mut places = PLACES.lock().unwrap();
    for (name, v) in saved {
        let Some(pane) = name.strip_prefix(PLACE_PREFIX) else { continue };
        match v.split_once(',').and_then(|(x, y)| Some((x.parse().ok()?, y.parse().ok()?))) {
            Some(at) => {
                places.insert(pane.to_string(), at);
            }
            None => warnings.push(format!("{name} = {v:?} is not x,y; keeping the default place")),
        }
    }
    warnings
}

impl Prefs {
    fn flags(&mut self) -> Vec<(String, &mut bool)> {
        let mut out: Vec<(String, &mut bool)> = vec![
            (SOUND.to_string(), &mut self.sound),
            (LIGHTS.to_string(), &mut self.lights),
            (HOTKEYS.to_string(), &mut self.hotkeys),
            (ALWAYS_VISIBLE.to_string(), &mut self.always_visible),
            (DRAGGABLE.to_string(), &mut self.draggable),
        ];
        out.extend(KINDS.iter().zip(self.map_kinds.iter_mut()).map(|(k, on)| (format!("{MAP_KIND_PREFIX}{}", k.key), on)));
        out
    }

    pub fn draws_on_map(&self, kind: &str) -> bool {
        KINDS.iter().position(|k| k.key == kind).is_none_or(|i| self.map_kinds[i])
    }

    fn levels(&mut self) -> [(&'static str, &mut u32, &'static [u32]); 2] {
        [(OPACITY, &mut self.opacity, &OPACITY_CHOICES), (SIZE, &mut self.size, &SIZE_CHOICES)]
    }

    pub fn from_settings(saved: &HashMap<String, String>) -> (Prefs, Vec<String>) {
        let mut p = DEFAULT;
        let mut warnings = Vec::new();
        for (name, slot) in p.flags() {
            let Some(v) = saved.get(&name) else { continue };
            match v.parse::<bool>() {
                Ok(b) => *slot = b,
                Err(_) => warnings.push(format!("{name} = {v:?} is not true or false; keeping {slot}")),
            }
        }
        for (name, slot, choices) in p.levels() {
            let Some(v) = saved.get(name) else { continue };
            match v.parse::<u32>() {
                Ok(n) if choices.contains(&n) => *slot = n,
                _ => warnings.push(format!("{name} = {v:?} is not one of {choices:?}; keeping {slot}")),
            }
        }
        (p, warnings)
    }

    pub fn settings(&self) -> Vec<(String, String)> {
        let mut p = *self;
        let mut out: Vec<(String, String)> = p.flags().into_iter().map(|(n, v)| (n, v.to_string())).collect();
        out.extend(p.levels().into_iter().map(|(n, v, _)| (n.to_string(), v.to_string())));
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_settings_round_trip_and_bad_values_keep_the_default() {
        let chosen = Prefs { sound: false, draggable: false, opacity: 60, size: 135, ..DEFAULT };
        let saved: HashMap<String, String> = chosen.settings().into_iter().collect();
        assert_eq!(Prefs::from_settings(&saved), (chosen, Vec::new()));

        let bad: HashMap<String, String> =
            [(SOUND, "loud"), (SIZE, "137")].into_iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
        let (p, warnings) = Prefs::from_settings(&bad);
        assert_eq!(p, DEFAULT);
        assert_eq!(warnings.len(), 2);
    }

    #[test]
    fn every_kind_is_drawn_on_the_map_until_unticked_and_the_choice_round_trips() {
        assert!(KINDS.iter().all(|k| DEFAULT.draws_on_map(k.key)));
        let mut map_kinds = DEFAULT.map_kinds;
        map_kinds[KINDS.iter().position(|k| k.key == "NEUTRON").unwrap()] = false;
        let chosen = Prefs { map_kinds, ..DEFAULT };
        assert!(!chosen.draws_on_map("NEUTRON"));
        assert!(chosen.draws_on_map("WR"));
        let saved: HashMap<String, String> = chosen.settings().into_iter().collect();
        assert_eq!(saved.get("hud.map_kind.NEUTRON").map(String::as_str), Some("false"));
        assert_eq!(Prefs::from_settings(&saved), (chosen, Vec::new()));
    }

    #[test]
    fn a_dragged_place_round_trips_and_a_bad_one_is_ignored() {
        let saved: HashMap<String, String> = [set_place("test_round", (1280, -40))].into_iter().collect();
        PLACES.lock().unwrap().clear();
        assert_eq!(load_places(&saved), Vec::<String>::new());
        assert_eq!(place("test_round"), Some((1280, -40)));

        let bad: HashMap<String, String> = [("hud.place.test_bad".to_string(), "12;5".to_string())].into_iter().collect();
        assert_eq!(load_places(&bad).len(), 1);
        assert_eq!(place("test_bad"), None);
    }
}
