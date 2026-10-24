use std::cell::RefCell;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    GetMonitorInfoW, MONITOR_DEFAULTTOPRIMARY, MONITORINFO, MonitorFromWindow, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, COLOR_BTNFACE, CreateFontW, DEFAULT_CHARSET, DeleteObject, FF_DONTCARE,
    FF_MODERN, FIXED_PITCH, FW_NORMAL, HBRUSH, HDC, HFONT, HGDIOBJ, OUT_DEFAULT_PRECIS, VARIABLE_PITCH, CreateSolidBrush,
    SetBkColor, SetTextColor, DT_CENTER, DT_NOPREFIX, DT_SINGLELINE, DT_VCENTER, DrawTextW, InvalidateRect, SetBkMode,
    SelectObject, TRANSPARENT,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Controls::{
    EM_GETFIRSTVISIBLELINE, EM_GETSEL, EM_LINEFROMCHAR, EM_LINEINDEX, EM_LINESCROLL, EM_REPLACESEL, EM_SETLIMITTEXT,
    EM_SETSEL, ICC_LISTVIEW_CLASSES, ICC_STANDARD_CLASSES, ICC_TAB_CLASSES, INITCOMMONCONTROLSEX,
    DRAWITEMSTRUCT, InitCommonControlsEx, LVN_COLUMNCLICK, ODS_SELECTED, LVN_ITEMCHANGING, NM_CUSTOMDRAW, NMHDR, NMLISTVIEW, SetWindowTheme,
    TCIF_TEXT, TCITEMW, TCM_ADJUSTRECT, TCM_GETCURSEL, TCM_INSERTITEMW, TCN_SELCHANGE, WC_TABCONTROLW,
};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{
    BM_GETCHECK, BN_CLICKED, BS_AUTOCHECKBOX, BS_OWNERDRAW, CB_ADDSTRING, CB_GETCURSEL, CB_SETCURSEL, CBN_SELCHANGE, CBS_DROPDOWNLIST, CW_USEDEFAULT, CreateWindowExW, HWND_BOTTOM, HWND_TOP,
    DefWindowProcW, ES_AUTOVSCROLL, ES_MULTILINE, ES_NOHIDESEL, ES_READONLY, GetClientRect, GetScrollInfo,
    GetSystemMetrics, HICON, IDC_ARROW, IMAGE_ICON, KillTimer, LR_DEFAULTCOLOR, LoadCursorW, LoadImageW, MoveWindow,
    PostQuitMessage, RegisterClassExW, SB_VERT, SCROLLINFO, SIF_ALL, SM_CXICON, SM_CXSMICON, SW_HIDE, SW_SHOW,
    SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SYSTEM_METRICS_INDEX, SendMessageW, SetTimer,
    SetWindowPos, SetWindowTextW, ShowWindow, WINDOW_EX_STYLE, WINDOW_STYLE, WM_COMMAND, WM_CTLCOLORSTATIC, WM_DESTROY, WM_DRAWITEM, WM_DPICHANGED, WM_NOTIFY,
    WM_SETFONT, WM_SIZE, WM_TIMER, WNDCLASSEXW, WS_CHILD, WS_CLIPCHILDREN, WS_CLIPSIBLINGS, WS_EX_CLIENTEDGE,
    WS_OVERLAPPEDWINDOW, WS_TABSTOP, WS_VISIBLE, WS_VSCROLL,
};
use windows::core::{PCWSTR, PWSTR, w};

use crate::database::{MapGrid, OutcomeRow, RegionExpected, TradeRow};
use crate::market::Quotes;
use crate::kinds::KINDS;
use crate::theme::{FLASH_TEXT, HEADER_BG, HEADER_LINE, HEADER_TEXT, TABLE_FLASH, TABLE_ROW};
use crate::win::expected_table::{ExpectedTable, colorref, fill, list_height};
use crate::win::hotkeys::BINDINGS;
use crate::win::map::{MapLayout, MapView};
use crate::win::settings::{OutcomeTables, SettingsTable};
use crate::win::trade::TradeTable;

pub const TITLE: &str = "Explorers Companion";

const LOG_TIMER: usize = 1;
const LOG_POLL_MS: u32 = 250;
const FLASH_TIMER: usize = 2;
const FLASH_MS: u32 = 350;
const ROUTE_FLASH_TIMER: usize = 3;
const LOG_BACKLOG_BYTES: u64 = 512 << 10;
const LOG_MAX_CHARS: usize = 2 << 20;
const LOG_KEEP_CHARS: usize = 1 << 20;

