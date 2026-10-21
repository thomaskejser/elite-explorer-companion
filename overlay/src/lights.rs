use serde_json::Value;

use crate::journal::flag;
use crate::kinds;
use crate::ship::has_shields;
use crate::win::vkb::{CONSTANT, FAST_BLINK, Throttle, from_vkb};

const FUEL_GREEN_ABOVE: f64 = 0.80;
const FUEL_FLASH_BELOW: f64 = 0.25;
const LEVELS: f64 = 7.0;

const FUEL_LED: usize = 0;
const TARGET_LED: usize = 1;
const SHIP_LED: usize = 2;

pub type LedState = (Option<String>, u8);

const DARK: LedState = (None, 0);

pub fn fuel_color(fraction: Option<f64>) -> LedState {
    let Some(f) = fraction else { return DARK };
    let f = f.clamp(0.0, 1.0);
    if f >= FUEL_GREEN_ABOVE {
        return (Some(from_vkb([0, 7, 0])), CONSTANT);
    }
    if f < FUEL_FLASH_BELOW {
        return (Some(from_vkb([7, 0, 0])), FAST_BLINK);
    }
    let u = (f - FUEL_FLASH_BELOW) / (FUEL_GREEN_ABOVE - FUEL_FLASH_BELOW);
    let red = crate::theme::round_half_even(LEVELS * (2.0 * (1.0 - u)).min(1.0)) as u8;
    let green = crate::theme::round_half_even(LEVELS * (2.0 * u).min(1.0)) as u8;
    (Some(from_vkb([red, green, 0])), CONSTANT)
}

pub fn target_color(star_class: Option<&str>) -> LedState {
    match star_class.and_then(kinds::key_of_class) {
        Some("NEUTRON") => (Some("#0000ff".into()), CONSTANT),
        Some("WHT DWRF") => (Some("#0000ff".into()), FAST_BLINK),
        Some("BH") => (Some("#ff0000".into()), FAST_BLINK),
        _ => DARK,
    }
}

pub fn ship_color(status: Option<&Value>, loadout: Option<&Value>) -> LedState {
    if flag(status, "InMainShip") != Some(true) {
        return DARK;
    }
    if flag(status, "ShieldsUp") == Some(false) && has_shields(loadout) {
        return (Some("#0000ff".into()), FAST_BLINK);
    }
    if flag(status, "CargoScoopDeployed") == Some(true) {
        return (Some("#ffffff".into()), CONSTANT);
    }
    DARK
}

pub fn fuel_fraction(status: Option<&Value>, loadout: Option<&Value>) -> Option<f64> {
    let main = status?.get("Fuel")?.get("FuelMain")?.as_f64()?;
    let tank = loadout?.get("FuelCapacity")?.get("Main")?.as_f64().filter(|t| *t != 0.0)?;
    Some(main / tank)
}

pub struct Lights {
    throttle: Throttle,
    enabled: bool,
    want: [LedState; 3],
    sent: Option<[LedState; 3]>,
}

impl Lights {
    pub fn new(enabled: bool) -> Lights {
        Lights { throttle: Throttle::new(), enabled, want: [DARK, DARK, DARK], sent: None }
    }

    pub fn present(&mut self) -> bool {
        self.enabled && self.throttle.present()
    }

    pub fn fuel(&mut self, fraction: Option<f64>) -> bool {
        self.show(FUEL_LED, fuel_color(fraction))
    }

    pub fn target(&mut self, star_class: Option<&str>) -> bool {
        self.show(TARGET_LED, target_color(star_class))
    }

    pub fn ship(&mut self, status: Option<&Value>, loadout: Option<&Value>) -> bool {
        self.show(SHIP_LED, ship_color(status, loadout))
    }

    pub fn clear(&mut self) -> bool {
        self.want = [DARK, DARK, DARK];
        self.sent = None;
        self.enabled && self.throttle.off()
    }

    fn show(&mut self, index: usize, state: LedState) -> bool {
        self.want[index] = state;
        if !self.enabled || self.sent.as_ref() == Some(&self.want) {
            return false;
        }
        if self.throttle.show(&self.want) {
            self.sent = Some(self.want.clone());
            return true;
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fuel_ramp_matches_python() {
        let want = [
            (0.1, "#ff0000", FAST_BLINK),
            (0.25, "#ff0000", CONSTANT),
            (0.3, "#ff2400", CONSTANT),
            (0.5, "#ffdb00", CONSTANT),
            (0.52, "#ffff00", CONSTANT),
            (0.7, "#6dff00", CONSTANT),
            (0.79, "#00ff00", CONSTANT),
            (0.8, "#00ff00", CONSTANT),
            (1.0, "#00ff00", CONSTANT),
        ];
        for (f, colour, mode) in want {
            assert_eq!(fuel_color(Some(f)), (Some(colour.to_string()), mode), "fraction {f}");
        }
        assert_eq!(fuel_color(None), (None, 0));
    }
}
