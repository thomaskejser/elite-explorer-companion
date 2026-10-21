use std::cell::Cell;
use std::cmp::Ordering;

use windows::Win32::Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    CreateSolidBrush, DT_END_ELLIPSIS, DT_LEFT, DT_NOPREFIX, DT_RIGHT, DT_SINGLELINE, DT_VCENTER, DeleteObject,
    DrawTextW, FillRect, HDC, HGDIOBJ, InvalidateRect, SetBkMode, SetTextColor, TRANSPARENT,
};
use windows::Win32::UI::Controls::{
    CDDS_ITEMPREPAINT, CDDS_PREPAINT, CDIS_FOCUS, CDIS_SELECTED, CDRF_DODEFAULT, CDRF_NEWFONT, CDRF_NOTIFYITEMDRAW,
    CDRF_SKIPDEFAULT, HDF_RIGHT, HDF_SORTDOWN, HDF_SORTUP, HDI_FORMAT, HDI_TEXT, HDITEMW, HDM_GETITEMW,
    HDM_SETITEMW, LVCF_FMT, LVCF_SUBITEM, LVCF_TEXT, LVCFMT_LEFT, LVCFMT_RIGHT, LVCOLUMNW, LVIF_STATE, LVIF_TEXT,
    LVIS_SELECTED, LVITEMW, LVM_APPROXIMATEVIEWRECT, LVM_DELETEALLITEMS, LVM_GETCOLUMNWIDTH, LVM_GETHEADER,
    LVM_GETITEMCOUNT, LVM_GETSTRINGWIDTHW, LVM_INSERTCOLUMNW, LVM_INSERTITEMW, LVM_REDRAWITEMS, LVM_SETBKCOLOR,
    LVM_SETCOLUMNW, LVM_SETCOLUMNWIDTH, LVM_SETEXTENDEDLISTVIEWSTYLE, LVM_SETITEMTEXTW, LVM_SETTEXTBKCOLOR,
    LVM_SETTEXTCOLOR,
    LVS_EX_DOUBLEBUFFER, LVS_EX_FULLROWSELECT, LVS_REPORT, LVS_SHOWSELALWAYS, LVS_SINGLESEL, LVSCW_AUTOSIZE,
    NM_CUSTOMDRAW, NMCUSTOMDRAW, NMHDR, NMLISTVIEW, NMLVCUSTOMDRAW, SetWindowTheme, WC_LISTVIEWW,
};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::Shell::{DefSubclassProc, SetWindowSubclass};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, GetClientRect, WINDOW_STYLE, WM_NOTIFY, WM_SETREDRAW, WS_CHILD, WS_EX_CLIENTEDGE, WS_TABSTOP,
};
use windows::core::{PCWSTR, PWSTR, w};

use crate::database::RegionExpected;
use crate::kinds::{self, KINDS};
use crate::table::{thousands, thousands_i};
use crate::theme::{
    self, CellKind, HEADER_BG, HEADER_LINE, HEADER_TEXT, Rgb, TABLE_ROW, TABLE_ROW_ALT, TABLE_SELECTED,
    TABLE_SELECTED_TEXT, TABLE_TEXT, TABLE_TOTAL, TABLE_TOTAL_BG,
};

use super::main_window::{send, wide};

const HEADER_PAD: i32 = 28;
const HEADER_TEXT_PAD: i32 = 6;

pub fn colorref(c: Rgb) -> COLORREF {
    COLORREF(c.0 as u32 | (c.1 as u32) << 8 | (c.2 as u32) << 16)
}

