use std::cell::Cell;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDRF_DODEFAULT, CDRF_NOTIFYITEMDRAW, LVCF_TEXT, LVCOLUMNW, LVM_SETCOLUMNW,
    LVS_REPORT, LVS_SHOWSELALWAYS, LVS_SINGLESEL, NMLVCUSTOMDRAW, WC_LISTVIEWW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, MoveWindow, WINDOW_STYLE, WM_SETFONT, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP,
};
use windows::core::{PCWSTR, PWSTR};

use crate::database::CodexSection;
use crate::table::{light_years, thousands_i};
use crate::theme::CODEX_CATEGORIES;
use crate::win::clipboard;

use super::expected_table::{
    autosize_columns, colour_row, highlight_selection, insert_columns, list_height, redraw, set_cells, style_list,
};
use super::main_window::{send, wide};

const COLUMNS: [(&str, bool); 4] =
    [("Entry", false), ("Systems reported", true), ("Nearest reported", false), ("Distance (ly)", true)];
const NONE_REPORTED: &str = "<none reported in this region>";
const MIN_ROWS: usize = 3;

pub struct CodexTable {
    pub list: HWND,
    category: &'static str,
    heading: String,
    rows: usize,
    systems: Vec<Option<String>>,
    highlight: Cell<Option<usize>>,
}

impl CodexTable {
    fn create(parent: HWND, instance: HINSTANCE, category: &'static str) -> Result<CodexTable, String> {
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
        let mut table = CodexTable {
            list,
            category,
            heading: String::new(),
            rows: 1,
            systems: Vec::new(),
            highlight: Cell::new(None),
        };
        table.show(None);
        Ok(table)
    }

    fn show(&mut self, section: Option<&CodexSection>) {
        let rows = section.map_or(&[][..], |s| s.rows.as_slice());
        let known = section.map_or(0, |s| s.known);
        self.heading = format!("{}  \u{00B7}  {} of {} not logged", self.category, rows.len(), known);
        let mut text = wide(&self.heading);
        let column = LVCOLUMNW { mask: LVCF_TEXT, pszText: PWSTR(text.as_mut_ptr()), ..Default::default() };
        send(self.list, LVM_SETCOLUMNW, 0, &column as *const LVCOLUMNW as isize);
        let cells: Vec<Vec<String>> = if rows.is_empty() {
            let note = if known == 0 { NONE_REPORTED.to_string() } else { format!("<all {known} logged>") };
            vec![vec![note, String::new(), String::new(), String::new()]]
        } else {
            rows.iter()
                .map(|r| {
                    vec![
                        r.entry.clone(),
                        r.systems.map_or(String::new(), thousands_i),
                        r.nearest.clone().unwrap_or_default(),
                        r.nearest_ly.map_or(String::new(), light_years),
                    ]
                })
                .collect()
        };
        self.rows = cells.len();
        self.systems = rows.iter().map(|r| r.nearest.clone()).collect();
        self.highlight.set(None);
        set_cells(self.list, &cells);
        self.autosize();
        redraw(self.list);
    }

    fn autosize(&self) {
        let mut headings: Vec<&str> = COLUMNS.iter().map(|c| c.0).collect();
        headings[0] = &self.heading;
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
        if let Some(item) = highlight_selection(self.list, &self.highlight, lparam)
            && let Some(Some(system)) = self.systems.get(item)
            && clipboard::copy(system)
        {
            crate::say!("copied {system} to the clipboard");
        }
        LRESULT(1)
    }
}

pub struct CodexTables {
    pub tables: Vec<CodexTable>,
    area: Cell<(i32, i32, i32, i32, i32)>,
}

impl CodexTables {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<CodexTables, String> {
        let tables = CODEX_CATEGORIES.iter().map(|&c| CodexTable::create(parent, instance, c)).collect::<Result<_, _>>()?;
        Ok(CodexTables { tables, area: Cell::new((0, 0, 0, 0, 0)) })
    }

    pub fn lists(&self) -> Vec<HWND> {
        self.tables.iter().map(|t| t.list).collect()
    }

    pub fn find(&self, list: HWND) -> Option<&CodexTable> {
        self.tables.iter().find(|t| t.list == list)
    }

    pub fn set_font(&self, font: usize) {
        for t in &self.tables {
            send(t.list, WM_SETFONT, font, 1);
            t.autosize();
        }
    }

    pub fn show(&mut self, sections: &[CodexSection]) {
        for s in sections.iter().filter(|s| !CODEX_CATEGORIES.contains(&s.category.as_str())) {
            crate::say!("codex: category {} has no table", s.category);
        }
        for t in &mut self.tables {
            t.show(sections.iter().find(|s| s.category == t.category));
        }
        let (left, top, w, h, gap) = self.area.get();
        self.place(left, top, w, h, gap);
    }

    pub fn place(&self, left: i32, top: i32, w: i32, h: i32, gap: i32) {
        self.area.set((left, top, w, h, gap));
        let need: Vec<i32> = self.tables.iter().map(|t| list_height(t.list, t.rows) + gap).collect();
        let split = (1..self.tables.len())
            .min_by_key(|&k| need[..k].iter().sum::<i32>().max(need[k..].iter().sum()))
            .unwrap_or(self.tables.len());
        let column_w = (w - gap) / 2;
        for (column, range) in [(0, 0..split), (1, split..self.tables.len())] {
            let x = left + column * (column_w + gap);
            let total: i32 = need[range.clone()].iter().sum();
            let mut y = top;
            for i in range.clone() {
                let t = &self.tables[i];
                let floor = list_height(t.list, MIN_ROWS.min(t.rows)) + gap;
                let share = if total <= h { need[i] } else { (need[i] as i64 * h as i64 / total.max(1) as i64) as i32 };
                let height = if i + 1 == range.end && total > h { top + h - y } else { share.max(floor.min(need[i])) };
                unsafe {
                    let _ = MoveWindow(t.list, x, y, column_w.max(0), (height - gap).max(0), true);
                }
                y += height;
            }
        }
    }
}
