pub struct Kind {
    pub key: &'static str,
    pub column: &'static str,
    pub abbr: &'static str,
    pub classes: &'static [&'static str],
    pub ranks: bool,
    pub rare: bool,
    pub chime: bool,
    pub chime_predicted: bool,
}

pub const KINDS: [Kind; 6] = [
    Kind {
        key: "BH",
        column: "p_bh",
        abbr: "BLK HOLE",
        classes: &["H", "SupermassiveBlackHole", "SuperMassiveBlackHole"],
        ranks: true,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "WR",
        column: "p_wr",
        abbr: "WOLF-RAY",
        classes: &["W", "WN", "WNC", "WC", "WO"],
        ranks: true,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "HERBIG",
        column: "p_herbig",
        abbr: "HERBIG",
        classes: &["AeBe"],
        ranks: false,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "O-TYPE",
        column: "p_otype",
        abbr: "O-TYPE",
        classes: &["O"],
        ranks: false,
        rare: true,
        chime: true,
        chime_predicted: false,
    },
    Kind {
        key: "NEUTRON",
        column: "p_neutron",
        abbr: "NEUTRON",
        classes: &["N"],
        ranks: false,
        rare: false,
        chime: false,
        chime_predicted: true,
    },
    Kind {
        key: "WHT DWRF",
        column: "p_wd",
        abbr: "WHT DWRF",
        classes: &[
            "D", "DA", "DAB", "DAO", "DAV", "DAZ", "DB", "DBV", "DBZ", "DC", "DCV", "DO", "DOV",
            "DQ", "DX",
        ],
        ranks: false,
        rare: false,
        chime: false,
        chime_predicted: false,
    },
];

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
}
