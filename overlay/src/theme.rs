use crate::kinds;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Rgb(pub u8, pub u8, pub u8);

impl Rgb {
    pub const fn hex(v: u32) -> Rgb {
        Rgb((v >> 16) as u8, (v >> 8) as u8, v as u8)
    }

    pub fn to_hex(self) -> String {
        format!("#{:02x}{:02x}{:02x}", self.0, self.1, self.2)
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Role {
    Fg,
    Head,
    Dim,
    Ok,
    Warn,
    Hot,
    Keycap,
    Clock,
    Confirmed,
    Poi,
    Carrier,
    Neutron,
    Unfound,
    Catalog,
    Region,
}

impl Role {
    pub fn rgb(self) -> Rgb {
        match self {
            Role::Fg => Rgb::hex(0x39ff14),
            Role::Head => HEADER_TEXT,
            Role::Dim => Rgb::hex(0xaaaaaa),
            Role::Ok => Rgb::hex(0xffd700),
            Role::Warn => Rgb::hex(0xff9955),
            Role::Hot => Rgb::hex(0xff4d4d),
            Role::Keycap => Rgb::hex(0xd6d6d6),
            Role::Clock => Rgb::hex(0x7f8c96),
            Role::Confirmed => Rgb::hex(0x00ff5f),
            Role::Poi => Rgb::hex(0xc78fff),
            Role::Carrier => Rgb::hex(0xffb347),
            Role::Neutron => STAR_NEUTRON,
            Role::Unfound => Rgb::hex(0xff7ba8),
            Role::Catalog => Rgb::hex(0x5f7f8f),
            Role::Region => Rgb::hex(0xffe9a8),
        }
    }
}

pub const KEY: Rgb = Rgb::hex(0x010101);

pub const STAR_BLACK_HOLE: Rgb = Rgb::hex(0xc7c7c8);
pub const STAR_WOLF_RAYET: Rgb = Rgb::hex(0xffffff);
pub const STAR_HERBIG: Rgb = Rgb::hex(0xf50100);
pub const STAR_O_TYPE: Rgb = Rgb::hex(0x6a5cff);
pub const STAR_NEUTRON: Rgb = Rgb::hex(0x2f9bff);
pub const STAR_WHITE_DWARF: Rgb = Rgb::hex(0xb9ceff);

pub fn star_colour(class: &str) -> Option<Rgb> {
    Some(match kinds::key_of_class(class)? {
        "BH" => STAR_BLACK_HOLE,
        "WR" => STAR_WOLF_RAYET,
        "HERBIG" => STAR_HERBIG,
        "O-TYPE" => STAR_O_TYPE,
        "NEUTRON" => STAR_NEUTRON,
        "WHT DWRF" => STAR_WHITE_DWARF,
        _ => return None,
    })
}

pub const HEADER_TEXT: Rgb = Rgb::hex(0xff8707);
pub const HEADER_BG: Rgb = Rgb::hex(0x612f18);
pub const HEADER_LINE: Rgb = Rgb::hex(0xdc6707);
pub const HEADER_ALPHA: f64 = 0.55;

pub const TABLE_TEXT: Rgb = Rgb::hex(0xff8c1a);
pub const TABLE_ROW: Rgb = Rgb::hex(0x0e0000);
pub const TABLE_ROW_ALT: Rgb = Rgb::hex(0x22140a);
pub const TABLE_TOTAL: Rgb = Rgb::hex(0xffc266);
pub const TABLE_TOTAL_BG: Rgb = Rgb::hex(0x3a2008);
pub const TABLE_SELECTED: Rgb = Rgb::hex(0xff7100);
pub const TABLE_SELECTED_TEXT: Rgb = Rgb::hex(0x000000);
pub const TABLE_FLASH: Rgb = Rgb::hex(0xff7100);
pub const FLASH_TEXT: Rgb = Rgb::hex(0xffffff);
pub const TABLE_HOVER: Rgb = Rgb::hex(0x4a2810);
pub const TABLE_HOVER_TEXT: Rgb = Rgb::hex(0xffffff);

pub const MAP_SPACE: Rgb = Rgb::hex(0x050302);
pub const MAP_STARS: Rgb = Rgb::hex(0x8a7d70);
pub const MAP_BORDER: Rgb = Rgb::hex(0x120804);
pub const MAP_SELECTED: Rgb = Rgb::hex(0xffe08a);
pub const MAP_LABEL: Rgb = Rgb::hex(0xf2d9b8);
pub const MAP_GRADIENT: [Rgb; 10] = [
    Rgb::hex(0x5a0f0f),
    Rgb::hex(0x8e1a14),
    Rgb::hex(0xc0281e),
    Rgb::hex(0xe0521a),
    Rgb::hex(0xf07f16),
    Rgb::hex(0xe8a317),
    Rgb::hex(0xd4c22b),
    Rgb::hex(0xa8cf35),
    Rgb::hex(0x6fcd3c),
    Rgb::hex(0x2ecc40),
];
pub const MAP_FADE: f64 = 0.15;
pub const MAP_ZERO: f64 = 0.5;
pub const SEL_BG: Rgb = Rgb::hex(0x14324e);

pub const FONT_FAMILY: &str = "Consolas";

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Anchor {
    W,
    E,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum CellKind {
    Text,
    Prob,
    Dist,
    Tally,
    Cube,
}

#[derive(Clone, Copy, Debug)]
pub struct Column {
    pub attr: &'static str,
    pub heading: &'static str,
    pub width: usize,
    pub anchor: Anchor,
    pub role: Role,
    pub kind: CellKind,
}

const fn col(
    attr: &'static str,
    heading: &'static str,
    width: usize,
    anchor: Anchor,
    role: Role,
    kind: CellKind,
) -> Column {
    Column { attr, heading, width, anchor, role, kind }
}

fn prob(column: &'static str, role: Role) -> Column {
    col(column, kinds::heading(column), 8, Anchor::E, role, CellKind::Prob)
}

pub fn columns() -> Vec<Column> {
    vec![
        col("system", "SYSTEM", 24, Anchor::W, Role::Fg, CellKind::Text),
        col("type_label", "TYPE", 8, Anchor::W, Role::Dim, CellKind::Text),
        col("dist_ly", "LY", 8, Anchor::E, Role::Dim, CellKind::Dist),
        prob("p_bh", Role::Ok),
        prob("p_wr", Role::Ok),
        prob("p_herbig", Role::Dim),
        prob("p_otype", Role::Dim),
        prob("p_neutron", Role::Dim),
        prob("p_wd", Role::Dim),
    ]
}

pub fn sector_columns() -> Vec<Column> {
    let mut cols = columns();
    cols[0].width = SECTOR_SYSTEM_W;
    cols.insert(0, col("cube", "", CUBE_W, Anchor::W, Role::Dim, CellKind::Cube));
    cols
}

pub const CUBE_W: usize = 3;
pub const SECTOR_SYSTEM_W: usize = 22;
pub const CUBE_LINE: Rgb = Rgb::hex(0x141414);
pub const CUBE_CELL: Rgb = Rgb::hex(0x585858);
pub const CUBE_TARGET: Rgb = Rgb::hex(0x3d8eff);
pub const CUBE_FOOTPRINT: Rgb = Rgb::hex(0x1c3f73);

pub const TALLY: Column = col("kind_count", "Σ", 5, Anchor::E, Role::Dim, CellKind::Tally);

pub fn nearest_columns() -> Vec<Column> {
    vec![
        col("type_label", "NEAREST", 7, Anchor::W, Role::Dim, CellKind::Text),
        col("jumps", "#", 3, Anchor::E, Role::Dim, CellKind::Tally),
        col("system", "NEXT", 26, Anchor::W, Role::Fg, CellKind::Text),
    ]
}

pub fn confirmed_columns() -> Vec<Column> {
    let mut cols: Vec<Column> = columns().into_iter().filter(|c| c.kind != CellKind::Prob).collect();
    cols[0].heading = "CONFIRMED";
    cols.push(TALLY);
    cols
}

pub fn assert_columns_cover_kinds() {
    let mut shown: Vec<&str> =
        columns().iter().filter(|c| c.kind == CellKind::Prob).map(|c| c.attr).collect();
    let mut known: Vec<&str> = kinds::KINDS.iter().map(|k| k.column).collect();
    shown.sort_unstable();
    known.sort_unstable();
    assert_eq!(shown, known, "theme columns and kinds disagree about which predictions exist");
}

pub const JUMP_ORANGE: Rgb = Rgb::hex(0xff6f00);
pub const JUMP_DIM: Rgb = Rgb::hex(0x5f3003);
pub const JUMP_CYAN: Rgb = Rgb::hex(0x54dfed);
pub const JUMP_TEAL: Rgb = Rgb::hex(0x008b8b);
pub const JUMP_TEAL_DIM: Rgb = Rgb::hex(0x005353);
pub const JUMP_RULE: i32 = 7;
pub const JUMP_GAP: i32 = 4;
pub const JUMP_PAD: i32 = 8;
pub const JUMP_TICK: i32 = 6;
pub const JUMP_BAR: i32 = 4;
pub const JUMP_MIN_W: i32 = 90;
pub const JUMP_MIN_GAP: i32 = 3;
pub const TOP_TABLE_GAP: i32 = 4;
pub const TOP_FONT_DROP: i32 = 2;

pub const PAD_X: i32 = 6;
pub const FOOTER_GAP: i32 = 7;
pub const EDGE_MARGIN: i32 = 8;

pub const MIN_SHOWN_PROBABILITY: f64 = 0.01;

pub const GRADIENT: [Rgb; 10] = [
    Rgb::hex(0xff4d4d),
    Rgb::hex(0xff6a3d),
    Rgb::hex(0xff8730),
    Rgb::hex(0xffa424),
    Rgb::hex(0xffc01a),
    Rgb::hex(0xffd633),
    Rgb::hex(0xe8e04a),
    Rgb::hex(0xc2e04f),
    Rgb::hex(0x8ed957),
    Rgb::hex(0x39ff14),
];
pub const GRADIENT_MIN: f64 = 0.05;
pub const GRADIENT_MAX: f64 = 0.60;

pub const FLASH_CONFIRM: Rgb = Rgb::hex(0xffffff);
pub const FLASH_APPEAR: Rgb = Rgb::hex(0xbfe8ff);
pub const FLASH_COPIED: Rgb = Rgb::hex(0xffd27f);
pub const FLASH_STEPS: u32 = 12;
pub const FLASH_STEP_MS: u32 = 60;

pub const COUNT_GRADIENT_MIN: f64 = 0.1;
pub const COUNT_GRADIENT_MAX: f64 = 100.0;

pub fn blend(start: Rgb, end: Rgb, t: f64) -> Rgb {
    let mix = |a: u8, b: u8| round_half_even(a as f64 + (b as f64 - a as f64) * t) as u8;
    Rgb(mix(start.0, end.0), mix(start.1, end.1), mix(start.2, end.2))
}

pub fn round_half_even(v: f64) -> f64 {
    let r = v.round();
    if (v - v.trunc()).abs() == 0.5 && r % 2.0 != 0.0 { r - v.signum() } else { r }
}
