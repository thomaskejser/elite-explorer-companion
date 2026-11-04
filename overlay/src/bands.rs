use crate::slots::SLOTS;
use crate::spectrum::slot_at;

pub const SLACK: f64 = 0.004;
pub const SAME_GROUP: usize = 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Family {
    Signal,
    Asteroid,
    Rock,
    Ice,
    EarthLike,
    Ammonia,
    Water,
    Gas,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Range {
    pub class: &'static str,
    pub lo: f64,
    pub hi: f64,
    pub family: Family,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Slot {
    pub slot: usize,
    pub class: &'static str,
    pub atmosphere: bool,
}

const fn range(class: &'static str, lo: f64, hi: f64, family: Family) -> Range {
    Range { class, lo, hi, family }
}

pub const RANGES: [Range; 21] = [
    range("Transient signal source", 0.0, 0.080, Family::Signal),
    range("Concentrated signal source", 0.098, 0.285, Family::Signal),
    range("Asteroid cluster", 0.322, 0.358, Family::Asteroid),
    range("Metal rich body", 0.359, 0.382, Family::Rock),
    range("High metal content body", 0.385, 0.417, Family::Rock),
    range("Rocky body", 0.420, 0.452, Family::Rock),
    range("Icy body", 0.453, 0.486, Family::Ice),
    range("Rocky ice body", 0.486, 0.521, Family::Ice),
    range("Earthlike body", 0.522, 0.547, Family::EarthLike),
    range("Ammonia world", 0.548, 0.579, Family::Ammonia),
    range("Water world", 0.582, 0.614, Family::Water),
    range("Water giant", 0.615, 0.626, Family::Gas),
    range("Gas giant with water based life", 0.676, 0.707, Family::Gas),
    range("Gas giant with ammonia based life", 0.712, 0.734, Family::Gas),
    range("Sudarsky class I gas giant", 0.738, 0.761, Family::Gas),
    range("Sudarsky class II gas giant", 0.770, 0.793, Family::Gas),
    range("Sudarsky class III gas giant", 0.797, 0.831, Family::Gas),
    range("Sudarsky class IV gas giant", 0.836, 0.866, Family::Gas),
    range("Sudarsky class V gas giant", 0.870, 0.898, Family::Gas),
    range("Helium rich gas giant", 0.908, 0.931, Family::Gas),
    range("Helium gas giant", 0.908, 0.931, Family::Gas),
];

#[derive(Debug, Clone, PartialEq)]
pub struct Mark {
    pub at: f64,
    pub class: Option<String>,
    pub atmosphere: bool,
}

impl Range {
    fn distance(&self, at: f64) -> f64 {
        if at < self.lo { self.lo - at } else if at > self.hi { at - self.hi } else { 0.0 }
    }

    fn holds(&self, at: f64) -> bool {
        at >= self.lo - SLACK && at <= self.hi + SLACK
    }
}

pub const NOTABLE: [Family; 4] = [Family::EarthLike, Family::Water, Family::Ammonia, Family::Signal];

pub fn notable(marks: &[Mark]) -> Vec<Family> {
    NOTABLE.iter().copied().filter(|f| marks.iter().any(|m| m.class.as_deref().is_some_and(|c| family(c) == *f))).collect()
}

pub fn bio_candidates(marks: &[Mark], scanned: &[&str]) -> usize {
    marks
        .iter()
        .filter(|m| m.atmosphere)
        .filter_map(|m| m.class.as_deref())
        .filter(|c| *c != "Metal rich body" && matches!(family(c), Family::Rock | Family::Ice))
        .filter(|c| !scanned.contains(c))
        .count()
}

pub fn unknown(marks: &[Mark]) -> usize {
    marks.iter().filter(|m| m.class.is_none()).count()
}

pub fn family(class: &str) -> Family {
    RANGES.iter().find(|r| r.class == class).map_or(Family::Rock, |r| r.family)
}

pub fn ranges_at(at: f64) -> Vec<&'static Range> {
    RANGES.iter().filter(|r| r.holds(at)).collect()
}

fn owners(slot: usize) -> Vec<(Option<&'static str>, bool)> {
    let learned: Vec<_> = SLOTS.iter().filter(|s| s.slot == slot).map(|s| (Some(s.class), s.atmosphere)).collect();
    if !learned.is_empty() {
        return learned;
    }
    let at = slot_at(slot);
    match RANGES.iter().find(|r| matches!(r.family, Family::Signal | Family::Asteroid) && r.holds(at)) {
        Some(r) => vec![(Some(r.class), false)],
        None => vec![(None, false)],
    }
}

pub fn marks(slots: &[usize], icons: &[f64]) -> Vec<Mark> {
    let mut groups: Vec<(Option<&'static str>, bool, Vec<usize>)> = Vec::new();
    for &slot in slots {
        for (class, atmosphere) in owners(slot) {
            match groups.iter_mut().find(|g| g.0 == class && g.1 == atmosphere && g.2.last().is_some_and(|&l| slot - l <= SAME_GROUP)) {
                Some(g) => g.2.push(slot),
                None => groups.push((class, atmosphere, vec![slot])),
            }
        }
    }
    let mut out: Vec<Mark> = groups
        .into_iter()
        .map(|(class, atmosphere, run)| Mark {
            at: run.iter().map(|&s| slot_at(s)).sum::<f64>() / run.len() as f64,
            class: class.map(str::to_string),
            atmosphere,
        })
        .collect();
    for &at in icons {
        let Some(r) = ranges_at(at).into_iter().min_by(|a, b| a.distance(at).total_cmp(&b.distance(at))) else { continue };
        if out.iter().all(|m| m.class.as_deref() != Some(r.class)) {
            out.push(Mark { at, class: Some(r.class.to_string()), atmosphere: false });
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn named(m: &[Mark]) -> Vec<(Option<&str>, bool)> {
        m.iter().map(|k| (k.class.as_deref(), k.atmosphere)).collect()
    }

    #[test]
    fn a_spike_on_a_border_names_both_neighbours() {
        assert_eq!(ranges_at(0.486).iter().map(|r| r.class).collect::<Vec<_>>(), ["Icy body", "Rocky ice body"]);
    }

    #[test]
    fn a_learned_slot_names_its_class_and_atmosphere() {
        assert_eq!(named(&marks(&[77], &[])), [(Some("High metal content body"), false)]);
        assert_eq!(named(&marks(&[82], &[])), [(Some("High metal content body"), true)]);
    }

    #[test]
    fn a_shared_slot_names_every_class_that_uses_it() {
        assert_eq!(named(&marks(&[96], &[])), [(Some("Icy body"), true), (Some("Rocky ice body"), false)]);
    }

    #[test]
    fn neighbouring_slots_of_one_class_make_one_mark_between_them() {
        let m = marks(&[159, 160], &[]);
        assert_eq!(named(&m), [(Some("Sudarsky class III gas giant"), false)]);
        assert!((m[0].at - (slot_at(159) + slot_at(160)) / 2.0).abs() < 1e-9);
    }

    #[test]
    fn an_unlearned_slot_is_a_warning_and_a_signal_slot_is_a_signal() {
        assert_eq!(named(&marks(&[128], &[])), [(None, false)]);
        assert_eq!(named(&marks(&[30], &[])), [(Some("Concentrated signal source"), false)]);
        assert_eq!(unknown(&marks(&[128, 30], &[])), 1);
    }

    #[test]
    fn counts_each_atmospheric_rock_and_ice_group_as_a_biology_candidate() {
        assert_eq!(bio_candidates(&marks(&[83], &[]), &[]), 1);
        assert_eq!(bio_candidates(&marks(&[77, 83, 96, 107], &[]), &[]), 2);
        assert_eq!(bio_candidates(&marks(&[77, 83, 96, 107], &[]), &["High metal content body"]), 1);
        assert_eq!(bio_candidates(&marks(&[77, 83, 96, 107], &[]), &["High metal content body", "Icy body"]), 0);
    }

    #[test]
    fn an_asteroid_cluster_wave_below_its_published_range_is_still_an_asteroid_cluster() {
        assert_eq!(named(&marks(&[62, 63, 64, 65], &[])), [(Some("Asteroid cluster"), false)]);
        assert_eq!(unknown(&marks(&[62, 63, 64, 65, 66, 67, 68], &[])), 0);
    }

    #[test]
    fn a_sudarsky_class_v_spike_is_named() {
        assert_eq!(named(&marks(&[173], &[])), [(Some("Sudarsky class V gas giant"), false)]);
    }

    #[test]
    fn an_icon_already_drawn_adds_its_class_once() {
        let m = marks(&[], &[0.326]);
        assert_eq!(named(&m), [(Some("Asteroid cluster"), false)]);
    }

    #[test]
    fn flags_the_worth_scanning_families_from_the_marks() {
        let m = marks(&[107, 118, 30, 82], &[]);
        assert_eq!(notable(&m), [Family::EarthLike, Family::Water, Family::Signal]);
    }

    #[test]
    fn colours_each_class_by_its_family() {
        assert_eq!(family("Icy body"), Family::Ice);
        assert_eq!(family("Earthlike body"), Family::EarthLike);
        assert_eq!(family("Water world"), Family::Water);
        assert_eq!(family("Sudarsky class I gas giant"), Family::Gas);
        assert_eq!(family("High metal content body"), Family::Rock);
    }

    #[test]
    fn the_ranges_run_from_low_to_high() {
        assert!(RANGES.windows(2).all(|w| w[0].lo <= w[1].lo && w[0].lo < w[0].hi));
    }

    #[test]
    fn the_slot_table_runs_from_low_to_high() {
        assert!(SLOTS.windows(2).all(|w| w[0].slot <= w[1].slot));
    }
}
