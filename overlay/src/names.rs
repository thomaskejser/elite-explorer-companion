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
