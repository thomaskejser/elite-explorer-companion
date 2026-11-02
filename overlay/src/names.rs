pub const CRAFTED_SECTOR: &str = "crafted";

fn is_boxel_token(part: &str) -> bool {
    let b = part.as_bytes();
    b.len() == 4
        && b[0].is_ascii_uppercase()
        && b[1].is_ascii_uppercase()
        && b[2] == b'-'
        && b[3].is_ascii_uppercase()
}

pub const PROCEDURAL: &str = r"^(.*) [A-Z][A-Z]-[A-Z] ([a-h])(\d+-)?(\d+)$";

fn is_number(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}

fn procedural(system: &str) -> Option<(&str, char)> {
    let (rest, index) = system.trim().rsplit_once(' ')?;
    let (sector, cube) = rest.rsplit_once(' ')?;
    let mut chars = index.chars();
    let mass = chars.next().filter(|m| ('a'..='h').contains(m))?;
    let number = chars.as_str();
    let (lead, last) = number.split_once('-').unwrap_or(("0", number));
    (!sector.is_empty() && is_boxel_token(cube) && is_number(lead) && is_number(last)).then_some((sector, mass))
}

pub fn sector_of(system: &str) -> Option<String> {
    procedural(system).map(|(sector, _)| sector.to_string())
}

pub fn mass_code(system: &str) -> Option<char> {
    procedural(system).map(|(_, mass)| mass)
}

pub fn boxel_centre(id64: i64) -> ([f64; 3], f64) {
    let m = (id64 & 7) as u32;
    let bits = |n: u32| (1i64 << n) - 1;
    let z = (id64 >> 3) & bits(14 - m);
    let y = (id64 >> (17 - m)) & bits(13 - m);
    let x = (id64 >> (30 - 2 * m)) & bits(14 - m);
    let size = 10.0 * f64::from(1u32 << m);
    let at = |cell: i64, origin: f64| origin + (cell as f64 + 0.5) * size;
    ([at(x, -49985.0), at(y, -40985.0), at(z, -24105.0)], size / 2.0 * 3f64.sqrt())
}

pub fn name_centre(system: &str, sector_id: i64) -> Option<([f64; 3], f64)> {
    if sector_id <= 0 {
        return None;
    }
    let (rest, index) = system.trim().rsplit_once(' ')?;
    let (_, cube) = rest.rsplit_once(' ')?;
    let mass = procedural(system)?.1 as i64 - 'a' as i64;
    let letter = |i: usize| i64::from(cube.as_bytes()[i] - b'A');
    let number = &index[1..];
    let lead: i64 = number.split_once('-').map_or(Ok(0), |(lead, _)| lead.parse()).ok()?;
    let at = letter(0) + 26 * letter(1) + 676 * letter(3) + 17576 * lead;
    let size = 10.0 * (1i64 << mass) as f64;
    let boxel = [at % 128, (at / 128) % 128, at / 16384];
    let cell = [sector_id % 128, (sector_id / 128) % 128, sector_id / 16384];
    let origin = [-49985.0, -40985.0, -24105.0];
    let centre = std::array::from_fn(|i| origin[i] + cell[i] as f64 * 1280.0 + (boxel[i] as f64 + 0.5) * size);
    Some((centre, size / 2.0 * 3f64.sqrt()))
}

pub fn boxel_index(system: &str) -> Option<u64> {
    let trimmed = system.trim();
    let digits: String = trimmed.chars().rev().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    digits.chars().rev().collect::<String>().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn boxel_centre_holds_the_system() {
        for (id64, xyz) in [
            (57128518868i64, [-617.2642, 50.39773, 613.79261]),
            (22760383692, [-943.20313, -41.17188, 483.80469]),
            (44243608804, [-558.53125, -146.6875, 878.41667]),
        ] {
            let (centre, within) = boxel_centre(id64);
            let off = ((0..3).map(|i| (centre[i] - xyz[i]).powi(2)).sum::<f64>()).sqrt();
            assert!(off <= within, "{id64}: {off} ly off, allowed {within}");
            assert!((centre[0] - xyz[0]).abs() <= 80.0 && (centre[2] - xyz[2]).abs() <= 80.0, "{id64}");
        }
    }

    #[test]
    fn name_centre_holds_the_system() {
        for (system, sector_id, xyz) in [
            ("Bleae Air AA-A h100", 495780, [-3188.21875, 2287.84375, 15490.625]),
            ("Bleae Air AA-A h110", 495780, [-2743.09375, 1652.09375, 15232.53125]),
            ("Whamboe TJ-Q e5-4788", 544802, [-5536.59375, 837.21875, 19240.46875]),
        ] {
            let (centre, within) = name_centre(system, sector_id).unwrap();
            let off = ((0..3).map(|i| (centre[i] - xyz[i]).powi(2)).sum::<f64>()).sqrt();
            assert!(off <= within, "{system}: {off} ly off, allowed {within}");
        }
        assert_eq!(name_centre("Sol", 1), None);
        assert_eq!(name_centre("Col 359 Sector IH-V e2-13", -5), None);
    }

    #[test]
    fn parses_procedural_names() {
        assert_eq!(sector_of("Blaa Hypai BA-A g5").as_deref(), Some("Blaa Hypai"));
        assert_eq!(sector_of("Sol"), None);
        assert_eq!(sector_of("AA-A h5"), None);
        assert_eq!(sector_of("Col 285 Sector AB-C d12-34").as_deref(), Some("Col 285 Sector"));
        assert_eq!(mass_code("Pyraleau AA-A h0"), Some('h'));
        assert_eq!(mass_code("Col 285 Sector AB-C d12-34"), Some('d'));
        assert_eq!(mass_code("Shinrarta Dezhra"), None);
        assert_eq!(mass_code("Pyraleau AA-A x0"), None);
        assert_eq!(mass_code("Pyraleau AA-A h"), None);
        assert_eq!(mass_code("Pyraleau AA-A h0x"), None);
        assert_eq!(boxel_index("Col 359 Sector SO-R e4-10"), Some(10));
        assert_eq!(boxel_index("Sol"), None);
    }
}
