use std::cmp::Ordering;

use windows::Win32::Foundation::{HINSTANCE, HWND};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::Controls::{
    HDF_SORTDOWN, HDF_SORTUP, HDI_FORMAT, HDITEMW, HDM_GETITEMW, HDM_SETITEMW, LVCF_FMT, LVCF_SUBITEM, LVCF_TEXT,
    LVCFMT_LEFT, LVCFMT_RIGHT, LVCOLUMNW, LVIF_TEXT, LVITEMW, LVM_DELETEALLITEMS, LVM_GETCOLUMNWIDTH, LVM_GETHEADER,
    LVM_GETSTRINGWIDTHW, LVM_INSERTCOLUMNW, LVM_INSERTITEMW, LVM_SETCOLUMNWIDTH, LVM_SETEXTENDEDLISTVIEWSTYLE,
    LVM_SETITEMTEXTW, LVS_EX_DOUBLEBUFFER, LVS_EX_FULLROWSELECT, LVS_EX_GRIDLINES, LVS_REPORT, LVS_SHOWSELALWAYS,
    LVS_SINGLESEL, LVSCW_AUTOSIZE, WC_LISTVIEWW,
};
use windows::Win32::Graphics::Gdi::InvalidateRect;
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, WINDOW_STYLE, WM_SETREDRAW, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP,
};
use windows::core::{PCWSTR, PWSTR};

use crate::database::RegionExpected;
use crate::kinds::{self, KINDS};
use crate::table::{thousands, thousands_i};
use crate::theme::{self, CellKind};

use super::main_window::{send, wide};

const TOTAL_LABEL: &str = "Galaxy";
const HEADER_PAD: i32 = 28;

#[derive(Clone, Copy)]
enum Field {
    Region,
    Systems,
    Expected(usize),
}

struct Column {
    heading: String,
    field: Field,
}

fn columns() -> Vec<Column> {
    let mut out = vec![
        Column { heading: "Region".into(), field: Field::Region },
        Column { heading: "Unvisited systems".into(), field: Field::Systems },
    ];
    for c in theme::columns().into_iter().filter(|c| c.kind == CellKind::Prob) {
        let i = KINDS.iter().position(|k| k.column == c.attr).expect("probability column without a kind");
        out.push(Column { heading: kinds::heading(c.attr).to_string(), field: Field::Expected(i) });
    }
    out
}

fn text(row: &RegionExpected, field: Field) -> String {
    match field {
        Field::Region => row.region.clone(),
        Field::Systems => thousands_i(row.systems),
        Field::Expected(i) => thousands(row.p[i], 0),
    }
}

fn compare(a: &RegionExpected, b: &RegionExpected, field: Field) -> Ordering {
    match field {
        Field::Region => a.region.cmp(&b.region),
        Field::Systems => a.systems.cmp(&b.systems),
        Field::Expected(i) => a.p[i].total_cmp(&b.p[i]),
    }
}

fn total(rows: &[RegionExpected]) -> RegionExpected {
    let mut sum = RegionExpected { region: TOTAL_LABEL.to_string(), systems: 0, p: [0.0; KINDS.len()] };
    for r in rows {
        sum.systems += r.systems;
        for (s, v) in sum.p.iter_mut().zip(r.p) {
            *s += v;
        }
    }
    sum
}

pub struct RegionsView {
    pub list: HWND,
    columns: Vec<Column>,
    rows: Vec<RegionExpected>,
    sort: Option<(usize, bool)>,
}

