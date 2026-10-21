pub const CRAFTED_SECTOR: &str = "crafted";

fn is_boxel_token(part: &str) -> bool {
    let b = part.as_bytes();
    b.len() == 4
        && b[0].is_ascii_uppercase()
        && b[1].is_ascii_uppercase()
        && b[2] == b'-'
        && b[3].is_ascii_uppercase()
}

fn split(system: &str) -> (Vec<&str>, Option<usize>) {
    let parts: Vec<&str> = system.split_whitespace().collect();
    let at = parts.iter().enumerate().skip(1).find(|(_, p)| is_boxel_token(p)).map(|(i, _)| i);
    (parts, at)
}

pub fn sector_of(system: &str) -> Option<String> {
    let (parts, at) = split(system);
    at.map(|i| parts[..i].join(" "))
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
        assert_eq!(boxel_index("Col 359 Sector SO-R e4-10"), Some(10));
        assert_eq!(boxel_index("Sol"), None);
    }
}