const MAP_TAB: usize = 0;
const REGIONS_TAB: usize = 1;
const TRADE_TAB: usize = 2;
const ENGINEERS_TAB: usize = 3;
const GUARDIAN_TAB: usize = 4;
const THARGOID_TAB: usize = 5;
const CARRIER_TAB: usize = 6;
const SETTINGS_TAB: usize = 7;
const LOG_TAB: usize = 8;
const TAB_NAMES: [&str; 9] = ["Map", "Regions", "Trade", "Engineers", "Guardian", "Thargoid", "Carrier", "Settings", "Log"];
const APP_ICON: u16 = 1;

const MIN_SECTOR_ROWS: usize = 5;
const MAP_BAND: i32 = 34;
const MAP_CAPTION: i32 = 44;
const SECTOR_WIDTH: i32 = 360;
const REGION_TOTAL: &str = "Region total";
const NO_SECTORS: &str = "<none>";
const SECTOR_ZERO: f64 = 0.05;
const COMBO_WIDTH: i32 = 220;
const COMBO_DROP: i32 = 220;
const CHECK_WIDTH: i32 = 150;
const CHECK_HEIGHT: i32 = 22;
const INCLUDE_CATALOGUED: &str = "Include plot only";
const ROUTE_WIDTH: i32 = 110;
const CARRIER_ROUTE: &str = "Carrier Route";
const GAP: i32 = 8;

pub enum UiAsk {
    Regions,
    MapRegions { catalogued: bool },
    MapGrid,
    Trade,
    Engineers,
    Alien,
    Carrier,
    CarrierRoute,
    Outcomes,
    Sectors { region_id: i64, catalogued: bool, column: &'static str, limit: i64 },
    SectorBest { sector: String, catalogued: bool, column: &'static str, kind: &'static str },
}

thread_local! {
    static MAIN: RefCell<Option<MainWindow>> = const { RefCell::new(None) };
    static ASKS: RefCell<Vec<UiAsk>> = RefCell::new(vec![UiAsk::Regions, UiAsk::MapRegions { catalogued: false }, UiAsk::MapGrid, UiAsk::Outcomes]);
}

pub fn take_asks() -> Vec<UiAsk> {
    ASKS.with(|q| std::mem::take(&mut *q.borrow_mut()))
}

fn push_ask(ask: UiAsk) {
    ASKS.with(|q| q.borrow_mut().push(ask));
}

pub fn show_regions(rows: Vec<RegionExpected>) {
    with_main(|m| m.regions.show(rows));
}

pub fn show_map_regions(rows: Vec<RegionExpected>) {
    with_main(|m| m.map.show_regions(&rows));
}

pub fn show_sectors(mut rows: Vec<RegionExpected>) {
    with_main(|m| {
        let kind = m.map.kind();
        rows.retain(|r| r.p[kind] >= SECTOR_ZERO);
        let total = m.map.selected_total(REGION_TOTAL);
        m.sectors.show_with_total(rows, total);
        m.sectors.sort_by_kind(m.map.kind());
    });
}

pub fn show_trade(rows: Vec<TradeRow>) {
    with_main(|m| m.trade.show_rows(rows));
}

pub fn show_engineers(rows: Vec<TradeRow>) {
    with_main(|m| m.engineers.show_rows(rows));
}

pub fn show_guardian(rows: Vec<TradeRow>) {
    with_main(|m| m.guardian.show_rows(rows));
}

pub fn show_thargoid(rows: Vec<TradeRow>) {
    with_main(|m| m.thargoid.show_rows(rows));
}

pub fn show_carrier(rows: Vec<TradeRow>) {
    with_main(|m| m.carrier.show_rows(rows));
}

pub fn show_tritium(quotes: Quotes) {
    with_main(|m| m.carrier.show_tritium(quotes));
}

pub fn refresh_settings() {
    with_main(|m| m.settings.refresh());
}

pub fn show_outcomes(rows: Vec<OutcomeRow>) {
    with_main(|m| m.outcomes.show(&rows));
}

pub fn show_map_grid(grid: MapGrid) {
    with_main(|m| m.map.show_grid(grid));
}

pub(super) fn with_map<R>(f: impl FnOnce(&mut MapView) -> R) -> Option<R> {
    with_main(|m| f(&mut m.map))
}

pub(super) fn region_clicked(region_id: i64) {
    with_main(|m| m.ask_sectors(Some(region_id)));
}

pub(super) fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

pub(super) fn send(hwnd: HWND, msg: u32, wparam: usize, lparam: isize) -> isize {
    unsafe { SendMessageW(hwnd, msg, Some(WPARAM(wparam)), Some(LPARAM(lparam))).0 }
}

fn app_icon(instance: HINSTANCE, metric: SYSTEM_METRICS_INDEX) -> HICON {
    let size = unsafe { GetSystemMetrics(metric) };
    unsafe { LoadImageW(Some(instance), PCWSTR(APP_ICON as usize as *const u16), IMAGE_ICON, size, size, LR_DEFAULTCOLOR) }
        .map(|h| HICON(h.0))
        .unwrap_or_default()
}

fn font(name: &str, pt: i32, dpi: i32, family: u32) -> HFONT {
    let face = wide(name);
    unsafe {
        CreateFontW(
            -(pt * dpi / 72),
            0,
            0,
            0,
            FW_NORMAL.0 as i32,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            CLEARTYPE_QUALITY,
            family,
            PCWSTR(face.as_ptr()),
        )
    }
}

struct Fonts {
    ui: HFONT,
    small: HFONT,
    mono: HFONT,
}

impl Fonts {
    fn new(dpi: i32) -> Fonts {
        let sans = (VARIABLE_PITCH.0 | FF_DONTCARE.0) as u32;
        Fonts {
            ui: font("Segoe UI", 9, dpi, sans),
            small: font("Segoe UI", 8, dpi, sans),
            mono: font("Consolas", 10, dpi, (FIXED_PITCH.0 | FF_MODERN.0) as u32),
        }
    }
}

impl Drop for Fonts {
    fn drop(&mut self) {
        unsafe {
            let _ = DeleteObject(HGDIOBJ(self.ui.0));
            let _ = DeleteObject(HGDIOBJ(self.small.0));
            let _ = DeleteObject(HGDIOBJ(self.mono.0));
        }
    }
}

struct LogView {
    edit: HWND,
    path: PathBuf,
    offset: u64,
    pending: Vec<u8>,
    chars: usize,
}

impl LogView {
    fn read_new(&mut self) -> Option<String> {
        let mut file = File::open(&self.path).ok()?;
        let len = file.metadata().ok()?.len();
        if len < self.offset {
            self.offset = 0;
            self.pending.clear();
        }
        if len == self.offset {
            return None;
        }
        let first = self.offset == 0 && self.chars == 0;
        let start = if first { len.saturating_sub(LOG_BACKLOG_BYTES) } else { self.offset };
        file.seek(SeekFrom::Start(start)).ok()?;
        let mut bytes = Vec::with_capacity((len - start) as usize);
        file.take(len - start).read_to_end(&mut bytes).ok()?;
        self.offset = start + bytes.len() as u64;
        if first && start > 0 {
            let cut = bytes.iter().position(|&b| b == b'\n').map_or(bytes.len(), |i| i + 1);
            bytes.drain(..cut);
        }
        self.pending.extend_from_slice(&bytes);
        let end = self.pending.iter().rposition(|&b| b == b'\n')? + 1;
        let complete: Vec<u8> = self.pending.drain(..end).collect();
        let text = String::from_utf8_lossy(&complete).replace("\r\n", "\n").replace('\n', "\r\n");
        Some(text)
    }

