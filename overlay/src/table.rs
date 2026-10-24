use std::collections::HashSet;

use crate::row::*;
use crate::theme::*;

pub const BELOW_THRESHOLD: &str = "-";

fn row_tint(grp: i64) -> Option<Role> {
    Some(match grp {
        ROW_CONFIRMED => Role::Confirmed,
        ROW_POI => Role::Poi,
        ROW_CATALOG => Role::Catalog,
        ROW_TOTAL => Role::Region,
        ROW_CARRIER => Role::Carrier,
        ROW_SECTOR => Role::Head,
        ROW_NEUTRON => Role::Neutron,
        ROW_SECTOR_UNNAMED => Role::Dim,
        ROW_UNFOUND => Role::Unfound,
        ROW_ROUTE => Role::Keycap,
        ROW_REGION => Role::Region,
        _ => return None,
    })
}

pub fn is_count_kind(grp: i64) -> bool {
    matches!(grp, ROW_TOTAL | ROW_SECTOR | ROW_SECTOR_UNNAMED | ROW_REGION)
}

fn group_digits(digits: &str) -> String {
    let mut out = String::with_capacity(digits.len() + digits.len() / 3);
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    out
}

pub fn thousands(value: f64, decimals: usize) -> String {
    let text = format!("{value:.decimals$}");
    let (sign, body) = text.strip_prefix('-').map_or(("", text.as_str()), |b| ("-", b));
    let (int, frac) = body.split_once('.').map_or((body, None), |(i, f)| (i, Some(f)));
    match frac {
        Some(f) => format!("{sign}{}.{f}", group_digits(int)),
        None => format!("{sign}{}", group_digits(int)),
    }
}

pub fn thousands_i(value: i64) -> String {
    let digits = value.unsigned_abs().to_string();
    format!("{}{}", if value < 0 { "-" } else { "" }, group_digits(&digits))
}

pub fn format_probability(value: Option<f64>) -> String {
    match value {
        Some(v) if v >= MIN_SHOWN_PROBABILITY => format!("{v:.2}"),
        _ => BELOW_THRESHOLD.into(),
    }
}

pub fn format_count(value: Option<f64>) -> String {
    match value {
        None => BELOW_THRESHOLD.into(),
        Some(v) if v == 0.0 => BELOW_THRESHOLD.into(),
        Some(v) if v < 0.005 => "<0.01".into(),
        Some(v) => format!("{v:.2}"),
    }
}

pub fn format_tally(value: Option<f64>) -> String {
    match value {
        Some(v) if v != 0.0 => thousands_i(v as i64),
        _ => BELOW_THRESHOLD.into(),
    }
}

pub fn format_distance(value: Option<f64>, approx: bool) -> String {
    match value {
        None => BELOW_THRESHOLD.into(),
        Some(v) if approx => format!("~{}", thousands(v, 0)),
        Some(v) => thousands(v, 0),
    }
}

fn truncate(text: &str, width: usize) -> String {
    if text.chars().count() <= width {
        return text.to_string();
    }
    let mut out: String = text.chars().take(width.saturating_sub(1)).collect();
    out.push('…');
    out
}

pub fn cell_text(row: &Row, col: &Column, selected: bool) -> String {
    if col.kind == CellKind::Text && col.attr == "system" {
        if let Some(t) = row.arrived_text.as_deref().filter(|t| !t.is_empty()) {
            return truncate(t, col.width);
        }
        if selected && row.grp() == ROW_SECTOR
            && let Some(t) = row.copy_text.as_deref().filter(|t| !t.is_empty()) {
                return truncate(t, col.width);
            }
    }
    let text = match col.kind {
        CellKind::Prob if is_count_kind(row.grp()) => format_count(row.number(col.attr)),
        CellKind::Prob => format_probability(row.number(col.attr)),
        CellKind::Tally => format_tally(row.number(col.attr)),
        CellKind::Dist => format_distance(row.number(col.attr), row.dist_approx),
        CellKind::Text => row.text(col.attr).unwrap_or_default(),
        CellKind::Cube => String::new(),
    };
    truncate(&text, col.width)
}

