pub struct Kind {
    pub key: &'static str,
    pub column: &'static str,
    pub abbr: &'static str,
    pub name: &'static str,
    pub classes: &'static [&'static str],
    pub by_mass: &'static [(&'static str, &'static str)],
    pub ranks: bool,
    pub rare: bool,
    pub chime: bool,
    pub chime_predicted: bool,
}

pub const KINDS: [Kind; 7] = [
    Kind {
        key: "BH",
        column: "p_bh",
        abbr: "BLK HOLE",
        name: "black holes",
        classes: &["H", "SupermassiveBlackHole", "SuperMassiveBlackHole"],
        by_mass: &[],
        ranks: true,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "WR",
        column: "p_wr",
        abbr: "WOLF-RAY",
        name: "Wolf-Rayet stars",
        classes: &["W", "WN", "WNC", "WC", "WO"],
        by_mass: &[],
        ranks: true,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "HERBIG",
        column: "p_herbig",
        abbr: "HERBIG",
        name: "Herbig Ae/Be stars",
        classes: &["AeBe"],
        by_mass: &[],
        ranks: false,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "O-TYPE",
        column: "p_otype",
        abbr: "O-TYPE",
        name: "O-type stars",
        classes: &["O"],
        by_mass: &[],
        ranks: false,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "SUPERGNT",
        column: "p_supergiant",
        abbr: "SUPERGNT",
        name: "supergiants",
        classes: &[
            "A_BlueWhiteSuperGiant",
            "B_BlueWhiteSuperGiant",
            "F_WhiteSuperGiant",
            "G_WhiteSuperGiant",
            "M_RedSuperGiant",
        ],
        by_mass: &[
            ("A_BlueWhiteSuperGiant", "fgh"),
            ("B_BlueWhiteSuperGiant", "h"),
            ("F_WhiteSuperGiant", "e"),
            ("G_WhiteSuperGiant", "e"),
            ("M_RedSuperGiant", "e"),
        ],
        ranks: false,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "NEUTRON",
        column: "p_neutron",
        abbr: "NEUTRON",
        name: "neutron stars",
        classes: &["N"],
        by_mass: &[],
        ranks: false,
        rare: false,
        chime: false,
        chime_predicted: true,
    },
    Kind {
        key: "WHT DWRF",
        column: "p_wd",
        abbr: "WHT DWRF",
        name: "white dwarfs",
        classes: &[
            "D", "DA", "DAB", "DAO", "DAV", "DAZ", "DB", "DBV", "DBZ", "DC", "DCV", "DO", "DOV",
            "DQ", "DX",
        ],
        by_mass: &[],
        ranks: false,
        rare: false,
        chime: false,
        chime_predicted: false,
    },
];

impl Kind {
    pub fn title(&self) -> String {
        let mut c = self.name.chars();
        c.next().map(|f| f.to_uppercase().chain(c).collect()).unwrap_or_default()
    }
}

pub fn by_key(key: &str) -> &'static Kind {
    KINDS.iter().find(|k| k.key == key).expect("unknown kind key")
}

pub fn column_index(column: &str) -> Option<usize> {
    KINDS.iter().position(|k| k.column == column)
}

pub fn heading(column: &str) -> &'static str {
    KINDS[column_index(column).expect("unknown kind column")].abbr
}

pub fn key_of_class(class: &str) -> Option<&'static str> {
    KINDS.iter().find(|k| k.classes.contains(&class)).map(|k| k.key)
}

pub fn arrival_class<'a>(class: &'a str, system: &str) -> &'a str {
    let Some(mass) = crate::names::mass_code(system) else { return class };
    KINDS
        .iter()
        .flat_map(|k| k.by_mass.iter())
        .find(|(long, masses)| letter_of(long) == class && masses.contains(mass))
        .map_or(class, |(long, _)| long)
}

pub fn letter_of(long: &str) -> &str {
    long.split('_').next().unwrap_or(long)
}

pub fn arrival_sql(class: &str, system: &str) -> String {
    let whens: String = KINDS
        .iter()
        .flat_map(|k| k.by_mass.iter())
        .flat_map(|(long, masses)| masses.chars().map(move |m| format!(" WHEN '{}{m}' THEN '{long}'", letter_of(long))))
        .collect();
    format!(
        "(CASE {class} || regexp_extract({system}, '{}', 2){whens} ELSE {class} END)",
        crate::names::PROCEDURAL
    )
}

pub fn is_rare_class(class: &str) -> bool {
    key_of_class(class).is_some()
}

pub fn is_chime_class(class: &str) -> bool {
    KINDS.iter().any(|k| k.chime && k.classes.contains(&class))
}

pub fn is_chime_if_predicted(class: &str) -> bool {
    KINDS.iter().any(|k| k.chime_predicted && k.classes.contains(&class))
}

pub fn all_classes() -> Vec<&'static str> {
    let mut all: Vec<&'static str> = KINDS.iter().flat_map(|k| k.classes.iter().copied()).collect();
    all.sort_unstable();
    all
}

pub fn assert_vocabulary() {
    let total: usize = KINDS.iter().map(|k| k.classes.len()).sum();
    let mut all = all_classes();
    all.dedup();
    assert_eq!(all.len(), total, "an arrival class names more than one kind");
    assert!(
        KINDS.iter().filter(|k| k.ranks).count() >= 2,
        "RANK_BY summarises competing outcomes; one is not a race"
    );
    for k in &KINDS {
        assert!(
            k.by_mass.iter().all(|(long, _)| k.classes.contains(long)),
            "{} confirms a class by mass code that it does not list",
            k.key
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CASES: [(&str, &str, &str); 9] = [
        ("A", "Pyraleau AA-A f3", "A_BlueWhiteSuperGiant"),
        ("B", "Byoi Euq AA-A h8", "B_BlueWhiteSuperGiant"),
        ("F", "Eol Prou LW-L e8-4", "F_WhiteSuperGiant"),
        ("M", "Eol Prou LW-L e8-4", "M_RedSuperGiant"),
        ("B", "Byoi Euq AA-A g8", "B"),
        ("F", "Eol Prou LW-L d8-4", "F"),
        ("A", "Sol", "A"),
        ("K", "Eol Prou LW-L e8-4", "K"),
        ("H", "Byoi Euq AA-A h8", "H"),
    ];

    #[test]
    fn a_letter_is_a_supergiant_only_in_its_mass_codes() {
        let con = duckdb::Connection::open_in_memory().unwrap();
        for (class, system, want) in CASES {
            assert_eq!(arrival_class(class, system), want, "{class} in {system}");
            let sql = format!("SELECT {}", arrival_sql(&format!("'{class}'"), &format!("'{system}'")));
            let got: String = con.query_row(&sql, [], |r| r.get(0)).unwrap();
            assert_eq!(got, want, "SQL: {class} in {system}");
        }
        assert_eq!(key_of_class(arrival_class("M", "Eol Prou LW-L e8-4")), Some("SUPERGNT"));
        assert_eq!(key_of_class(arrival_class("A", "Pyraleau AA-A e3")), None);
    }
}
