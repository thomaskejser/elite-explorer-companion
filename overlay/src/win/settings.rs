use std::cell::Cell;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDRF_DODEFAULT, CDRF_NOTIFYITEMDRAW, LVS_REPORT, LVS_SHOWSELALWAYS,
    LVS_SINGLESEL, NMLVCUSTOMDRAW, WC_LISTVIEWW,
};
use windows::Win32::UI::WindowsAndMessaging::{CreateWindowExW, WINDOW_STYLE, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP};
use windows::core::PCWSTR;

use crate::database::OutcomeRow;
use crate::kinds::KINDS;
use crate::table::thousands_i;
use crate::win::hotkeys::{self, BINDINGS};

use super::expected_table::{autosize_columns, colour_row, highlight_selection, insert_columns, redraw, set_cells, style_list};

const COLUMNS: [(&str, bool); 2] = [("Action", false), ("Key", false)];
const WAITING: &str = "press a key\u{2026}  (Esc cancels)";
const NO_OUTCOMES: &str = "no predicted system visited yet: arrive in one and its prediction is recorded here";

pub struct SettingsTable {
    pub list: HWND,
    highlight: Cell<Option<usize>>,
}

fn sentence(text: &str) -> String {
    let mut c = text.chars();
    c.next().map(|f| f.to_uppercase().chain(c).collect()).unwrap_or_default()
}

impl SettingsTable {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<SettingsTable, String> {
        let style = LVS_REPORT | LVS_SINGLESEL | LVS_SHOWSELALWAYS;
        let list = unsafe {
            CreateWindowExW(
                WS_EX_CLIENTEDGE,
                WC_LISTVIEWW,
                PCWSTR::null(),
                WS_CHILD | WS_TABSTOP | WINDOW_STYLE(style),
                0,
                0,
                0,
                0,
                Some(parent),
                None,
                Some(instance),
                None,
            )
        }
        .map_err(|e| e.to_string())?;
        style_list(list);
        insert_columns(list, &COLUMNS);
        let table = SettingsTable { list, highlight: Cell::new(None) };
        table.refresh();
        Ok(table)
    }

    pub fn refresh(&self) {
        let capturing = hotkeys::capturing();
        let cells: Vec<Vec<String>> = BINDINGS
            .iter()
            .map(|(_, action)| {
                let key = if capturing == Some(*action) {
                    WAITING.to_string()
                } else {
                    hotkeys::key_label(&hotkeys::binding(*action))
                };
                vec![sentence(hotkeys::description(*action)), key]
            })
            .collect();
        if capturing.is_none() {
            self.highlight.set(None);
        }
        set_cells(self.list, &cells);
        self.autosize();
        redraw(self.list);
    }

    pub fn autosize(&self) {
        let headings: Vec<&str> = COLUMNS.iter().map(|c| c.0).collect();
        autosize_columns(self.list, &headings);
    }

    pub fn custom_draw(&self, lparam: LPARAM) -> LRESULT {
        let cd = unsafe { &mut *(lparam.0 as *mut NMLVCUSTOMDRAW) };
        if cd.nmcd.dwDrawStage == CDDS_PREPAINT {
            return LRESULT(CDRF_NOTIFYITEMDRAW as isize);
        }
        if cd.nmcd.dwDrawStage != CDDS_ITEMPREPAINT {
            return LRESULT(CDRF_DODEFAULT as isize);
        }
        colour_row(cd, self.highlight.get(), None)
    }

    pub fn select(&self, lparam: LPARAM) -> LRESULT {
        if let Some(item) = highlight_selection(self.list, &self.highlight, lparam) {
            if let Some((_, action)) = BINDINGS.get(item) {
                hotkeys::begin_capture(*action);
                let highlight = self.highlight.get();
                self.refresh();
                self.highlight.set(highlight);
            }
        }
        LRESULT(1)
    }
}

pub struct ReadOnlyTable {
    pub list: HWND,
    headings: Vec<String>,
    highlight: Cell<Option<usize>>,
}

impl ReadOnlyTable {
    pub fn create(parent: HWND, instance: HINSTANCE, columns: &[(String, bool)]) -> Result<ReadOnlyTable, String> {
        let style = LVS_REPORT | LVS_SINGLESEL | LVS_SHOWSELALWAYS;
        let list = unsafe {
            CreateWindowExW(
                WS_EX_CLIENTEDGE,
                WC_LISTVIEWW,
                PCWSTR::null(),
                WS_CHILD | WS_TABSTOP | WINDOW_STYLE(style),
                0,
                0,
                0,
                0,
                Some(parent),
                None,
                Some(instance),
                None,
            )
        }
        .map_err(|e| e.to_string())?;
        style_list(list);
        let refs: Vec<(&str, bool)> = columns.iter().map(|(h, r)| (h.as_str(), *r)).collect();
        insert_columns(list, &refs);
        let table = ReadOnlyTable { list, headings: columns.iter().map(|c| c.0.clone()).collect(), highlight: Cell::new(None) };
        table.autosize();
        Ok(table)
    }

