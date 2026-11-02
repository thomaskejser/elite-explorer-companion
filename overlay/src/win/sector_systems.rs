use std::cell::Cell;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDRF_DODEFAULT, CDRF_NOTIFYITEMDRAW, LVS_REPORT, LVS_SHOWSELALWAYS,
    LVS_SINGLESEL, NMLVCUSTOMDRAW, WC_LISTVIEWW,
};
use windows::Win32::UI::WindowsAndMessaging::{CreateWindowExW, WINDOW_STYLE, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP};
use windows::core::PCWSTR;

use crate::database::SectorSystem;
use crate::win::clipboard;

use super::expected_table::{autosize_columns, colour_row, highlight_selection, insert_columns, redraw, set_cells, style_list};

const COLUMNS: [(&str, bool); 3] = [("System", false), ("Mass code", false), ("Listed as", false)];
const NO_SYSTEMS: &str = "<none tracked>";

pub struct SectorSystemsTable {
    pub list: HWND,
    systems: Vec<String>,
    highlight: Cell<Option<usize>>,
}

impl SectorSystemsTable {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<SectorSystemsTable, String> {
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
        let table = SectorSystemsTable { list, systems: Vec::new(), highlight: Cell::new(None) };
        table.autosize();
        Ok(table)
    }

    pub fn show(&mut self, rows: &[SectorSystem]) {
        let cells: Vec<Vec<String>> = if rows.is_empty() {
            vec![vec![NO_SYSTEMS.to_string(), String::new(), String::new()]]
        } else {
            rows.iter().map(|r| vec![r.system.clone(), r.mass_code.clone().unwrap_or_default(), r.listed_as.clone()]).collect()
        };
        self.systems = rows.iter().map(|r| r.system.clone()).collect();
        self.highlight.set(None);
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
        if let Some(item) = highlight_selection(self.list, &self.highlight, lparam)
            && let Some(system) = self.systems.get(item)
            && clipboard::copy(system)
        {
            crate::say!("copied {system} to the clipboard");
        }
        LRESULT(1)
    }
}
