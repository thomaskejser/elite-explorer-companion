use std::cell::Cell;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDRF_DODEFAULT, CDRF_NOTIFYITEMDRAW, LVS_REPORT, LVS_SHOWSELALWAYS,
    LVS_SINGLESEL, NMLVCUSTOMDRAW, WC_LISTVIEWW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    BS_PUSHBUTTON, CreateWindowExW, SetWindowTextW, WINDOW_EX_STYLE, WINDOW_STYLE, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP,
};
use windows::core::{PCWSTR, w};

use crate::database::OutcomeRow;
use crate::kinds::KINDS;
use crate::table::thousands_i;
use crate::win::hotkeys::{self, BINDINGS};

use super::expected_table::{autosize_columns, colour_row, highlight_selection, insert_columns, redraw, set_cells, style_list};
use super::main_window::wide;

const WAITING: &str = "press a key\u{2026}  (Esc cancels)";

pub struct KeyBindings {
    pub labels: Vec<HWND>,
    pub buttons: Vec<HWND>,
}

fn sentence(text: &str) -> String {
    let mut c = text.chars();
    c.next().map(|f| f.to_uppercase().chain(c).collect()).unwrap_or_default()
}

fn control(parent: HWND, instance: HINSTANCE, class: PCWSTR, style: WINDOW_STYLE, text: &str) -> Result<HWND, String> {
    let text = wide(text);
    unsafe {
        CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            class,
            PCWSTR(text.as_ptr()),
            WS_CHILD | style,
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
    .map_err(|e| e.to_string())
}

impl KeyBindings {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<KeyBindings, String> {
        let mut keys = KeyBindings { labels: Vec::new(), buttons: Vec::new() };
        for (_, action) in BINDINGS {
            keys.labels.push(control(parent, instance, w!("STATIC"), WINDOW_STYLE(0), &sentence(hotkeys::description(action)))?);
            keys.buttons.push(control(parent, instance, w!("BUTTON"), WS_TABSTOP | WINDOW_STYLE(BS_PUSHBUTTON as u32), "")?);
        }
        keys.refresh();
        Ok(keys)
    }

    pub fn refresh(&self) {
        let capturing = hotkeys::capturing();
        for (&button, (_, action)) in self.buttons.iter().zip(BINDINGS) {
            let key = if capturing == Some(action) { WAITING.to_string() } else { hotkeys::key_label(&hotkeys::binding(action)) };
            let text = wide(&key);
            unsafe {
                let _ = SetWindowTextW(button, PCWSTR(text.as_ptr()));
            }
        }
    }

    pub fn controls(&self) -> Vec<HWND> {
        self.labels.iter().chain(&self.buttons).copied().collect()
    }

    pub fn clicked(&self, button: isize) -> bool {
        let Some(i) = self.buttons.iter().position(|b| b.0 as isize == button) else {
            return false;
        };
        hotkeys::begin_capture(BINDINGS[i].1);
        self.refresh();
        true
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

fn percent(v: f64) -> String {
    format!("{:.1}%", 100.0 * v)
}

pub fn outcome_table(parent: HWND, instance: HINSTANCE) -> Result<ReadOnlyTable, String> {
    let columns: Vec<(String, bool)> = [
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
    let table = ReadOnlyTable::create(parent, instance, &columns)?;
    show_outcome_summary(&table, &[]);
    Ok(table)
}

pub fn show_outcome_summary(table: &ReadOnlyTable, rows: &[OutcomeRow]) {
    let cells: Vec<Vec<String>> = KINDS
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
    table.show(&cells);
}