unsafe extern "system" fn list_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
    _id: usize,
    _data: usize,
) -> LRESULT {
    if msg == WM_NOTIFY {
        let hdr = unsafe { &*(lparam.0 as *const NMHDR) };
        let header = HWND(send(hwnd, LVM_GETHEADER, 0, 0) as *mut _);
        if hdr.code == NM_CUSTOMDRAW && hdr.hwndFrom == header {
            let cd = unsafe { &*(lparam.0 as *const NMCUSTOMDRAW) };
            if cd.dwDrawStage == CDDS_PREPAINT {
                fill(cd.hdc, cd.rc, HEADER_BG);
                return LRESULT(CDRF_NOTIFYITEMDRAW as isize);
            }
            if cd.dwDrawStage == CDDS_ITEMPREPAINT {
                draw_heading(header, cd.hdc, cd.rc, cd.dwItemSpec);
                return LRESULT(CDRF_SKIPDEFAULT as isize);
            }
        }
    }
    unsafe { DefSubclassProc(hwnd, msg, wparam, lparam) }
}

pub fn fill(dc: HDC, r: RECT, c: Rgb) {
    unsafe {
        let brush = CreateSolidBrush(colorref(c));
        FillRect(dc, &r, brush);
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

fn draw_heading(header: HWND, dc: HDC, r: RECT, index: usize) {
    let mut buffer = [0u16; 128];
    let mut item = HDITEMW {
        mask: HDI_TEXT | HDI_FORMAT,
        pszText: PWSTR(buffer.as_mut_ptr()),
        cchTextMax: buffer.len() as i32,
        ..Default::default()
    };
    send(header, HDM_GETITEMW, index, &mut item as *mut HDITEMW as isize);
    let len = buffer.iter().position(|&c| c == 0).unwrap_or(buffer.len());
    let label = String::from_utf16_lossy(&buffer[..len]);
    let arrow = if item.fmt.0 & HDF_SORTDOWN.0 != 0 {
        Some('\u{25BC}')
    } else if item.fmt.0 & HDF_SORTUP.0 != 0 {
        Some('\u{25B2}')
    } else {
        None
    };
    let right = item.fmt.0 & HDF_RIGHT.0 != 0;
    let shown = match (arrow, right) {
        (Some(a), true) => format!("{a} {label}"),
        (Some(a), false) => format!("{label} {a}"),
        (None, _) => label,
    };
    fill(dc, r, TABLE_ROW);
    fill(dc, RECT { right: r.right - 1, bottom: r.bottom - 2, ..r }, HEADER_BG);
    fill(dc, RECT { top: r.bottom - 2, ..r }, HEADER_LINE);
    let pad = HEADER_TEXT_PAD * unsafe { GetDpiForWindow(header) }.max(96) as i32 / 96;
    let mut text_rect = RECT { left: r.left + pad, right: r.right - 1 - pad, bottom: r.bottom - 2, ..r };
    let mut text: Vec<u16> = shown.encode_utf16().collect();
    let align = if right { DT_RIGHT } else { DT_LEFT };
    unsafe {
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, colorref(HEADER_TEXT));
        DrawTextW(dc, &mut text, &mut text_rect, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS | align);
    }
}

#[derive(Clone, Copy)]
enum Field {
    Name,
    Systems,
    Known,
    Expected(usize),
}

struct Column {
    heading: String,
    field: Field,
}

fn expected_column(kind: usize) -> Column {
    Column { heading: kinds::heading(KINDS[kind].column).to_string(), field: Field::Expected(kind) }
}

fn columns(name_heading: &str, single: Option<usize>) -> Vec<Column> {
    let name = Column { heading: name_heading.into(), field: Field::Name };
    if let Some(kind) = single {
        return vec![name, expected_column(kind)];
    }
    let mut out = vec![
        name,
        Column { heading: "Predicted systems".into(), field: Field::Systems },
        Column { heading: "Visited systems".into(), field: Field::Known },
    ];
    for c in theme::columns().into_iter().filter(|c| c.kind == CellKind::Prob) {
        let i = KINDS.iter().position(|k| k.column == c.attr).expect("probability column without a kind");
        out.push(expected_column(i));
    }
    out
}

fn text(row: &RegionExpected, field: Field, decimals: usize) -> String {
    match field {
        Field::Name => row.region.clone(),
        Field::Systems => thousands_i(row.systems),
        Field::Known => thousands_i(row.known),
        Field::Expected(i) => thousands(row.p[i], decimals),
    }
}

fn compare(a: &RegionExpected, b: &RegionExpected, field: Field) -> Ordering {
    match field {
        Field::Name => a.region.cmp(&b.region),
        Field::Systems => a.systems.cmp(&b.systems),
        Field::Known => a.known.cmp(&b.known),
        Field::Expected(i) => a.p[i].total_cmp(&b.p[i]),
    }
}

fn total(label: &str, rows: &[RegionExpected]) -> RegionExpected {
    let mut sum = RegionExpected { region: label.to_string(), id: None, systems: 0, known: 0, p: [0.0; KINDS.len()] };
    for r in rows {
        sum.systems += r.systems;
        sum.known += r.known;
        for (s, v) in sum.p.iter_mut().zip(r.p) {
            *s += v;
        }
    }
    sum
}

pub struct ExpectedTable {
    pub list: HWND,
    columns: Vec<Column>,
    rows: Vec<RegionExpected>,
    total_label: Option<&'static str>,
    given_total: Option<RegionExpected>,
    single: bool,
    decimals: usize,
    sort: Option<(usize, bool)>,
    highlight: Cell<Option<usize>>,
}

impl ExpectedTable {
    pub fn create(
        parent: HWND,
        instance: HINSTANCE,
        name_heading: &str,
        total_label: Option<&'static str>,
        single: Option<usize>,
        decimals: usize,
    ) -> Result<ExpectedTable, String> {
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
        let extended = LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER;
        send(list, LVM_SETEXTENDEDLISTVIEWSTYLE, extended as usize, extended as isize);
        send(list, LVM_SETBKCOLOR, 0, colorref(TABLE_ROW).0 as isize);
        send(list, LVM_SETTEXTBKCOLOR, 0, colorref(TABLE_ROW).0 as isize);
        send(list, LVM_SETTEXTCOLOR, 0, colorref(TABLE_TEXT).0 as isize);
        let header = HWND(send(list, LVM_GETHEADER, 0, 0) as *mut _);
        unsafe {
            let _ = SetWindowTheme(list, w!("DarkMode_Explorer"), PCWSTR::null());
            let _ = SetWindowTheme(header, w!("DarkMode_ItemsView"), PCWSTR::null());
            let _ = SetWindowSubclass(list, Some(list_proc), 1, 0);
        }
        let table = ExpectedTable {
            list,
            columns: columns(name_heading, single),
            rows: Vec::new(),
            total_label,
            given_total: None,
            single: single.is_some(),
            decimals,
            sort: None,
            highlight: Cell::new(None),
        };
        for (i, c) in table.columns.iter().enumerate() {
            let mut heading = wide(&c.heading);
            let column = LVCOLUMNW {
                mask: LVCF_FMT | LVCF_TEXT | LVCF_SUBITEM,
                fmt: if matches!(c.field, Field::Name) { LVCFMT_LEFT } else { LVCFMT_RIGHT },
                pszText: PWSTR(heading.as_mut_ptr()),
                iSubItem: i as i32,
                ..Default::default()
            };
            send(list, LVM_INSERTCOLUMNW, i, &column as *const LVCOLUMNW as isize);
        }
        table.autosize();
        Ok(table)
    }

    pub fn height_for(&self, rows: usize) -> i32 {
        let size = send(self.list, LVM_APPROXIMATEVIEWRECT, rows, -1);
        ((size >> 16) & 0xffff) as i32
    }

    pub fn custom_draw(&self, lparam: LPARAM) -> LRESULT {
        let cd = unsafe { &mut *(lparam.0 as *mut NMLVCUSTOMDRAW) };
        if cd.nmcd.dwDrawStage == CDDS_PREPAINT {
            return LRESULT(CDRF_NOTIFYITEMDRAW as isize);
        }
        if cd.nmcd.dwDrawStage != CDDS_ITEMPREPAINT {
            return LRESULT(CDRF_DODEFAULT as isize);
        }
        let item = cd.nmcd.dwItemSpec;
        let last = (send(self.list, LVM_GETITEMCOUNT, 0, 0) as usize).saturating_sub(1);
        let (text, back) = if self.highlight.get() == Some(item) {
            (TABLE_SELECTED_TEXT, TABLE_SELECTED)
        } else if item == last && (self.total_label.is_some() || self.given_total.is_some()) && !self.rows.is_empty() {
            (TABLE_TOTAL, TABLE_TOTAL_BG)
        } else if item % 2 == 1 {
            (TABLE_TEXT, TABLE_ROW_ALT)
        } else {
            (TABLE_TEXT, TABLE_ROW)
        };
        cd.clrText = colorref(text);
        cd.clrTextBk = colorref(back);
        cd.nmcd.uItemState.0 &= !(CDIS_SELECTED.0 | CDIS_FOCUS.0);
        LRESULT(CDRF_NEWFONT as isize)
    }

    pub fn refuse_selection(&self, lparam: LPARAM) -> LRESULT {
        let change = unsafe { &*(lparam.0 as *const NMLISTVIEW) };
        let selecting = change.uChanged.0 & LVIF_STATE.0 != 0 && change.uNewState & LVIS_SELECTED.0 != 0;
        if selecting && change.iItem >= 0 {
            let previous = self.highlight.replace(Some(change.iItem as usize));
            for item in [previous, Some(change.iItem as usize)].into_iter().flatten() {
                send(self.list, LVM_REDRAWITEMS, item, item as isize);
            }
        }
        LRESULT(1)
    }

    pub fn show_with_total(&mut self, rows: Vec<RegionExpected>, total: Option<RegionExpected>) {
        self.given_total = total;
        self.show(rows);
    }

    pub fn show(&mut self, rows: Vec<RegionExpected>) {
        self.rows = rows;
        self.fill();
    }

    pub fn sort_by(&mut self, column: usize) {
        let Some(c) = self.columns.get(column) else { return };
        let descending = match self.sort {
            Some((current, desc)) if current == column => !desc,
            _ => !matches!(c.field, Field::Name),
        };
        self.sort = Some((column, descending));
        self.fill();
    }

    pub fn set_kind(&mut self, kind: usize) {
        if !self.single {
            return;
        }
        self.columns[1] = expected_column(kind);
        let mut heading = wide(&self.columns[1].heading);
        let column = LVCOLUMNW { mask: LVCF_TEXT, pszText: PWSTR(heading.as_mut_ptr()), ..Default::default() };
        send(self.list, LVM_SETCOLUMNW, 1, &column as *const LVCOLUMNW as isize);
        self.sort_by_kind(kind);
    }

    pub fn sort_by_kind(&mut self, kind: usize) {
        self.sort = self.columns.iter().position(|c| matches!(c.field, Field::Expected(i) if i == kind)).map(|c| (c, true));
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
        let summary = self.given_total.clone().or_else(|| self.total_label.map(|label| total(label, &self.rows)));
        self.highlight.set(None);
        send(self.list, WM_SETREDRAW, 0, 0);
        send(self.list, LVM_DELETEALLITEMS, 0, 0);
        for (i, row) in ordered.into_iter().chain(summary.as_ref()).enumerate() {
            for (c, column) in self.columns.iter().enumerate() {
                let mut cell = wide(&text(row, column.field, self.decimals));
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
        if self.single {
            let mut client = RECT::default();
            unsafe {
                let _ = GetClientRect(self.list, &mut client);
            }
            let rest: i32 = (1..self.columns.len()).map(|c| send(self.list, LVM_GETCOLUMNWIDTH, c, 0) as i32).sum();
            let name = send(self.list, LVM_GETCOLUMNWIDTH, 0, 0) as i32;
            send(self.list, LVM_SETCOLUMNWIDTH, 0, name.max(client.right - rest) as isize);
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