pub fn gradient_colour(value: f64) -> Rgb {
    let span = GRADIENT_MAX - GRADIENT_MIN;
    let frac = if span != 0.0 { (value - GRADIENT_MIN) / span } else { 0.0 };
    let i = (frac * GRADIENT.len() as f64) as i64;
    GRADIENT[i.clamp(0, GRADIENT.len() as i64 - 1) as usize]
}

pub fn count_colour(value: Option<f64>) -> Rgb {
    let Some(v) = value.filter(|v| *v > 0.0) else { return Role::Dim.rgb() };
    let (lo, hi) = (COUNT_GRADIENT_MIN.log10(), COUNT_GRADIENT_MAX.log10());
    let frac = if hi > lo { (v.max(1e-9).log10() - lo) / (hi - lo) } else { 0.0 };
    let i = (frac * GRADIENT.len() as f64) as i64;
    GRADIENT[i.clamp(0, GRADIENT.len() as i64 - 1) as usize]
}

pub fn cell_colour(row: &Row, col: &Column) -> Rgb {
    let grp = row.grp();
    let value = row.number(col.attr);
    if col.kind == CellKind::Prob && !is_count_kind(grp) {
        return match value {
            Some(v) if v >= MIN_SHOWN_PROBABILITY => gradient_colour(v),
            _ => Role::Dim.rgb(),
        };
    }
    if col.attr == "system" {
        if let Some(tint) = row_tint(grp) {
            return tint.rgb();
        }
        if row.star_class.as_deref().is_some_and(|c| !c.is_empty()) {
            return Role::Dim.rgb();
        }
        return col.role.rgb();
    }
    if col.attr == "type_label" && row.mass_code.as_deref() == Some("h") {
        return Role::Hot.rgb();
    }
    if is_count_kind(grp) {
        return if col.kind == CellKind::Prob { count_colour(value) } else { Role::Dim.rgb() };
    }
    col.role.rgb()
}

pub fn wide_span(columns: &[Column]) -> Option<(usize, usize)> {
    let idx: Vec<usize> =
        columns.iter().enumerate().filter(|(_, c)| c.kind == CellKind::Prob).map(|(i, _)| i).collect();
    idx.first().map(|&f| (f, idx.len()))
}

pub struct DrawCell {
    pub text: String,
    pub fg: Rgb,
    pub shown: bool,
    pub cube: Option<[i64; 3]>,
}

pub struct DrawRow {
    pub cells: Vec<DrawCell>,
    pub wide: Option<String>,
    pub selected: bool,
}

pub struct TargetTable {
    pub columns: Vec<Column>,
    pub title: Option<String>,
    pub n_rows: usize,
    pub min_rows: usize,
    pub selected: Option<usize>,
    pub hide_when_empty: bool,
    pub visible: bool,
    rows: Vec<Row>,
    flash: Vec<(String, Rgb, u32)>,
    flash_new: bool,
    keys: Option<HashSet<String>>,
    span: Option<(usize, usize)>,
}

impl TargetTable {
    pub fn new(columns: Vec<Column>, rows: usize, title: &str, hide_when_empty: bool, flash_new: bool) -> TargetTable {
        let span = wide_span(&columns);
        TargetTable {
            columns,
            title: Some(title.to_string()),
            n_rows: rows,
            min_rows: rows,
            selected: None,
            hide_when_empty,
            visible: !hide_when_empty,
            rows: Vec::new(),
            flash: Vec::new(),
            flash_new,
            keys: None,
            span,
        }
    }

    pub fn with_min_rows(mut self, rows: usize) -> TargetTable {
        self.min_rows = rows.min(self.n_rows);
        self
    }