    pub fn show(&self, cells: &[Vec<String>]) {
        self.highlight.set(None);
        set_cells(self.list, cells);
        self.autosize();
        redraw(self.list);
    }

    pub fn autosize(&self) {
        let headings: Vec<&str> = self.headings.iter().map(String::as_str).collect();
        autosize_columns(self.list, &headings);
    }

    pub fn custom_draw(&self, lparam: LPARAM) -> LRESULT {
        let cd = unsafe { &mut *(lparam.0 as *mut NMLVCUSTOMDRAW) };
        if cd.nmcd.dwDrawStage == CDDS_PREPAINT {
            return LRESULT(CDRF_NOTIFYITEMDRAW as isize);
        }
        if cd.nmcd.dwDrawStage != CDDS_ITEMPREPAINT {
            return LRESULT(CDRF_DODEFAULT as isize);
        }
        colour_row(cd, self.highlight.get(), None)
    }

    pub fn refuse_selection(&self, lparam: LPARAM) -> LRESULT {
        highlight_selection(self.list, &self.highlight, lparam);
        LRESULT(1)
    }
}

pub struct OutcomeTables {
    pub summary: ReadOnlyTable,
    pub systems: ReadOnlyTable,
}

fn percent(v: f64) -> String {
    format!("{:.1}%", 100.0 * v)
}

impl OutcomeTables {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<OutcomeTables, String> {
        let summary_columns: Vec<(String, bool)> = [
            ("Prediction accuracy", false),
            ("Visits", true),
            ("Predicted", true),
            ("Found", true),
            ("Fully scanned", true),
            ("Predicted (full)", true),
            ("Found (full)", true),
        ]
        .iter()
        .map(|(h, r)| (h.to_string(), *r))
        .collect();
        let mut system_columns: Vec<(String, bool)> = [("Visited system", false), ("Date", false), ("Predicted from", false), ("Stars", true), ("Complete", false)]
            .iter()
            .map(|(h, r)| (h.to_string(), *r))
            .collect();
        system_columns.extend(KINDS.iter().map(|k| (k.abbr.to_string(), true)));
        let tables = OutcomeTables {
            summary: ReadOnlyTable::create(parent, instance, &summary_columns)?,
            systems: ReadOnlyTable::create(parent, instance, &system_columns)?,
        };
        tables.show(&[]);
        Ok(tables)
    }

    pub fn show(&self, rows: &[OutcomeRow]) {
        let summary: Vec<Vec<String>> = KINDS
            .iter()
            .enumerate()
            .map(|(i, kind)| {
                let measure = |full: bool| -> [String; 3] {
                    let kept: Vec<&OutcomeRow> = rows.iter().filter(|r| r.p[i].is_some() && (!full || r.complete)).collect();
                    if kept.is_empty() {
                        return ["0".into(), "-".into(), "-".into()];
                    }
                    let n = kept.len() as f64;
                    let predicted = kept.iter().filter_map(|r| r.p[i]).sum::<f64>() / n;
                    let found = kept.iter().filter(|r| r.found[i]).count();
                    [thousands_i(kept.len() as i64), percent(predicted), format!("{} ({found})", percent(found as f64 / n))]
                };
                let [n, p, f] = measure(false);
                let [nf, pf, ff] = measure(true);
                vec![kind.title(), n, p, f, nf, pf, ff]
            })
            .collect();
        self.summary.show(&summary);
        let systems: Vec<Vec<String>> = if rows.is_empty() {
            vec![vec![NO_OUTCOMES.to_string()]]
        } else {
            rows.iter()
                .map(|r| {
                    let mut cells = vec![
                        r.system.clone(),
                        r.visited.clone(),
                        if r.is_catalog { "plot only".into() } else { "boxel".into() },
                        thousands_i(r.stars),
                        if r.complete { "all bodies".into() } else { String::new() },
                    ];
                    cells.extend((0..KINDS.len()).map(|i| match r.p[i] {
                        Some(p) => format!("{}{}", percent(p), if r.found[i] { " \u{2713}" } else { "" }),
                        None => "-".into(),
                    }));
                    cells
                })
                .collect()
        };
        self.systems.show(&systems);
    }

    pub fn autosize(&self) {
        self.summary.autosize();
        self.systems.autosize();
    }
}