    fn poll(&mut self) {
        let Some(text) = self.read_new() else { return };
        let mut info = SCROLLINFO { cbSize: std::mem::size_of::<SCROLLINFO>() as u32, fMask: SIF_ALL, ..Default::default() };
        let at_bottom = unsafe { GetScrollInfo(self.edit, SB_VERT, &mut info) }.is_err()
            || info.nPos + info.nPage as i32 >= info.nMax;
        let first_line = send(self.edit, EM_GETFIRSTVISIBLELINE, 0, 0);
        let (mut sel_start, mut sel_end) = (0u32, 0u32);
        send(self.edit, EM_GETSEL, &mut sel_start as *mut u32 as usize, &mut sel_end as *mut u32 as isize);

        let removed = self.trim(text.encode_utf16().count());
        let body = wide(&text);
        send(self.edit, EM_SETSEL, self.chars, self.chars as isize);
        send(self.edit, EM_REPLACESEL, 0, body.as_ptr() as isize);
        self.chars += body.len() - 1;

        if at_bottom {
            return;
        }
        let keep = |p: u32| (p as usize).saturating_sub(removed);
        send(self.edit, EM_SETSEL, keep(sel_start), keep(sel_end) as isize);
        let removed_lines = if removed == 0 { 0 } else { send(self.edit, EM_LINEFROMCHAR, 0, 0) };
        let target = (first_line - removed_lines).max(0);
        let now = send(self.edit, EM_GETFIRSTVISIBLELINE, 0, 0);
        send(self.edit, EM_LINESCROLL, 0, target - now);
    }