impl RegionsView {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<RegionsView, String> {
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
        let extended = LVS_EX_FULLROWSELECT | LVS_EX_GRIDLINES | LVS_EX_DOUBLEBUFFER;
        send(list, LVM_SETEXTENDEDLISTVIEWSTYLE, extended as usize, extended as isize);
        let view = RegionsView { list, columns: columns(), rows: Vec::new(), sort: None };
        for (i, c) in view.columns.iter().enumerate() {
            let mut heading = wide(&c.heading);
            let column = LVCOLUMNW {
                mask: LVCF_FMT | LVCF_TEXT | LVCF_SUBITEM,
                fmt: if matches!(c.field, Field::Region) { LVCFMT_LEFT } else { LVCFMT_RIGHT },
                pszText: PWSTR(heading.as_mut_ptr()),
                iSubItem: i as i32,
                ..Default::default()
            };
            send(list, LVM_INSERTCOLUMNW, i, &column as *const LVCOLUMNW as isize);
        }
        view.autosize();
        Ok(view)
    }

    pub fn show(&mut self, rows: Vec<RegionExpected>) {
        self.rows = rows;
        self.fill();
    }

    pub fn sort_by(&mut self, column: usize) {
        let Some(c) = self.columns.get(column) else { return };
        let descending = match self.sort {
            Some((current, desc)) if current == column => !desc,
            _ => !matches!(c.field, Field::Region),
        };
        self.sort = Some((column, descending));
        self.fill();
    }

    fn fill(&self) {
        let mut ordered: Vec<&RegionExpected> = self.rows.iter().collect();
        if let Some((column, descending)) = self.sort {
            let field = self.columns[column].field;
            ordered.sort_by(|a, b| {
                let o = compare(a, b, field);
                if descending { o.reverse() } else { o }
            });
        }
        let galaxy = total(&self.rows);
        send(self.list, WM_SETREDRAW, 0, 0);
        send(self.list, LVM_DELETEALLITEMS, 0, 0);
        for (i, row) in ordered.into_iter().chain(std::iter::once(&galaxy)).enumerate() {
            for (c, column) in self.columns.iter().enumerate() {
                let mut cell = wide(&text(row, column.field));
                let item = LVITEMW {
                    mask: LVIF_TEXT,
                    iItem: i as i32,
                    iSubItem: c as i32,
                    pszText: PWSTR(cell.as_mut_ptr()),
                    ..Default::default()
                };
                let msg = if c == 0 { LVM_INSERTITEMW } else { LVM_SETITEMTEXTW };
                send(self.list, msg, i, &item as *const LVITEMW as isize);
            }
        }
        self.autosize();
        self.mark_sorted();
        send(self.list, WM_SETREDRAW, 1, 0);
        unsafe {
            let _ = InvalidateRect(Some(self.list), None, true);
        }
    }

    pub fn autosize(&self) {
        let pad = HEADER_PAD * unsafe { GetDpiForWindow(self.list) }.max(96) as i32 / 96;
        for (c, column) in self.columns.iter().enumerate() {
            send(self.list, LVM_SETCOLUMNWIDTH, c, LVSCW_AUTOSIZE as isize);
            let content = send(self.list, LVM_GETCOLUMNWIDTH, c, 0) as i32;
            let heading = wide(&column.heading);
            let header = send(self.list, LVM_GETSTRINGWIDTHW, 0, heading.as_ptr() as isize) as i32 + pad;
            send(self.list, LVM_SETCOLUMNWIDTH, c, content.max(header) as isize);
        }
    }

    fn mark_sorted(&self) {
        let header = HWND(send(self.list, LVM_GETHEADER, 0, 0) as *mut _);
        for c in 0..self.columns.len() {
            let mut item = HDITEMW { mask: HDI_FORMAT, ..Default::default() };
            send(header, HDM_GETITEMW, c, &mut item as *mut HDITEMW as isize);
            item.fmt.0 &= !(HDF_SORTUP.0 | HDF_SORTDOWN.0);
            match self.sort {
                Some((sorted, true)) if sorted == c => item.fmt.0 |= HDF_SORTDOWN.0,
                Some((sorted, false)) if sorted == c => item.fmt.0 |= HDF_SORTUP.0,
                _ => {}
            }
            send(header, HDM_SETITEMW, c, &item as *const HDITEMW as isize);
        }
    }
}
