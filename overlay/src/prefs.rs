use std::collections::HashMap;
use std::sync::Mutex;

const SOUND: &str = "hud.sound";
const LIGHTS: &str = "hud.lights";
const HOTKEYS: &str = "hud.hotkeys";
const ALWAYS_VISIBLE: &str = "hud.always_visible";
const CHROME: &str = "hud.chrome";
const DRAGGABLE: &str = "hud.draggable";
const OPACITY: &str = "hud.opacity_pct";
const SIZE: &str = "hud.size_pct";

pub const OPACITY_CHOICES: [u32; 7] = [50, 60, 70, 80, 85, 90, 100];
pub const SIZE_CHOICES: [u32; 9] = [70, 80, 90, 100, 110, 120, 135, 150, 175];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Prefs {
    pub sound: bool,
    pub lights: bool,
    pub hotkeys: bool,
    pub always_visible: bool,
    pub chrome: bool,
    pub draggable: bool,
    pub opacity: u32,
    pub size: u32,
}

pub const DEFAULT: Prefs = Prefs {
    sound: true,
    lights: true,
    hotkeys: true,
    always_visible: false,
    chrome: false,
    draggable: true,
    opacity: 85,
    size: 100,
};

static CURRENT: Mutex<Prefs> = Mutex::new(DEFAULT);

pub fn get() -> Prefs {
    *CURRENT.lock().unwrap()
}

pub fn set(p: Prefs) {
    *CURRENT.lock().unwrap() = p;
}

impl Prefs {
    fn flags(&mut self) -> [(&'static str, &mut bool); 6] {
        [
            (SOUND, &mut self.sound),
            (LIGHTS, &mut self.lights),
            (HOTKEYS, &mut self.hotkeys),
            (ALWAYS_VISIBLE, &mut self.always_visible),
            (CHROME, &mut self.chrome),
            (DRAGGABLE, &mut self.draggable),
        ]
    }

    fn levels(&mut self) -> [(&'static str, &mut u32, &'static [u32]); 2] {
        [(OPACITY, &mut self.opacity, &OPACITY_CHOICES), (SIZE, &mut self.size, &SIZE_CHOICES)]
    }

    pub fn from_settings(saved: &HashMap<String, String>) -> (Prefs, Vec<String>) {
        let mut p = DEFAULT;
        let mut warnings = Vec::new();
        for (name, slot) in p.flags() {
            let Some(v) = saved.get(name) else { continue };
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
        let mut out: Vec<(String, String)> = p.flags().into_iter().map(|(n, v)| (n.to_string(), v.to_string())).collect();
        out.extend(p.levels().into_iter().map(|(n, v, _)| (n.to_string(), v.to_string())));
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_settings_round_trip_and_bad_values_keep_the_default() {
        let chosen = Prefs { sound: false, chrome: true, opacity: 60, size: 135, ..DEFAULT };
        let saved: HashMap<String, String> = chosen.settings().into_iter().collect();
        assert_eq!(Prefs::from_settings(&saved), (chosen, Vec::new()));

        let bad: HashMap<String, String> =
            [(SOUND, "loud"), (SIZE, "137")].into_iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
        let (p, warnings) = Prefs::from_settings(&bad);
        assert_eq!(p, DEFAULT);
        assert_eq!(warnings.len(), 2);
    }
}