    fn trim(&mut self, incoming: usize) -> usize {
        if self.chars + incoming <= LOG_MAX_CHARS {
            return 0;
        }
        let cut_at = (self.chars + incoming).saturating_sub(LOG_KEEP_CHARS).min(self.chars);
        let line = send(self.edit, EM_LINEFROMCHAR, cut_at, 0);
        let next = send(self.edit, EM_LINEINDEX, (line + 1) as usize, 0);
        let cut = if next < 0 { self.chars } else { next as usize };
        let empty = wide("");
        send(self.edit, EM_SETSEL, 0, cut as isize);
        send(self.edit, EM_REPLACESEL, 0, empty.as_ptr() as isize);
        self.chars -= cut;
        cut
    }
}

pub struct MainWindow {
    hwnd: HWND,
    tabs: HWND,
    pages: Vec<Vec<HWND>>,
    log: LogView,
    regions: ExpectedTable,
    sectors: ExpectedTable,
    sector_rows: usize,
    map: MapView,
    trade: TradeTable,
    engineers: TradeTable,
    guardian: TradeTable,
    thargoid: TradeTable,
    carrier: TradeTable,
    settings: SettingsTable,
    outcomes: OutcomeTables,
    combo: HWND,
    catalogued: HWND,
    route: HWND,
    route_flash: bool,
    band: HBRUSH,
    fonts: Fonts,
}

impl MainWindow {
    pub fn open(log_path: &Path) -> Result<(), String> {
        let window = MainWindow::create(log_path)?;
        MAIN.with(|cell| *cell.borrow_mut() = Some(window));
        with_main(|m| {
            m.log.poll();
            unsafe { SetTimer(Some(m.hwnd), LOG_TIMER, LOG_POLL_MS, None) };
        });
        Ok(())
    }