    pub fn shown_rows(&self) -> usize {
        self.rows.len().clamp(self.min_rows, self.n_rows)
    }

    pub fn span(&self) -> Option<(usize, usize)> {
        self.span
    }

    pub fn show(&mut self, rows: Vec<Row>) {
        self.note_arrivals(&rows);
        self.visible = !(self.hide_when_empty && rows.is_empty());
        self.rows = rows;
    }

    pub fn blank(&mut self) {
        self.show(Vec::new());
    }

    fn note_arrivals(&mut self, rows: &[Row]) {
        let keys: HashSet<String> = rows.iter().filter_map(|r| r.system.clone()).filter(|s| !s.is_empty()).collect();
        if self.flash_new
            && let Some(old) = &self.keys {
                let fresh: Vec<String> = keys.difference(old).cloned().collect();
                self.flash(&fresh, FLASH_APPEAR);
            }
        self.keys = Some(keys);
    }

    pub fn set_selected(&mut self, index: Option<usize>) {
        self.selected = index;
    }

    pub fn set_title(&mut self, text: String) {
        self.title = Some(text);
    }

    pub fn flash(&mut self, names: &[String], colour: Rgb) {
        for name in names {
            match self.flash.iter_mut().find(|(n, ..)| n == name) {
                Some(entry) => {
                    entry.1 = colour;
                    entry.2 = 0;
                }
                None => self.flash.push((name.clone(), colour, 0)),
            }
        }
    }

    pub fn flashing(&self) -> bool {
        !self.flash.is_empty()
    }

    pub fn step_flash(&mut self) {
        self.flash.retain(|(_, _, step)| *step < FLASH_STEPS - 1);
        for entry in &mut self.flash {
            entry.2 += 1;
        }
    }

    fn flash_colour(&self, row: &Row, natural: Rgb) -> Option<Rgb> {
        let hit = |name: &Option<String>| {
            name.as_ref().and_then(|n| self.flash.iter().find(|(f, ..)| f == n))
        };
        let (_, colour, step) = hit(&row.system).or_else(|| hit(&row.copy_text))?;
        Some(blend(*colour, natural, (*step).min(FLASH_STEPS) as f64 / FLASH_STEPS as f64))
    }

    pub fn draw_rows(&self) -> Vec<DrawRow> {
        (0..self.shown_rows()).map(|i| self.draw_row(self.rows.get(i), self.selected == Some(i))).collect()
    }

    fn draw_row(&self, row: Option<&Row>, selected: bool) -> DrawRow {
        let wide = row.and_then(|r| r.wide_text.clone()).filter(|t| !t.is_empty() && self.span.is_some());
        let cells = self
            .columns
            .iter()
            .map(|col| {
                if wide.is_some() && col.kind == CellKind::Prob {
                    return DrawCell { text: String::new(), fg: col.role.rgb(), shown: false, cube: None };
                }
                let Some(row) = row else {
                    return DrawCell { text: String::new(), fg: col.role.rgb(), shown: true, cube: None };
                };
                let natural = cell_colour(row, col);
                let fg = if col.attr == "system" { self.flash_colour(row, natural) } else { None };
                let cube = if col.kind == CellKind::Cube { row.cube } else { None };
                DrawCell { text: cell_text(row, col, selected), fg: fg.unwrap_or(natural), shown: true, cube }
            })
            .collect();
        DrawRow { cells, wide, selected: selected && row.is_some() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_like_python() {
        assert_eq!(thousands(1234567.5, 0), "1,234,568");
        assert_eq!(thousands(999.4, 0), "999");
        assert_eq!(thousands_i(-12345), "-12,345");
        assert_eq!(format_count(Some(0.004)), "<0.01");
        assert_eq!(format_probability(Some(0.009)), "-");
        assert_eq!(format_distance(Some(12345.6), true), "~12,346");
        assert_eq!(truncate("abcdef", 4), "abc…");
    }
}
