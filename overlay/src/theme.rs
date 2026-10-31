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
pub const STAR_PROTO: Rgb = Rgb::hex(0xf50100);
pub const STAR_O_TYPE: Rgb = Rgb::hex(0x8c84ff);
pub const STAR_B_TYPE: Rgb = Rgb::hex(0xa091ff);
pub const STAR_A_TYPE: Rgb = Rgb::hex(0xc4a4ff);
pub const STAR_F_TYPE: Rgb = Rgb::hex(0xc8c8ff);
pub const STAR_G_TYPE: Rgb = Rgb::hex(0xffff92);
pub const STAR_K_TYPE: Rgb = Rgb::hex(0xff7c44);
pub const STAR_M_TYPE: Rgb = Rgb::hex(0xf43715);
pub const STAR_L_TYPE: Rgb = Rgb::hex(0xf32d00);
pub const STAR_T_TYPE: Rgb = Rgb::hex(0xc41e1e);
pub const STAR_Y_TYPE: Rgb = Rgb::hex(0xf50100);
pub const STAR_CARBON: Rgb = Rgb::hex(0xffff92);
pub const STAR_NEUTRON: Rgb = Rgb::hex(0x2f9bff);
pub const STAR_WHITE_DWARF: Rgb = Rgb::hex(0xb9ceff);

pub fn star_colour(class: &str) -> Option<Rgb> {
    if let Some(rgb) = kinds::key_of_class(class).and_then(kind_colour) {
        return Some(rgb);
    }
    Some(match kinds::letter_of(class) {
        "O" => STAR_O_TYPE,
        "B" => STAR_B_TYPE,
        "A" => STAR_A_TYPE,
        "F" => STAR_F_TYPE,
        "G" => STAR_G_TYPE,
        "K" => STAR_K_TYPE,
        "M" => STAR_M_TYPE,
        "L" => STAR_L_TYPE,
        "T" => STAR_T_TYPE,
        "Y" => STAR_Y_TYPE,
        "TTS" => STAR_PROTO,
        "C" | "CN" | "CJ" | "CH" | "CHd" | "CS" | "MS" | "S" => STAR_CARBON,
        "X" => STAR_BLACK_HOLE,
        c if c.starts_with('D') => STAR_WHITE_DWARF,
        _ => return None,
    })
}

pub fn dot_rank(key: &str) -> u8 {
    match key {
        "BH" => 2,
        "WR" => 1,
        _ => 0,
    }
}

pub fn heading_colour(col: &Column) -> Rgb {
    if col.kind != CellKind::Prob {
        return Role::Head.rgb();
    }
    kinds::column_index(col.attr).and_then(|i| kind_colour(kinds::KINDS[i].key)).unwrap_or(Role::Head.rgb())
}