    fn create(log_path: &Path) -> Result<MainWindow, String> {
        unsafe {
            let controls = INITCOMMONCONTROLSEX {
                dwSize: std::mem::size_of::<INITCOMMONCONTROLSEX>() as u32,
                dwICC: ICC_TAB_CLASSES | ICC_LISTVIEW_CLASSES | ICC_STANDARD_CLASSES,
            };
            let _ = InitCommonControlsEx(&controls);
            let instance = GetModuleHandleW(None).map_err(|e| e.to_string())?;
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(wndproc),
                hInstance: instance.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                hIcon: app_icon(instance.into(), SM_CXICON),
                hIconSm: app_icon(instance.into(), SM_CXSMICON),
                hbrBackground: HBRUSH((COLOR_BTNFACE.0 + 1) as usize as *mut _),
                lpszClassName: w!("EdOverlayMain"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let title = wide(TITLE);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("EdOverlayMain"),
                PCWSTR(title.as_ptr()),
                WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                None,
                None,
                Some(instance.into()),
                None,
            )
            .map_err(|e| e.to_string())?;
            let dpi = GetDpiForWindow(hwnd).max(96) as i32;
            let (w, h) = (1100 * dpi / 96, 860 * dpi / 96);
            let mut monitor = MONITORINFO { cbSize: std::mem::size_of::<MONITORINFO>() as u32, ..Default::default() };
            let work = if GetMonitorInfoW(MonitorFromWindow(hwnd, MONITOR_DEFAULTTOPRIMARY), &mut monitor).as_bool() {
                monitor.rcWork
            } else {
                RECT { right: w, bottom: h, ..Default::default() }
            };
            let _ = SetWindowPos(hwnd, None, work.right - w, work.top, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
            let child = |class: PCWSTR, ex: WINDOW_EX_STYLE, style: WINDOW_STYLE| {
                CreateWindowExW(ex, class, PCWSTR::null(), WS_CHILD | style, 0, 0, 0, 0, Some(hwnd), None, Some(instance.into()), None)
                    .map_err(|e| e.to_string())
            };
            let tabs = child(WC_TABCONTROLW, WINDOW_EX_STYLE::default(), WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP)?;
            let edit = child(
                w!("EDIT"),
                WS_EX_CLIENTEDGE,
                WS_VISIBLE
                    | WS_VSCROLL
                    | WS_TABSTOP
                    | WINDOW_STYLE((ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | ES_NOHIDESEL) as u32),
            )?;
            send(edit, EM_SETLIMITTEXT, 0x7FFF_FFFE, 0);
            let regions = ExpectedTable::create(hwnd, instance.into(), "Region", Some("Galaxy"), None, 0)?;
            let mut sectors = ExpectedTable::create(hwnd, instance.into(), "Sector", None, Some(0), 1)?;
            sectors.set_empty_label(NO_SECTORS);
            let map = MapView::create(hwnd, instance.into())?;
            let trade = TradeTable::create(hwnd, instance.into(), false)?;
            let engineers = TradeTable::create(hwnd, instance.into(), false)?;
            let guardian = TradeTable::create(hwnd, instance.into(), false)?;
            let thargoid = TradeTable::create(hwnd, instance.into(), false)?;
            let carrier = TradeTable::create(hwnd, instance.into(), true)?;
            let settings = SettingsTable::create(hwnd, instance.into())?;
            let outcomes = OutcomeTables::create(hwnd, instance.into())?;
            let combo = child(w!("COMBOBOX"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WS_VSCROLL | WINDOW_STYLE(CBS_DROPDOWNLIST as u32))?;
            let _ = SetWindowTheme(combo, w!("DarkMode_CFD"), PCWSTR::null());
            for kind in &KINDS {
                let name = wide(&kind.title());
                send(combo, CB_ADDSTRING, 0, name.as_ptr() as isize);
            }
            send(combo, CB_SETCURSEL, 0, 0);
            let catalogued = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_AUTOCHECKBOX as u32))?;
            let _ = SetWindowTheme(catalogued, w!(""), w!(""));
            let label = wide(INCLUDE_CATALOGUED);
            let _ = SetWindowTextW(catalogued, PCWSTR(label.as_ptr()));
            let _ = SetWindowPos(catalogued, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let route = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_OWNERDRAW as u32))?;
            let route_label = wide(CARRIER_ROUTE);
            let _ = SetWindowTextW(route, PCWSTR(route_label.as_ptr()));
            let _ = SetWindowPos(route, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(tabs, Some(HWND_BOTTOM), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(combo, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(sectors.list, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let window = MainWindow {
                hwnd,
                tabs,
                pages: {
                    let mut pages = vec![Vec::new(); TAB_NAMES.len()];
                    pages[MAP_TAB] = vec![combo, catalogued, route, map.hwnd, sectors.list];
                    pages[REGIONS_TAB] = vec![regions.list];
                    pages[TRADE_TAB] = vec![trade.list];
                    pages[ENGINEERS_TAB] = vec![engineers.list];
                    pages[GUARDIAN_TAB] = vec![guardian.list];
                    pages[THARGOID_TAB] = vec![thargoid.list];
                    pages[CARRIER_TAB] = vec![carrier.list];
                    pages[SETTINGS_TAB] = vec![settings.list, outcomes.summary.list, outcomes.systems.list];
                    pages[LOG_TAB] = vec![edit];
                    pages
                },
                log: LogView { edit, path: log_path.to_path_buf(), offset: 0, pending: Vec::new(), chars: 0 },
                regions,
                sectors,
                map,
                trade,
                engineers,
                guardian,
                thargoid,
                carrier,
                settings,
                outcomes,
                combo,
                catalogued,
                route,
                route_flash: false,
                band: CreateSolidBrush(colorref(TABLE_ROW)),
                sector_rows: MIN_SECTOR_ROWS,
                fonts: Fonts::new(dpi),
            };
            for (i, name) in TAB_NAMES.iter().enumerate() {
                window.add_tab(i, name);
            }
            let mut window = window;
            window.apply_fonts();
            window.layout();
            window.show_selected();
            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
            Ok(window)
        }
    }

    fn add_tab(&self, index: usize, label: &str) {
        let mut text = wide(label);
        let item = TCITEMW { mask: TCIF_TEXT, pszText: PWSTR(text.as_mut_ptr()), ..Default::default() };
        send(self.tabs, TCM_INSERTITEMW, index, &item as *const TCITEMW as isize);
    }

    fn apply_fonts(&mut self) {
        let ui = self.fonts.ui.0 as usize;
        send(self.tabs, WM_SETFONT, ui, 1);
        send(self.log.edit, WM_SETFONT, self.fonts.mono.0 as usize, 1);
        send(self.regions.list, WM_SETFONT, ui, 1);
        send(self.sectors.list, WM_SETFONT, ui, 1);
        send(self.trade.list, WM_SETFONT, ui, 1);
        self.trade.autosize();
        send(self.engineers.list, WM_SETFONT, ui, 1);
        self.engineers.autosize();
        send(self.guardian.list, WM_SETFONT, ui, 1);
        self.guardian.autosize();
        send(self.thargoid.list, WM_SETFONT, ui, 1);
        self.thargoid.autosize();
        send(self.carrier.list, WM_SETFONT, ui, 1);
        self.carrier.autosize();
        send(self.settings.list, WM_SETFONT, ui, 1);
        self.settings.autosize();
        send(self.outcomes.summary.list, WM_SETFONT, ui, 1);
        send(self.outcomes.systems.list, WM_SETFONT, ui, 1);
        self.outcomes.autosize();
        send(self.combo, WM_SETFONT, ui, 1);
        send(self.catalogued, WM_SETFONT, ui, 1);
        send(self.route, WM_SETFONT, ui, 1);
        self.regions.autosize();
        self.sectors.autosize();
        self.map.set_fonts(self.fonts.ui, self.fonts.small);
    }

    fn table(&self, hwnd: HWND) -> Option<&ExpectedTable> {
        [&self.regions, &self.sectors].into_iter().find(|t| t.list == hwnd)
    }

    fn table_mut(&mut self, hwnd: HWND) -> Option<&mut ExpectedTable> {
        [&mut self.regions, &mut self.sectors].into_iter().find(|t| t.list == hwnd)
    }

    fn layout(&mut self) {
        let mut client = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut client);
            let _ = MoveWindow(self.tabs, 0, 0, client.right, client.bottom, true);
        }
        let mut page = client;
        send(self.tabs, TCM_ADJUSTRECT, 0, &mut page as *mut RECT as isize);
        let (w, h) = (page.right - page.left, page.bottom - page.top);
        let place = |hwnd: HWND, x: i32, y: i32, cw: i32, ch: i32| unsafe {
            let _ = MoveWindow(hwnd, x, y, cw.max(0), ch.max(0), true);
        };
        for &p in self.pages[LOG_TAB].iter().chain(&self.pages[REGIONS_TAB]).chain(&self.pages[TRADE_TAB]).chain(&self.pages[ENGINEERS_TAB]).chain(&self.pages[GUARDIAN_TAB]).chain(&self.pages[THARGOID_TAB]).chain(&self.pages[CARRIER_TAB]) {
            place(p, page.left, page.top, w, h);
        }
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        let px = |v: i32| v * dpi / 96;
        let bindings_h = list_height(self.settings.list, BINDINGS.len()) + px(4);
        let summary_h = list_height(self.outcomes.summary.list, KINDS.len()) + px(4);
        let summary_top = page.top + bindings_h + px(GAP);
        let systems_top = summary_top + summary_h + px(GAP);
        place(self.settings.list, page.left, page.top, w, bindings_h);
        place(self.outcomes.summary.list, page.left, summary_top, w, summary_h);
        place(self.outcomes.systems.list, page.left, systems_top, w, page.bottom - systems_top);
        let table_w = px(SECTOR_WIDTH).min(w / 2);
        let table_top = page.top + px(MAP_BAND) + px(MAP_CAPTION);
        let one = self.sectors.height_for(1);
        let row = (self.sectors.height_for(2) - one).max(1);
        let fits = ((page.bottom - table_top - px(GAP) - (one - row)) / row).max(0) as usize;
        let rows = fits.saturating_sub(1).max(MIN_SECTOR_ROWS);
        let table_h = self.sectors.height_for(rows + 1) + px(4);
        place(self.map.hwnd, page.left, page.top, w, h);
        place(self.combo, page.left + px(GAP), page.top + px(5), px(COMBO_WIDTH), px(COMBO_DROP));
        place(self.catalogued, page.left + px(GAP * 2 + COMBO_WIDTH), page.top + px(6), px(CHECK_WIDTH), px(CHECK_HEIGHT));
        place(self.route, page.left + px(GAP * 3 + COMBO_WIDTH + CHECK_WIDTH), page.top + px(4), px(ROUTE_WIDTH), px(CHECK_HEIGHT + 4));
        place(self.sectors.list, page.right - table_w, table_top, table_w, table_h.min(page.bottom - table_top));
        self.sectors.autosize();
        self.map.set_layout(MapLayout {
            top: px(MAP_BAND),
            right: table_w + px(GAP),
            caption: px(MAP_CAPTION),
            info_left: px(GAP * 4 + COMBO_WIDTH + CHECK_WIDTH + ROUTE_WIDTH),
        });
        if rows != self.sector_rows {
            self.sector_rows = rows;
            self.map.set_top(rows);
            self.ask_sectors(self.map.selected_region());
        }
    }

    fn show_selected(&self) {
        let selected = send(self.tabs, TCM_GETCURSEL, 0, 0).max(0) as usize;
        if selected == REGIONS_TAB {
            push_ask(UiAsk::Regions);
        }
        if selected == MAP_TAB {
            push_ask(UiAsk::MapRegions { catalogued: self.include_catalogued() });
        }
        if selected == TRADE_TAB {
            push_ask(UiAsk::Trade);
        }
        if selected == ENGINEERS_TAB {
            push_ask(UiAsk::Engineers);
        }
        if selected == CARRIER_TAB {
            push_ask(UiAsk::Carrier);
        }
        if selected == GUARDIAN_TAB || selected == THARGOID_TAB {
            push_ask(UiAsk::Alien);
        }
        if selected == SETTINGS_TAB {
            push_ask(UiAsk::Outcomes);
        }
        if selected != SETTINGS_TAB && crate::win::hotkeys::cancel_capture() {
            self.settings.refresh();
        }
        for (i, page) in self.pages.iter().enumerate() {
            for &p in page {
                unsafe {
                    let _ = ShowWindow(p, if i == selected { SW_SHOW } else { SW_HIDE });
                }
            }
        }
    }

    fn kind_changed(&mut self) {
        let kind = send(self.combo, CB_GETCURSEL, 0, 0);
        if kind < 0 || kind as usize >= KINDS.len() {
            return;
        }
        self.map.set_kind(kind as usize);
        self.sectors.set_kind(kind as usize);
        self.ask_sectors(self.map.selected_region());
    }

    fn ask_sectors(&self, region_id: Option<i64>) {
        if let Some(region_id) = region_id {
            let column = KINDS[self.map.kind()].column;
            let catalogued = self.include_catalogued();
            push_ask(UiAsk::Sectors { region_id, catalogued, column, limit: self.sector_rows as i64 });
        }
    }

    fn include_catalogued(&self) -> bool {
        send(self.catalogued, BM_GETCHECK, 0, 0) == 1
    }

    fn catalogued_changed(&mut self) {
        let catalogued = self.include_catalogued();
        self.map.set_catalogued(catalogued);
        push_ask(UiAsk::MapRegions { catalogued });
        self.ask_sectors(self.map.selected_region());
    }

    fn draw_route(&self, item: &DRAWITEMSTRUCT) {
        let pressed = item.itemState.0 & ODS_SELECTED.0 != 0 || self.route_flash;
        let (back, text) = if pressed { (TABLE_FLASH, FLASH_TEXT) } else { (HEADER_BG, HEADER_TEXT) };
        let r = item.rcItem;
        fill(item.hDC, r, back);
        for edge in [
            RECT { bottom: r.top + 1, ..r },
            RECT { top: r.bottom - 1, ..r },
            RECT { right: r.left + 1, ..r },
            RECT { left: r.right - 1, ..r },
        ] {
            fill(item.hDC, edge, HEADER_LINE);
        }
        let mut label: Vec<u16> = CARRIER_ROUTE.encode_utf16().collect();
        let mut area = r;
        unsafe {
            let old = SelectObject(item.hDC, HGDIOBJ(self.fonts.ui.0));
            SetBkMode(item.hDC, TRANSPARENT);
            SetTextColor(item.hDC, colorref(text));
            DrawTextW(item.hDC, &mut label, &mut area, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
            SelectObject(item.hDC, old);
        }
    }

    fn flash_route(&mut self, on: bool) {
        self.route_flash = on;
        unsafe {
            let _ = InvalidateRect(Some(self.route), None, false);
            if on {
                SetTimer(Some(self.hwnd), ROUTE_FLASH_TIMER, FLASH_MS, None);
            } else {
                let _ = KillTimer(Some(self.hwnd), ROUTE_FLASH_TIMER);
            }
        }
    }

    fn colour_check(&self, dc: HDC) -> LRESULT {
        unsafe {
            SetTextColor(dc, colorref(HEADER_TEXT));
            SetBkColor(dc, colorref(TABLE_ROW));
        }
        LRESULT(self.band.0 as isize)
    }

    fn dpi_changed(&mut self, suggested: &RECT) {
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        self.fonts = Fonts::new(dpi);
        self.apply_fonts();
        unsafe {
            let _ = SetWindowPos(
                self.hwnd,
                None,
                suggested.left,
                suggested.top,
                suggested.right - suggested.left,
                suggested.bottom - suggested.top,
                SWP_NOZORDER | SWP_NOACTIVATE,
            );
        }
        self.layout();
    }
}

fn with_main<R>(f: impl FnOnce(&mut MainWindow) -> R) -> Option<R> {
    MAIN.with(|cell| match cell.try_borrow_mut() {
        Ok(mut guard) => guard.as_mut().map(f),
        Err(_) => None,
    })
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_SIZE => {
            with_main(|m| m.layout());
            LRESULT(0)
        }
        WM_TIMER if wparam.0 == ROUTE_FLASH_TIMER => {
            with_main(|m| m.flash_route(false));
            LRESULT(0)
        }
        WM_DRAWITEM => {
            let item = unsafe { &*(lparam.0 as *const DRAWITEMSTRUCT) };
            let drawn = MAIN.with(|cell| match cell.try_borrow() {
                Ok(guard) => guard.as_ref().filter(|m| m.route == item.hwndItem).map(|m| m.draw_route(item)),
                Err(_) => None,
            });
            match drawn {
                Some(()) => LRESULT(1),
                None => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
            }
        }
        WM_TIMER if wparam.0 == FLASH_TIMER => {
            unsafe {
                let _ = KillTimer(Some(hwnd), FLASH_TIMER);
            }
            with_main(|m| m.sectors.end_flash());
            LRESULT(0)
        }
        WM_TIMER if wparam.0 == LOG_TIMER => {
            with_main(|m| m.log.poll());
            LRESULT(0)
        }
        WM_COMMAND => {
            let code = ((wparam.0 >> 16) & 0xffff) as u32;
            if code == CBN_SELCHANGE {
                with_main(|m| {
                    if m.combo.0 as isize == lparam.0 {
                        m.kind_changed();
                    }
                });
            }
            if code == BN_CLICKED {
                with_main(|m| {
                    if m.catalogued.0 as isize == lparam.0 {
                        m.catalogued_changed();
                    }
                    if m.route.0 as isize == lparam.0 {
                        m.flash_route(true);
                        push_ask(UiAsk::CarrierRoute);
                    }
                });
            }
            LRESULT(0)
        }
        WM_CTLCOLORSTATIC => {
            let checked = MAIN.with(|cell| match cell.try_borrow() {
                Ok(guard) => guard
                    .as_ref()
                    .filter(|m| m.catalogued.0 as isize == lparam.0)
                    .map(|m| m.colour_check(HDC(wparam.0 as *mut _))),
                Err(_) => None,
            });
            checked.unwrap_or_else(|| unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) })
        }
        WM_NOTIFY => {
            let header = unsafe { &*(lparam.0 as *const NMHDR) };
            if header.code == NM_CUSTOMDRAW || header.code == LVN_ITEMCHANGING {
                return MAIN.with(|cell| match cell.try_borrow() {
                    Ok(guard) => match guard.as_ref() {
                        Some(m) if m.trade.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.trade.custom_draw(lparam)
                        }
                        Some(m) if m.trade.list == header.hwndFrom => m.trade.select(lparam),
                        Some(m) if m.engineers.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.engineers.custom_draw(lparam)
                        }
                        Some(m) if m.engineers.list == header.hwndFrom => m.engineers.select(lparam),
                        Some(m) if m.guardian.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.guardian.custom_draw(lparam)
                        }
                        Some(m) if m.guardian.list == header.hwndFrom => m.guardian.select(lparam),
                        Some(m) if m.thargoid.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.thargoid.custom_draw(lparam)
                        }
                        Some(m) if m.thargoid.list == header.hwndFrom => m.thargoid.select(lparam),
                        Some(m) if m.carrier.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.carrier.custom_draw(lparam)
                        }
                        Some(m) if m.carrier.list == header.hwndFrom => m.carrier.select(lparam),
                        Some(m) if m.settings.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.settings.custom_draw(lparam)
                        }
                        Some(m) if m.settings.list == header.hwndFrom => m.settings.select(lparam),
                        Some(m) if m.sectors.list == header.hwndFrom && header.code != NM_CUSTOMDRAW => {
                            if let Some(sector) = m.sectors.pick(lparam) {
                                let kind = &KINDS[m.map.kind()];
                                push_ask(UiAsk::SectorBest {
                                    sector,
                                    catalogued: m.include_catalogued(),
                                    column: kind.column,
                                    kind: kind.name,
                                });
                                unsafe { SetTimer(Some(hwnd), FLASH_TIMER, FLASH_MS, None) };
                            }
                            LRESULT(1)
                        }
                        Some(m) => match [&m.outcomes.summary, &m.outcomes.systems].into_iter().find(|t| t.list == header.hwndFrom) {
                            Some(t) if header.code == NM_CUSTOMDRAW => t.custom_draw(lparam),
                            Some(t) => t.refuse_selection(lparam),
                            None => match m.table(header.hwndFrom) {
                                Some(t) if header.code == NM_CUSTOMDRAW => t.custom_draw(lparam),
                                Some(t) => t.refuse_selection(lparam),
                                None => LRESULT(0),
                            },
                        },
                        None => LRESULT(0),
                    },
                    Err(_) => LRESULT(0),
                });
            }
            if header.code == TCN_SELCHANGE {
                with_main(|m| m.show_selected());
            } else if header.code == LVN_COLUMNCLICK {
                let column = unsafe { (*(lparam.0 as *const NMLISTVIEW)).iSubItem };
                let from = header.hwndFrom;
                with_main(|m| {
                    if let Some(t) = m.table_mut(from) {
                        t.sort_by(column as usize);
                    }
                });
            }
            LRESULT(0)
        }
        WM_DPICHANGED => {
            let suggested = unsafe { *(lparam.0 as *const RECT) };
            with_main(|m| m.dpi_changed(&suggested));
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe {
                let _ = KillTimer(Some(hwnd), LOG_TIMER);
                PostQuitMessage(0);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
