use crate::kinds::{self, KINDS};

pub const ROW_CONFIRMED: i64 = -1;
pub const ROW_POI: i64 = 0;
pub const ROW_PREDICTED: i64 = 1;
pub const ROW_CATALOG: i64 = 2;
pub const ROW_TOTAL: i64 = 3;
pub const ROW_CARRIER: i64 = 4;
pub const ROW_SECTOR: i64 = 5;
pub const ROW_NEUTRON: i64 = 6;
pub const ROW_UNFOUND: i64 = 8;
pub const ROW_ROUTE: i64 = 9;
pub const ROW_REGION: i64 = 11;
pub const ROW_SECTOR_UNNAMED: i64 = 12;
pub const MASS_COUNTS: [&str; 4] = ["n_h", "n_g", "n_f", "n_e"];

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Row {
    pub rank: Option<i64>,
    pub n: Option<i64>,
    pub system: Option<String>,
    pub type_label: Option<String>,
    pub dist_ly: Option<f64>,
    pub dist_approx: bool,
    pub p: [Option<f64>; KINDS.len()],
    pub row_grp: Option<i64>,
    pub wide_text: Option<String>,
    pub detail: Option<String>,
    pub mass_code: Option<String>,
    pub boxel: Option<String>,
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub z: Option<f64>,
    pub dist_sol: Option<f64>,
    pub star_class: Option<String>,
    pub copy_text: Option<String>,
    pub candidates: Vec<String>,
    pub kind_count: Option<i64>,
    pub arrived_text: Option<String>,
    pub route: Option<String>,
    pub cube: Option<[i64; 3]>,
    pub mass_n: [Option<i64>; MASS_COUNTS.len()],
}

#[derive(Clone, Debug, PartialEq)]
pub enum Cell {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Text(String),
    List(Vec<Cell>),
}

impl Cell {
    pub fn int(&self) -> Option<i64> {
        match self {
            Cell::Int(i) => Some(*i),
            Cell::Float(f) => Some(*f as i64),
            Cell::Bool(b) => Some(*b as i64),
            _ => None,
        }
    }

    pub fn float(&self) -> Option<f64> {
        match self {
            Cell::Float(f) => Some(*f),
            Cell::Int(i) => Some(*i as f64),
            _ => None,
        }
    }

    pub fn text(&self) -> Option<String> {
        match self {
            Cell::Text(t) => Some(t.clone()),
            Cell::Null => None,
            Cell::Int(i) => Some(i.to_string()),
            Cell::Float(f) => Some(f.to_string()),
            Cell::Bool(b) => Some(b.to_string()),
            Cell::List(_) => None,
        }
    }

    pub fn bool(&self) -> bool {
        matches!(self, Cell::Bool(true)) || matches!(self, Cell::Int(i) if *i != 0)
    }
}

impl Row {
    pub fn from_cells(names: &[String], cells: Vec<Cell>) -> Result<Row, String> {
        let mut row = Row::default();
        for (name, cell) in names.iter().zip(cells) {
            if let Some(i) = kinds::column_index(name) {
                row.p[i] = cell.float();
                continue;
            }
            if let Some(i) = MASS_COUNTS.iter().position(|m| m == name) {
                row.mass_n[i] = cell.int();
                continue;
            }
            match name.as_str() {
                "rank" => row.rank = cell.int(),
                "n" => row.n = cell.int(),
                "system" => row.system = cell.text(),
                "type_label" => row.type_label = cell.text(),
                "dist_ly" => row.dist_ly = cell.float(),
                "dist_approx" => row.dist_approx = cell.bool(),
                "row_grp" => row.row_grp = cell.int(),
                "wide_text" => row.wide_text = cell.text(),
                "detail" => row.detail = cell.text(),
                "mass_code" => row.mass_code = cell.text(),
                "boxel" => row.boxel = cell.text(),
                "x" => row.x = cell.float(),
                "y" => row.y = cell.float(),
                "z" => row.z = cell.float(),
                "dist_sol" => row.dist_sol = cell.float(),
                "star_class" => row.star_class = cell.text(),
                "copy_text" => row.copy_text = cell.text(),
                "kind_count" => row.kind_count = cell.int(),
                "dx" | "dy" | "dz" => {
                    let at = ["dx", "dy", "dz"].iter().position(|a| a == name).unwrap_or(0);
                    if let Some(v) = cell.int() {
                        row.cube.get_or_insert([0; 3])[at] = v;
                    }
                }
                "candidates" => {
                    row.candidates = match cell {
                        Cell::List(items) => items.iter().filter_map(Cell::text).collect(),
                        _ => Vec::new(),
                    }
                }
                other => return Err(format!("query returned a column no row carries: {other}")),
            }
        }
        Ok(row)
    }

    pub fn grp(&self) -> i64 {
        self.row_grp.unwrap_or(i64::MIN)
    }

    pub fn number(&self, attr: &str) -> Option<f64> {
        if let Some(i) = kinds::column_index(attr) {
            return self.p[i];
        }
        if let Some(i) = MASS_COUNTS.iter().position(|m| *m == attr) {
            return self.mass_n[i].map(|v| v as f64);
        }
        match attr {
            "dist_ly" => self.dist_ly,
            "kind_count" => self.kind_count.map(|v| v as f64),
            _ => None,
        }
    }

    pub fn text(&self, attr: &str) -> Option<String> {
        match attr {
            "system" => self.system.clone(),
            "type_label" => self.type_label.clone(),
            "detail" => self.detail.clone(),
            _ => self.number(attr).map(|v| v.to_string()),
        }
    }

    pub fn xyz(&self) -> Option<[f64; 3]> {
        Some([self.x?, self.y?, self.z?])
    }

    pub fn selectable(&self) -> bool {
        match self.grp() {
            ROW_TOTAL | ROW_REGION => false,
            ROW_SECTOR_UNNAMED => self.copy_text.is_some(),
            _ => true,
        }
    }

    pub fn names_a_system(&self) -> bool {
        self.grp() != ROW_SECTOR || self.copy_text.is_some()
    }

    pub fn target(&self) -> Option<&str> {
        self.copy_text.as_deref().filter(|s| !s.is_empty()).or(self.system.as_deref())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sector(copy: Option<&str>, grp: i64) -> Row {
        Row { system: Some("Blau Trua".into()), copy_text: copy.map(String::from), row_grp: Some(grp), ..Row::default() }
    }

    #[test]
    fn an_empty_sector_copies_its_name_but_is_no_guess() {
        let empty = sector(None, ROW_SECTOR);
        assert!(empty.selectable());
        assert_eq!(empty.target(), Some("Blau Trua"));
        assert!(!empty.names_a_system());
        let full = sector(Some("Blau Trua AA-A h1"), ROW_SECTOR);
        assert_eq!(full.target(), Some("Blau Trua AA-A h1"));
        assert!(full.names_a_system());
        assert!(!sector(None, ROW_SECTOR_UNNAMED).selectable());
        assert!(!sector(None, ROW_TOTAL).selectable());
    }
}
