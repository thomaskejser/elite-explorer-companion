use std::cell::Cell;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDRF_DODEFAULT, CDRF_NOTIFYITEMDRAW, LVS_REPORT, LVS_SHOWSELALWAYS,
    LVS_SINGLESEL, NMLVCUSTOMDRAW, WC_LISTVIEWW,
};
use windows::Win32::UI::WindowsAndMessaging::{CreateWindowExW, WINDOW_STYLE, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP};
use windows::core::PCWSTR;

use crate::win::hotkeys::{self, BINDINGS};

use super::expected_table::{autosize_columns, colour_row, highlight_selection, insert_columns, redraw, set_cells, style_list};

const COLUMNS: [(&str, bool); 2] = [("Action", false), ("Key", false)];
const WAITING: &str = "press a key\u{2026}  (Esc cancels)";

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