pub fn kind_colour(key: &str) -> Option<Rgb> {
    Some(match key {
        "BH" => STAR_BLACK_HOLE,
        "WR" => STAR_WOLF_RAYET,
        "HERBIG" => STAR_PROTO,
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
pub const MAP_CONFIRMED: Rgb = Rgb::hex(0xe4e4e4);
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
pub const STATS_KIND: [Rgb; kinds::KINDS.len()] = [
    Rgb::hex(0x3987e5),
    Rgb::hex(0xd95926),
    Rgb::hex(0x199e70),
    Rgb::hex(0xc98500),
    Rgb::hex(0xd55181),
    Rgb::hex(0x008300),
    Rgb::hex(0x9085e9),
];
pub const STATS_GRID: Rgb = Rgb::hex(0x2a1a0c);
pub const STATS_TIP_BG: Rgb = Rgb::hex(0x1c0e04);
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

const SYSTEM: Column = col("system", "SYSTEM", 24, Anchor::W, Role::Fg, CellKind::Text);
const TYPE: Column = col("type_label", "TYPE", 8, Anchor::W, Role::Dim, CellKind::Text);
const LY: Column = col("dist_ly", "LY", 8, Anchor::E, Role::Dim, CellKind::Dist);

pub fn columns() -> Vec<Column> {
    vec![
        SYSTEM,
        TYPE,
        LY,
        prob("p_bh", Role::Ok),
        prob("p_wr", Role::Ok),
        prob("p_herbig", Role::Dim),
        prob("p_otype", Role::Dim),
        prob("p_supergiant", Role::Dim),
        prob("p_neutron", Role::Dim),
        prob("p_wd", Role::Dim),
    ]
}

pub fn sector_columns() -> Vec<Column> {
    let mut cols = columns();
    cols[0].width = SECTOR_SYSTEM_W;
    let at = cols.iter().position(|c| c.attr == "type_label").expect("the sector table starts from the TYPE column");
    cols.splice(at..=at, MASS_COLUMNS);
    cols
}

const MASS_COLUMNS: [Column; 4] = [
    col("n_h", "Σ H", MASS_W, Anchor::E, Role::Dim, CellKind::Tally),
    col("n_g", "Σ G", MASS_W, Anchor::E, Role::Dim, CellKind::Tally),
    col("n_f", "Σ F", MASS_W, Anchor::E, Role::Dim, CellKind::Tally),
    col("n_e", "Σ E", MASS_W, Anchor::E, Role::Dim, CellKind::Tally),
];

pub const MASS_W: usize = 5;
pub const SECTOR_SYSTEM_W: usize = 22;
pub const CUBE_FOOTPRINT: Rgb = Rgb::hex(0x1c3f73);
pub const CUBE_LAYER: Rgb = Rgb::hex(0x3170cc);
pub const TABLE_RULE: Rgb = Rgb::hex(0x4d2605);
pub const TABLE_RULE_STEP: i32 = 3;

pub const TALLY: Column = col("kind_count", "Σ", 5, Anchor::E, Role::Dim, CellKind::Tally);

pub fn nearest_columns() -> Vec<Column> {
    vec![
        col("type_label", "NEAREST", 8, Anchor::W, Role::Dim, CellKind::Text),
        col("system", "SYSTEM", 26, Anchor::W, Role::Fg, CellKind::Text),
        col("dist_ly", "LY", 6, Anchor::E, Role::Dim, CellKind::Dist),
    ]
}

pub fn poi_columns() -> Vec<Column> {
    vec![
        col("detail", "POI", POI_TYPE_W, Anchor::W, Role::Dim, CellKind::Text),
        col("dist_ly", "LY", 6, Anchor::E, Role::Dim, CellKind::Dist),
        col("system", "SYSTEM", 26, Anchor::W, Role::Fg, CellKind::Text),
    ]
}

pub const POI_TYPE_W: usize = 24;

pub fn carrier_jump_columns() -> Vec<Column> {
    vec![
        col("type_label", "CARRIER", POI_TYPE_W, Anchor::W, Role::Dim, CellKind::Text),
        col("dist_ly", "LY", 6, Anchor::E, Role::Dim, CellKind::Dist),
        col("system", "SYSTEM", 26, Anchor::W, Role::Carrier, CellKind::Text),
    ]
}

pub fn confirmed_columns() -> Vec<Column> {
    vec![TYPE, Column { heading: "CONFIRMED", ..SYSTEM }, LY, TALLY]
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
pub const JUMP_CARRIER: Rgb = Rgb::hex(0xffb347);
pub const JUMP_CARRIER_SHUT: Rgb = Rgb::hex(0x8a8a8a);
pub const CARRIER_ICON_SPAN: f64 = 160.0;
pub const CARRIER_ICON_HULL: [(f64, f64); 8] = [
    (-13.0, -80.0),
    (13.0, -80.0),
    (75.0, 38.0),
    (38.0, 76.0),
    (12.0, 60.0),
    (-12.0, 60.0),
    (-38.0, 76.0),
    (-75.0, 38.0),
];
pub const CARRIER_ICON_RING: (f64, f64, f64) = (0.0, 7.0, 37.0);
pub const CARRIER_ICON_BAR: f64 = 15.0;
pub const CARRIER_ICON_RING_STEPS: usize = 16;
pub const CARRIER_ICON_PEN_DIV: i32 = 12;
pub const ROUTE_LINE_MIN_ROWS: i32 = 3;
pub const ROUTE_TICK: i32 = 9;
pub const ROUTE_NEXT: Rgb = Rgb::hex(0xebebeb);
pub const CLOCK_TEXT: Rgb = Rgb::hex(0xf4f4f4);
pub const CLOCK_EDGE: Rgb = Rgb::hex(0x0a0a0a);
pub const ROUTE_CHARS: i32 = 54;
pub const ROUTE_GAP_CHARS: i32 = 2;
pub const ROUTE_TICK_SHORT: i32 = 6;
pub const ROUTE_TICK_H: i32 = 2;
pub const JUMP_GAP: i32 = 4;
pub const JUMP_PAD: i32 = 8;
pub const JUMP_TICK: i32 = 6;
pub const JUMP_BAR: i32 = 4;
pub const TOP_TABLE_GAP: i32 = 4;
pub const SHEET_GAP: i32 = 8;
pub const MINIMAP_ALPHA: f64 = 0.55;
pub const MINIMAP_HERE_TINT: f64 = 0.45;
pub const MINIMAP_MARGIN_DIV: i32 = 3;
pub const MINIMAP_NAME_HERE: Rgb = Rgb::hex(0x8c8c8c);
pub const MINIMAP_NAME: Rgb = Rgb::hex(0x6a6a6a);
pub const MINIMAP_NAME_OFF: Rgb = Rgb::hex(0x4a4a4a);
pub const MINIMAP_NAME_LIT: Rgb = Rgb::hex(0xfff2c8);
pub const SECTOR_FONT_DROP: i32 = 1;
pub const SECTOR_ROW_TRIM: i32 = 1;
pub const PANEL_BG: Rgb = Rgb::hex(0x03040a);
pub const PANEL_ALPHA: f64 = 0.6;
pub const MINIMAP_ROUTE_W: i32 = 2;
pub const MINIMAP_STOP_R: i32 = 2;
pub const MINIMAP_CARRIER_ROUTE: Rgb = Rgb::hex(0x7d6fa8);
pub const MINIMAP_CARRIER_W: i32 = 1;
pub const MINIMAP_CARRIER_STOP_R: i32 = 1;
pub const MINIMAP_DOT: i32 = 2;
pub const MINIMAP_REGION_BORDER: Rgb = Rgb::hex(0x9a7a50);
pub const MINIMAP_REGION_ALPHA: f64 = 0.7;
pub const MINIMAP_STRETCH: [f64; 2] = [0.02, 0.99];
pub const MINIMAP_SAMPLE_STEP: usize = 7;
pub const POPUP_PAD: i32 = 12;
pub const POPUP_GAP: i32 = 3;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_star_takes_its_kind_or_its_letter_colour() {
        assert_eq!(star_colour("H"), Some(STAR_BLACK_HOLE));
        assert_eq!(star_colour("N"), Some(STAR_NEUTRON));
        assert_eq!(star_colour("AeBe"), Some(STAR_PROTO));
        assert_eq!(star_colour("TTS"), Some(STAR_PROTO));
        assert_eq!(star_colour("K"), Some(STAR_K_TYPE));
        assert_eq!(star_colour("M_RedGiant"), Some(STAR_M_TYPE));
        assert_eq!(star_colour("B_BlueWhiteSuperGiant"), Some(STAR_B_TYPE));
        assert_eq!(star_colour("O_BlueWhiteSuperGiant"), Some(STAR_O_TYPE));
        assert_eq!(star_colour("DAV"), Some(STAR_WHITE_DWARF));
        assert_eq!(star_colour("Q"), None);
    }
}
