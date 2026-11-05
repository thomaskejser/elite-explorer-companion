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
    DRAWITEMSTRUCT, InitCommonControlsEx, LVN_COLUMNCLICK, ODS_DISABLED, ODS_SELECTED, LVN_ITEMCHANGING, NM_CUSTOMDRAW, NM_DBLCLK, NMHDR, NMLISTVIEW, SetWindowTheme,
    TCIF_TEXT, TCITEMW, TCM_ADJUSTRECT, TCM_GETCURSEL, TCM_INSERTITEMW, TCN_SELCHANGE, WC_TABCONTROLW,
};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::Input::KeyboardAndMouse::SetFocus;
use windows::Win32::UI::WindowsAndMessaging::{
    BM_GETCHECK, BM_SETCHECK, BN_CLICKED, BS_AUTOCHECKBOX, BS_OWNERDRAW, CB_ADDSTRING, CB_GETCURSEL, CB_RESETCONTENT, CB_SETCURSEL, CB_SETEDITSEL,
    CB_SHOWDROPDOWN, CBN_EDITCHANGE, CBN_SELCHANGE, CBN_SELENDOK, CBS_AUTOHSCROLL, CBS_DROPDOWN, CBS_DROPDOWNLIST, CW_USEDEFAULT,
    GetWindowTextLengthW, GetWindowTextW, SetCursor, CreateWindowExW, HWND_BOTTOM, HWND_TOP,
    DefWindowProcW, ES_AUTOHSCROLL, ES_AUTOVSCROLL, ES_MULTILINE, ES_NOHIDESEL, ES_READONLY, GetClientRect, GetScrollInfo,
    GetSystemMetrics, HICON, IDC_ARROW, IMAGE_ICON, KillTimer, LR_DEFAULTCOLOR, LoadCursorW, LoadImageW, MoveWindow,
    PostQuitMessage, RegisterClassExW, SB_VERT, SCROLLINFO, SIF_ALL, SM_CXICON, SM_CXSMICON, SW_HIDE, SW_SHOW,
    SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SYSTEM_METRICS_INDEX, SendMessageW, SetTimer,
    SetWindowPos, SetWindowTextW, ShowWindow, WINDOW_EX_STYLE, WINDOW_STYLE, WM_COMMAND, WM_CTLCOLOREDIT, WM_CTLCOLORSTATIC, WM_DESTROY, WM_DRAWITEM, WM_DPICHANGED, WM_NOTIFY,
    WM_SETFONT, WM_SIZE, WM_TIMER, WNDCLASSEXW, WS_CHILD, WS_CLIPCHILDREN, WS_CLIPSIBLINGS, WS_EX_CLIENTEDGE,
    WS_OVERLAPPEDWINDOW, WS_TABSTOP, WS_VISIBLE, WS_VSCROLL,
};
use windows::core::{PCWSTR, PWSTR, w};

use crate::database::{CodexView, MapGrid, OutcomeRow, RegionExpected, SectorView, Stats, TradeRow};
use crate::market::Quotes;
use crate::kinds::KINDS;
use crate::say;
use crate::theme::{BUTTON_OFF_TEXT, FLASH_TEXT, HEADER_BG, HEADER_LINE, HEADER_TEXT, TABLE_FLASH, TABLE_ROW, TABLE_TEXT};
use crate::win::carrier_card::{CarrierCard, Section};
use crate::win::codex::CodexTables;
use crate::win::expected_table::{ExpectedTable, colorref, fill, fitted_height, list_height, summed};
use crate::win::map::{MapClick, MapLayout, MapView};
use crate::win::sector_systems::SectorSystemsTable;
use crate::win::settings::{KeyBindings, ReadOnlyTable, outcome_table, show_outcome_summary};
use crate::win::stats::StatsView;
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
const CODEX_TAB: usize = 1;
const TRADE_TAB: usize = 2;
const ENGINEERS_TAB: usize = 3;
const GUARDIAN_TAB: usize = 4;
const THARGOID_TAB: usize = 5;
const CARRIER_TAB: usize = 6;
const STATS_TAB: usize = 7;
const SETTINGS_TAB: usize = 8;
const LOG_TAB: usize = 9;
const TAB_NAMES: [&str; 10] = ["Map", "Codex", "Trade", "Engineers", "Guardian", "Thargoid", "Carrier", "Stats", "Settings", "Log"];
const KEYS_PAGE: usize = 1;
const SETTINGS_PAGE_NAMES: [&str; 4] = ["General", "Keybinds", "Mini Map", "Debug"];
const KEY_LABEL_WIDTH: i32 = 440;
const KEY_BUTTON_WIDTH: i32 = 220;
const KEY_ROW: i32 = 30;
const APP_ICON: u16 = 1;

const SECTOR_ROWS: usize = 20;
const SQUARE_TOTAL: &str = "Square total";
const MAP_BAND: i32 = 34;
const SECTOR_WIDTH: i32 = 360;
const NO_SECTORS: &str = "<none>";
const SECTOR_ZERO: f64 = 0.05;
const COMBO_WIDTH: i32 = 220;
const COMBO_DROP: i32 = 220;
const CHECK_WIDTH: i32 = 150;
const CHECK_HEIGHT: i32 = 22;
const INCLUDE_CATALOGUED: &str = "Include plot only";
const KEEP_CAPTURES: &str = "Keep every FSS screenshot (calibration data; otherwise only the latest)";
const KEEP_CAPTURES_WIDTH: i32 = 460;
const PREF_CHECKS: [&str; 5] = [
    "Play sounds",
    "Drive the VKB throttle lights",
    "Global navigation keys",
    "Show the HUD when Elite is not in front",
    "Drag panes with the mouse",
];
const PREF_CHECK_WIDTH: i32 = 270;
const PREF_COLUMNS: i32 = 3;
const SIZE_LABEL: &str = "HUD size (100% fits the game window)";
const OPACITY_LABEL: &str = "HUD opacity";
const PREF_LABEL_WIDTH: i32 = 250;
const MAP_KINDS_LABEL: &str = "Dots on the galaxy map's mini map";
const PREF_COMBO_WIDTH: i32 = 90;
const ROUTE_WIDTH: i32 = 130;
const ZOOM_OUT: &str = "Zoom out";
const ZOOM_WIDTH: i32 = 90;
const MAP_SEARCH_WIDTH: i32 = 220;
const PLOT_CARRIER: &str = "Plot carrier route";
const CARRIER_BUTTONS: [(&str, Option<&str>); 3] = [
    ("To Shinrarta", Some("Shinrarta Dezhra")),
    ("To Colonia", Some("Colonia")),
    ("Carrier Route", None),
];
const CARRIER_FIXED: usize = 2;
const GAP: i32 = 8;
const SEARCH_WIDTH: i32 = 280;
const SEARCH_DROP: i32 = 360;
const SEARCH_MATCHES: usize = 200;
const SECTOR_SYSTEMS_LIMIT: i64 = 20;
const CODEX_COMBO_WIDTH: i32 = 320;

pub enum UiAsk {
    Prefs(crate::prefs::Prefs),
    KeepFssCaptures(bool),
    MapRegions { catalogued: bool },
    RegionSectors { region_id: i64, catalogued: bool },
    MapGrid,
    MapConfirmed,
    Stats,
    Codex { region_id: Option<i64> },
    Trade,
    Engineers,
    Alien,
    Carrier,
    CarrierRoute { destination: Option<String> },
    Outcomes,
    Sectors { region_id: i64, catalogued: bool, column: &'static str, limit: i64 },
    SectorBest { sector: String, catalogued: bool, column: &'static str, kind: &'static str },
    SectorNames,
    SectorView { sector: String, column: &'static str, catalogued: bool, limit: i64, locate: bool },
}

thread_local! {
    static MAIN: RefCell<Option<MainWindow>> = const { RefCell::new(None) };
    static ASKS: RefCell<Vec<UiAsk>> = RefCell::new(vec![UiAsk::MapRegions { catalogued: false }, UiAsk::MapGrid, UiAsk::MapConfirmed, UiAsk::Outcomes]);
}

fn pref_flags(p: &crate::prefs::Prefs) -> [bool; 5] {
    [p.sound, p.lights, p.hotkeys, p.always_visible, p.draggable]
}

pub fn take_asks() -> Vec<UiAsk> {
    ASKS.with(|q| std::mem::take(&mut *q.borrow_mut()))
}

fn push_ask(ask: UiAsk) {
    ASKS.with(|q| q.borrow_mut().push(ask));
}

pub fn show_map_regions(rows: Vec<RegionExpected>) {
    with_main(|m| m.map.show_regions(&rows));
}

pub fn show_region_sectors(region_id: i64, rows: Vec<RegionExpected>, galaxy: [f64; KINDS.len()]) {
    with_main(|m| m.map.show_region_sectors(region_id, rows, galaxy));
}

pub fn show_sector_names(names: Vec<String>) {
    with_main(|m| m.sector_names = names);
}

pub fn show_sector_view(view: SectorView, locate: bool) {
    with_main(|m| m.show_sector_view(view, locate));
}

pub fn show_sectors(mut rows: Vec<RegionExpected>) {
    with_main(|m| {
        if m.square {
            return;
        }
        let kind = m.map.kind();
        rows.retain(|r| r.p[kind] >= SECTOR_ZERO);
        let total = m.map.selected_total();
        m.sectors.show_with_total(rows, total);
        m.sectors.sort_by_kind(m.map.kind());
        m.fit_tables();
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

pub fn show_carrier(sections: Vec<Section>) {
    with_main(|m| m.carrier.show_carrier(sections));
}

pub fn show_tritium(quotes: Quotes) {
    with_main(|m| m.carrier.show_tritium(quotes));
}

pub fn refresh_settings() {
    with_main(|m| m.keys.refresh());
}

pub fn show_outcomes(rows: Vec<OutcomeRow>) {
    with_main(|m| show_outcome_summary(&m.outcomes, &rows));
}

pub fn show_map_grid(grid: MapGrid) {
    with_main(|m| m.map.show_grid(grid));
}

pub fn show_map_confirmed(kinds: Vec<String>, pts: Vec<[f64; 3]>) {
    with_main(|m| m.map.show_confirmed(&kinds, &pts));
}

pub fn show_stats(stats: Stats) {
    with_main(|m| m.stats.show(stats));
}

pub fn show_codex(view: CodexView) {
    with_main(|m| m.show_codex(view));
}

pub(super) fn with_stats<R>(f: impl FnOnce(&mut StatsView) -> R) -> Option<R> {
    with_main(|m| f(&mut m.stats))
}

pub(super) fn with_carrier<R>(f: impl FnOnce(&mut CarrierCard) -> R) -> Option<R> {
    with_main(|m| f(&mut m.carrier))
}

pub(super) fn with_map<R>(hwnd: HWND, f: impl FnOnce(&mut MapView) -> R) -> Option<R> {
    with_main(|m| (m.map.hwnd == hwnd).then(|| f(&mut m.map))).flatten()
}

fn window_text(hwnd: HWND) -> String {
    let mut buffer = vec![0u16; unsafe { GetWindowTextLengthW(hwnd) } as usize + 1];
    let len = unsafe { GetWindowTextW(hwnd, &mut buffer) } as usize;
    String::from_utf16_lossy(&buffer[..len])
}

fn sector_matches(names: &[String], typed: &str) -> Vec<String> {
    let needle = typed.trim().to_lowercase();
    if needle.is_empty() {
        return Vec::new();
    }
    let lower: Vec<String> = names.iter().map(|n| n.to_lowercase()).collect();
    let prefix = names.iter().zip(&lower).filter(|(_, l)| l.starts_with(&needle));
    let inside = names.iter().zip(&lower).filter(|(_, l)| !l.starts_with(&needle) && l.contains(&needle));
    prefix.chain(inside).map(|(n, _)| n.clone()).take(SEARCH_MATCHES).collect()
}

pub(super) fn map_clicked(click: MapClick) {
    with_main(|m| match click {
        MapClick::Region(region_id) => m.ask_sectors(Some(region_id)),
        MapClick::Zoom(region_id) => m.zoom_to(region_id),
        MapClick::Sector(sector) => m.sector_clicked(sector),
        MapClick::Square(rows) => m.show_square(rows),
        MapClick::ZoomOut => m.zoom_out(),
        MapClick::Unnamed => say!("no sector in the model is named for this cell"),
    });
}

fn add_tab(tabs: HWND, index: usize, label: &str) {
    let mut text = wide(label);
    let item = TCITEMW { mask: TCIF_TEXT, pszText: PWSTR(text.as_mut_ptr()), ..Default::default() };
    send(tabs, TCM_INSERTITEMW, index, &item as *const TCITEMW as isize);
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
    big: HFONT,
    mono: HFONT,
}

impl Fonts {
    fn new(dpi: i32) -> Fonts {
        let sans = (VARIABLE_PITCH.0 | FF_DONTCARE.0) as u32;
        Fonts {
            ui: font("Segoe UI", 9, dpi, sans),
            small: font("Segoe UI", 8, dpi, sans),
            big: font("Segoe UI", 12, dpi, sans),
            mono: font("Consolas", 10, dpi, (FIXED_PITCH.0 | FF_MODERN.0) as u32),
        }
    }
}

impl Drop for Fonts {
    fn drop(&mut self) {
        unsafe {
            let _ = DeleteObject(HGDIOBJ(self.ui.0));
            let _ = DeleteObject(HGDIOBJ(self.small.0));
            let _ = DeleteObject(HGDIOBJ(self.big.0));
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
    sectors: ExpectedTable,
    map: MapView,
    zoom_out: HWND,
    sector_search: HWND,
    sector_systems: SectorSystemsTable,
    sector_names: Vec<String>,
    table_box: (i32, i32, i32, i32),
    square: bool,
    sector_matches: Vec<String>,
    trade: TradeTable,
    engineers: TradeTable,
    guardian: TradeTable,
    thargoid: TradeTable,
    carrier: CarrierCard,
    codex: CodexTables,
    codex_region: HWND,
    codex_regions: Vec<i64>,
    codex_pick: Option<i64>,
    stats: StatsView,
    settings_tabs: HWND,
    settings_pages: Vec<Vec<HWND>>,
    keys: KeyBindings,
    outcomes: ReadOnlyTable,
    combo: HWND,
    catalogued: HWND,
    keep_captures: Option<HWND>,
    pref_checks: Vec<HWND>,
    pref_labels: Vec<HWND>,
    pref_combos: Vec<HWND>,
    map_kinds_label: HWND,
    map_kind_checks: Vec<HWND>,
    routes: Vec<HWND>,
    carrier_name: HWND,
    carrier_plot: HWND,
    route_flash: Option<HWND>,
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
            let mut sectors = ExpectedTable::create(hwnd, instance.into(), "Sector", 0, 1)?;
            sectors.set_empty_label(NO_SECTORS);
            let map = MapView::create(hwnd, instance.into())?;
            let sector_systems = SectorSystemsTable::create(hwnd, instance.into())?;
            let zoom_out = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_OWNERDRAW as u32))?;
            let zoom_label = wide(ZOOM_OUT);
            let _ = SetWindowTextW(zoom_out, PCWSTR(zoom_label.as_ptr()));
            let _ = SetWindowPos(zoom_out, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let sector_search = child(
                w!("COMBOBOX"),
                WINDOW_EX_STYLE::default(),
                WS_TABSTOP | WS_VSCROLL | WINDOW_STYLE((CBS_DROPDOWN | CBS_AUTOHSCROLL) as u32),
            )?;
            let _ = SetWindowTheme(sector_search, w!("DarkMode_CFD"), PCWSTR::null());
            let trade = TradeTable::create(hwnd, instance.into())?;
            let engineers = TradeTable::create(hwnd, instance.into())?;
            let guardian = TradeTable::create(hwnd, instance.into())?;
            let thargoid = TradeTable::create(hwnd, instance.into())?;
            let carrier = CarrierCard::create(hwnd, instance.into())?;
            let stats = StatsView::create(hwnd, instance.into())?;
            let codex = CodexTables::create(hwnd, instance.into())?;
            let codex_region =
                child(w!("COMBOBOX"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WS_VSCROLL | WINDOW_STYLE(CBS_DROPDOWNLIST as u32))?;
            let _ = SetWindowTheme(codex_region, w!("DarkMode_CFD"), PCWSTR::null());
            let settings_tabs = child(WC_TABCONTROLW, WINDOW_EX_STYLE::default(), WS_CLIPSIBLINGS | WS_TABSTOP)?;
            let keys = KeyBindings::create(hwnd, instance.into())?;
            let outcomes = outcome_table(hwnd, instance.into())?;
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
            let keep_captures = if crate::fss::CALIBRATE {
                let check = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_AUTOCHECKBOX as u32))?;
                let label = wide(KEEP_CAPTURES);
                let _ = SetWindowTextW(check, PCWSTR(label.as_ptr()));
                send(check, BM_SETCHECK, crate::fss::keep_all() as usize, 0);
                Some(check)
            } else {
                None
            };
            let prefs = crate::prefs::get();
            let mut pref_checks = Vec::new();
            for (label, on) in PREF_CHECKS.iter().zip(pref_flags(&prefs)) {
                let check = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_AUTOCHECKBOX as u32))?;
                let text = wide(label);
                let _ = SetWindowTextW(check, PCWSTR(text.as_ptr()));
                send(check, BM_SETCHECK, on as usize, 0);
                pref_checks.push(check);
            }
            let mut pref_labels = Vec::new();
            let mut pref_combos = Vec::new();
            for (label, choices, chosen) in [
                (SIZE_LABEL, &crate::prefs::SIZE_CHOICES[..], prefs.size),
                (OPACITY_LABEL, &crate::prefs::OPACITY_CHOICES[..], prefs.opacity),
            ] {
                let caption = child(w!("STATIC"), WINDOW_EX_STYLE::default(), WINDOW_STYLE(0))?;
                let text = wide(label);
                let _ = SetWindowTextW(caption, PCWSTR(text.as_ptr()));
                let combo = child(w!("COMBOBOX"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WS_VSCROLL | WINDOW_STYLE(CBS_DROPDOWNLIST as u32))?;
                for c in choices {
                    let item = wide(&format!("{c}%"));
                    send(combo, CB_ADDSTRING, 0, item.as_ptr() as isize);
                }
                send(combo, CB_SETCURSEL, choices.iter().position(|c| *c == chosen).unwrap_or(0), 0);
                pref_labels.push(caption);
                pref_combos.push(combo);
            }
            let map_kinds_label = child(w!("STATIC"), WINDOW_EX_STYLE::default(), WINDOW_STYLE(0))?;
            let text = wide(MAP_KINDS_LABEL);
            let _ = SetWindowTextW(map_kinds_label, PCWSTR(text.as_ptr()));
            let mut map_kind_checks = Vec::new();
            for (kind, on) in KINDS.iter().zip(prefs.map_kinds) {
                let check = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_AUTOCHECKBOX as u32))?;
                let text = wide(&kind.title());
                let _ = SetWindowTextW(check, PCWSTR(text.as_ptr()));
                send(check, BM_SETCHECK, on as usize, 0);
                map_kind_checks.push(check);
            }
            let mut routes = Vec::new();
            for (label, _) in CARRIER_BUTTONS {
                let route = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_OWNERDRAW as u32))?;
                let route_label = wide(label);
                let _ = SetWindowTextW(route, PCWSTR(route_label.as_ptr()));
                let _ = SetWindowPos(route, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
                routes.push(route);
            }
            let carrier_name = child(w!("EDIT"), WS_EX_CLIENTEDGE, WS_TABSTOP | WINDOW_STYLE(ES_AUTOHSCROLL as u32))?;
            let _ = SetWindowTheme(carrier_name, w!("DarkMode_CFD"), PCWSTR::null());
            let carrier_plot = child(w!("BUTTON"), WINDOW_EX_STYLE::default(), WS_TABSTOP | WINDOW_STYLE(BS_OWNERDRAW as u32))?;
            let plot_label = wide(PLOT_CARRIER);
            let _ = SetWindowTextW(carrier_plot, PCWSTR(plot_label.as_ptr()));
            for c in [carrier_name, carrier_plot] {
                let _ = SetWindowPos(c, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            }
            let _ = SetWindowPos(settings_tabs, Some(HWND_BOTTOM), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(tabs, Some(HWND_BOTTOM), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(combo, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(sectors.list, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(sector_search, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let _ = SetWindowPos(sector_systems.list, Some(HWND_TOP), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            let window = MainWindow {
                hwnd,
                tabs,
                pages: {
                    let mut pages = vec![Vec::new(); TAB_NAMES.len()];
                    let (fixed, picked): (Vec<_>, Vec<_>) = routes.iter().zip(CARRIER_BUTTONS).partition(|(_, (_, to))| to.is_some());
                    let (fixed, picked): (Vec<HWND>, Vec<HWND>) = (fixed.into_iter().map(|(r, _)| *r).collect(), picked.into_iter().map(|(r, _)| *r).collect());
                    pages[MAP_TAB] =
                        [vec![combo, catalogued, zoom_out, sector_search], picked, vec![map.hwnd, sectors.list, sector_systems.list]].concat();
                    pages[CODEX_TAB] = [vec![codex_region], codex.lists()].concat();
                    pages[TRADE_TAB] = vec![trade.list];
                    pages[ENGINEERS_TAB] = vec![engineers.list];
                    pages[GUARDIAN_TAB] = vec![guardian.list];
                    pages[THARGOID_TAB] = vec![thargoid.list];
                    pages[CARRIER_TAB] = [vec![carrier_name, carrier_plot], fixed, vec![carrier.hwnd]].concat();
                    pages[STATS_TAB] = vec![stats.hwnd];
                    pages[SETTINGS_TAB] = vec![settings_tabs];
                    pages[LOG_TAB] = vec![edit];
                    pages
                },
                log: LogView { edit, path: log_path.to_path_buf(), offset: 0, pending: Vec::new(), chars: 0 },
                sectors,
                map,
                zoom_out,
                sector_search,
                sector_systems,
                sector_names: Vec::new(),
                table_box: (0, 0, 0, 0),
                square: false,
                sector_matches: Vec::new(),
                trade,
                engineers,
                guardian,
                thargoid,
                carrier,
                codex,
                codex_region,
                codex_regions: Vec::new(),
                codex_pick: None,
                stats,
                settings_tabs,
                settings_pages: {
                    let mut sub = vec![
                        [pref_checks.clone(), pref_labels.clone(), pref_combos.clone(), vec![outcomes.list]].concat(),
                        keys.controls(),
                        [vec![map_kinds_label], map_kind_checks.clone()].concat(),
                    ];
                    sub.extend(keep_captures.map(|c| vec![c]));
                    sub
                },
                keys,
                outcomes,
                combo,
                catalogued,
                keep_captures,
                pref_checks,
                pref_labels,
                pref_combos,
                map_kinds_label,
                map_kind_checks,
                routes,
                route_flash: None,
                carrier_name,
                carrier_plot,
                band: CreateSolidBrush(colorref(TABLE_ROW)),
                fonts: Fonts::new(dpi),
            };
            for (i, name) in TAB_NAMES.iter().enumerate() {
                add_tab(window.tabs, i, name);
            }
            for (i, name) in SETTINGS_PAGE_NAMES.iter().take(window.settings_pages.len()).enumerate() {
                add_tab(window.settings_tabs, i, name);
            }
            let mut window = window;
            window.apply_fonts();
            window.layout();
            window.show_selected();
            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
            Ok(window)
        }
    }

    fn chosen_prefs(&self) -> crate::prefs::Prefs {
        let on: Vec<bool> = self.pref_checks.iter().map(|c| send(*c, BM_GETCHECK, 0, 0) == 1).collect();
        let pick = |i: usize, choices: &[u32], fallback: u32| {
            let at = send(self.pref_combos[i], CB_GETCURSEL, 0, 0);
            usize::try_from(at).ok().and_then(|a| choices.get(a).copied()).unwrap_or(fallback)
        };
        let was = crate::prefs::get();
        let mut map_kinds = was.map_kinds;
        for (slot, check) in map_kinds.iter_mut().zip(&self.map_kind_checks) {
            *slot = send(*check, BM_GETCHECK, 0, 0) == 1;
        }
        crate::prefs::Prefs {
            sound: on[0],
            lights: on[1],
            hotkeys: on[2],
            always_visible: on[3],
            draggable: on[4],
            size: pick(0, &crate::prefs::SIZE_CHOICES, was.size),
            opacity: pick(1, &crate::prefs::OPACITY_CHOICES, was.opacity),
            map_kinds,
        }
    }

    fn apply_fonts(&mut self) {
        let ui = self.fonts.ui.0 as usize;
        send(self.tabs, WM_SETFONT, ui, 1);
        send(self.log.edit, WM_SETFONT, self.fonts.mono.0 as usize, 1);
        send(self.sectors.list, WM_SETFONT, ui, 1);
        send(self.trade.list, WM_SETFONT, ui, 1);
        self.trade.autosize();
        send(self.engineers.list, WM_SETFONT, ui, 1);
        self.engineers.autosize();
        send(self.guardian.list, WM_SETFONT, ui, 1);
        self.guardian.autosize();
        send(self.thargoid.list, WM_SETFONT, ui, 1);
        self.thargoid.autosize();
        self.carrier.set_fonts(self.fonts.ui, self.fonts.small, self.fonts.big);
        self.stats.set_fonts(self.fonts.ui, self.fonts.small);
        send(self.settings_tabs, WM_SETFONT, ui, 1);
        for control in self.keys.controls() {
            send(control, WM_SETFONT, ui, 1);
        }
        send(self.outcomes.list, WM_SETFONT, ui, 1);
        self.outcomes.autosize();
        send(self.combo, WM_SETFONT, ui, 1);
        send(self.codex_region, WM_SETFONT, ui, 1);
        self.codex.set_font(ui);
        send(self.catalogued, WM_SETFONT, ui, 1);
        for &control in self
            .keep_captures
            .iter()
            .chain(&self.pref_checks)
            .chain(&self.pref_labels)
            .chain(&self.pref_combos)
            .chain([&self.map_kinds_label])
            .chain(&self.map_kind_checks)
        {
            send(control, WM_SETFONT, ui, 1);
        }
        for &control in self.routes.iter().chain([&self.carrier_name, &self.carrier_plot, &self.zoom_out]) {
            send(control, WM_SETFONT, ui, 1);
        }
        self.sectors.autosize();
        self.map.set_fonts(self.fonts.ui, self.fonts.small);
        send(self.sector_search, WM_SETFONT, ui, 1);
        send(self.sector_systems.list, WM_SETFONT, ui, 1);
        self.sector_systems.autosize();
    }

    fn table(&self, hwnd: HWND) -> Option<&ExpectedTable> {
        (self.sectors.list == hwnd).then_some(&self.sectors)
    }

    fn table_mut(&mut self, hwnd: HWND) -> Option<&mut ExpectedTable> {
        (self.sectors.list == hwnd).then_some(&mut self.sectors)
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
        for &p in self.pages[LOG_TAB].iter().chain(&self.pages[TRADE_TAB]).chain(&self.pages[ENGINEERS_TAB]).chain(&self.pages[GUARDIAN_TAB]).chain(&self.pages[THARGOID_TAB]).chain(&self.pages[STATS_TAB]) {
            place(p, page.left, page.top, w, h);
        }
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        let px = |v: i32| v * dpi / 96;
        place(self.settings_tabs, page.left, page.top, w, h);
        let mut sub = page;
        send(self.settings_tabs, TCM_ADJUSTRECT, 0, &mut sub as *mut RECT as isize);
        let (left, top, sub_w) = (sub.left + px(GAP), sub.top + px(GAP), sub.right - sub.left - px(GAP * 2));
        let check_rows = (self.pref_checks.len() as i32 + PREF_COLUMNS - 1) / PREF_COLUMNS;
        for (i, &check) in self.pref_checks.iter().enumerate() {
            let (row, col) = (i as i32 / PREF_COLUMNS, i as i32 % PREF_COLUMNS);
            place(check, left + col * px(PREF_CHECK_WIDTH), top + row * px(CHECK_HEIGHT), px(PREF_CHECK_WIDTH), px(CHECK_HEIGHT));
        }
        let levels_top = top + check_rows * px(CHECK_HEIGHT) + px(GAP / 2);
        for (i, (&caption, &combo)) in self.pref_labels.iter().zip(&self.pref_combos).enumerate() {
            let x = left + i as i32 * (px(PREF_LABEL_WIDTH) + px(PREF_COMBO_WIDTH) + px(GAP) * 3);
            place(caption, x, levels_top + px(3), px(PREF_LABEL_WIDTH), px(CHECK_HEIGHT));
            place(combo, x + px(PREF_LABEL_WIDTH) + px(GAP), levels_top, px(PREF_COMBO_WIDTH), px(COMBO_DROP));
        }
        let summary_top = levels_top + px(CHECK_HEIGHT) + px(GAP * 2);
        let summary_h = (list_height(self.outcomes.list, KINDS.len()) + px(4)).min(sub.bottom - px(GAP) - summary_top);
        place(self.outcomes.list, left, summary_top, sub_w, summary_h);
        for (i, (&label, &button)) in self.keys.labels.iter().zip(&self.keys.buttons).enumerate() {
            let y = top + i as i32 * px(KEY_ROW);
            place(label, left, y + px(4), px(KEY_LABEL_WIDTH), px(CHECK_HEIGHT));
            place(button, left + px(KEY_LABEL_WIDTH + GAP), y, px(KEY_BUTTON_WIDTH), px(CHECK_HEIGHT + 4));
        }
        place(self.map_kinds_label, left, top, px(PREF_LABEL_WIDTH), px(CHECK_HEIGHT));
        for (i, &check) in self.map_kind_checks.iter().enumerate() {
            let (row, col) = (i as i32 / PREF_COLUMNS, i as i32 % PREF_COLUMNS);
            place(check, left + col * px(PREF_CHECK_WIDTH), top + px(CHECK_HEIGHT) + row * px(CHECK_HEIGHT), px(PREF_CHECK_WIDTH), px(CHECK_HEIGHT));
        }
        if let Some(check) = self.keep_captures {
            place(check, left, top, px(KEEP_CAPTURES_WIDTH).min(sub_w), px(CHECK_HEIGHT));
        }
        let table_w = px(SECTOR_WIDTH).min(w / 2);
        let table_top = page.top + px(MAP_BAND);
        let table_h = (self.sectors.height_for(SECTOR_ROWS + 1) + px(4)).min(page.bottom - table_top);
        place(self.map.hwnd, page.left, page.top, w, h);
        place(self.combo, page.left + px(GAP), page.top + px(5), px(COMBO_WIDTH), px(COMBO_DROP));
        place(self.catalogued, page.left + px(GAP * 2 + COMBO_WIDTH), page.top + px(6), px(CHECK_WIDTH), px(CHECK_HEIGHT));
        place(self.zoom_out, page.left + px(GAP), page.top + px(MAP_BAND + GAP), px(ZOOM_WIDTH), px(CHECK_HEIGHT + 4));
        let search_left = GAP * 3 + COMBO_WIDTH + CHECK_WIDTH;
        place(self.sector_search, page.left + px(search_left), page.top + px(5), px(MAP_SEARCH_WIDTH), px(SEARCH_DROP));
        place(self.carrier_name, page.left + px(GAP), page.top + px(5), px(SEARCH_WIDTH), px(CHECK_HEIGHT + 2));
        place(self.carrier_plot, page.left + px(GAP * 2 + SEARCH_WIDTH), page.top + px(4), px(ROUTE_WIDTH), px(CHECK_HEIGHT + 4));
        let mut fixed = 0;
        for (&route, _) in self.routes.iter().zip(CARRIER_BUTTONS).rev().filter(|(_, (_, to))| to.is_some()) {
            fixed += 1;
            let x = page.left + px(GAP * 2 + SEARCH_WIDTH + (GAP + ROUTE_WIDTH) * (CARRIER_FIXED as i32 + 1 - fixed));
            place(route, x, page.top + px(4), px(ROUTE_WIDTH), px(CHECK_HEIGHT + 4));
        }
        place(self.carrier.hwnd, page.left, page.top, w, h);
        place(self.codex_region, page.left + px(GAP), page.top + px(5), px(CODEX_COMBO_WIDTH), px(SEARCH_DROP));
        self.codex.place(page.left, page.top + px(MAP_BAND), w, h - px(MAP_BAND), px(GAP) / 2);
        self.carrier.set_top(px(MAP_BAND));
        place(self.sectors.list, page.right - table_w, table_top, table_w, table_h);
        self.map.set_layout(MapLayout {
            top: px(MAP_BAND),
            right: table_w + px(GAP),
            pad: px(GAP),
            inset: px(GAP * 2 + CHECK_HEIGHT + 4),
        });
        place(self.sector_systems.list, page.right - table_w, table_top, table_w, table_h);
        self.table_box = (page.right - table_w, table_top, table_w, table_h);
        self.fit_tables();
    }

    fn show_selected(&self) {
        let selected = send(self.tabs, TCM_GETCURSEL, 0, 0).max(0) as usize;
        if selected == MAP_TAB {
            push_ask(UiAsk::MapRegions { catalogued: self.include_catalogued() });
            push_ask(UiAsk::MapConfirmed);
        }
        if selected == MAP_TAB && self.sector_names.is_empty() {
            push_ask(UiAsk::SectorNames);
        }
        if selected == CODEX_TAB {
            push_ask(UiAsk::Codex { region_id: self.codex_pick });
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
        if selected == STATS_TAB {
            push_ask(UiAsk::Stats);
        }
        if selected == SETTINGS_TAB {
            push_ask(UiAsk::Outcomes);
        }
        let sub_selected = send(self.settings_tabs, TCM_GETCURSEL, 0, 0).max(0) as usize;
        let on_keys = selected == SETTINGS_TAB && sub_selected == KEYS_PAGE;
        if !on_keys && crate::win::hotkeys::cancel_capture() {
            self.keys.refresh();
        }
        for (i, page) in self.pages.iter().enumerate() {
            for &p in page {
                unsafe {
                    let _ = ShowWindow(p, if i == selected { SW_SHOW } else { SW_HIDE });
                }
            }
        }
        for (i, page) in self.settings_pages.iter().enumerate() {
            for &p in page {
                unsafe {
                    let _ = ShowWindow(p, if selected == SETTINGS_TAB && i == sub_selected { SW_SHOW } else { SW_HIDE });
                }
            }
        }
        if selected == MAP_TAB {
            self.show_map_level();
        }
    }

    fn show_map_level(&self) {
        let zoomed = self.map.zoomed_region().is_some();
        let on_map = send(self.tabs, TCM_GETCURSEL, 0, 0).max(0) as usize == MAP_TAB;
        let shown = |on: bool| if on && on_map { SW_SHOW } else { SW_HIDE };
        unsafe {
            let _ = ShowWindow(self.sectors.list, shown(!zoomed || self.square));
            let _ = ShowWindow(self.sector_systems.list, shown(zoomed && !self.square));
            let _ = ShowWindow(self.zoom_out, shown(zoomed));
        }
    }

    fn zoom_to(&mut self, region_id: i64) {
        if !self.map.zoom_to(region_id) {
            return;
        }
        self.square = false;
        self.sector_systems.clear();
        self.fit_tables();
        push_ask(UiAsk::RegionSectors { region_id, catalogued: self.include_catalogued() });
        self.ask_sectors(Some(region_id));
        self.show_map_level();
    }

    fn show_square(&mut self, rows: Vec<RegionExpected>) {
        let total = summed(SQUARE_TOTAL, &rows);
        self.square = true;
        self.sectors.show_with_total(rows, Some(total));
        self.sectors.sort_by_kind(self.map.kind());
        self.show_map_level();
        self.fit_tables();
    }

    fn fit_tables(&mut self) {
        let (x, y, w, most) = self.table_box;
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        let px = |v: i32| v * dpi / 96;
        let (gap, button_w, button_h) = (px(GAP), px(ROUTE_WIDTH), px(CHECK_HEIGHT + 4));
        let shown = if self.map.zoomed_region().is_some() && !self.square { self.sector_systems.list } else { self.sectors.list };
        for list in [self.sectors.list, self.sector_systems.list] {
            let h = fitted_height(list).min(most);
            unsafe {
                let _ = MoveWindow(list, x, y, w, h, true);
            }
            if list != shown {
                continue;
            }
            let row = y + h + gap;
            let mut right = x + w;
            for (&route, _) in self.routes.iter().zip(CARRIER_BUTTONS).rev().filter(|(_, (_, to))| to.is_none()) {
                unsafe {
                    let _ = MoveWindow(route, right - button_w, row, button_w, button_h, true);
                }
                right -= button_w + gap;
            }
        }
        self.sectors.autosize();
        self.sector_systems.autosize();
        for list in [self.sectors.list, self.sector_systems.list] {
            unsafe {
                let _ = InvalidateRect(Some(list), None, true);
            }
        }
    }

    fn zoom_out(&mut self) {
        if self.map.zoom_out() {
            if self.square {
                self.square = false;
                self.ask_sectors(self.map.selected_region());
            }
            self.show_map_level();
            self.fit_tables();
        }
    }

    fn ask_sector_view(&self, sector: String, locate: bool) {
        let column = KINDS[self.map.kind()].column;
        push_ask(UiAsk::SectorView { sector, column, catalogued: self.include_catalogued(), limit: SECTOR_SYSTEMS_LIMIT, locate });
    }

    fn sector_clicked(&self, sector: String) {
        let kind = &KINDS[self.map.kind()];
        self.ask_sector_view(sector.clone(), false);
        push_ask(UiAsk::SectorBest { sector, catalogued: self.include_catalogued(), column: kind.column, kind: kind.name });
    }

    fn show_sector_view(&mut self, view: SectorView, locate: bool) {
        if locate {
            let (x0, z0, x1, z1) = view.cells;
            let region = view.region_id.or_else(|| self.map.region_at_cells((x0 + x1) / 2.0, (z0 + z1) / 2.0));
            match region {
                Some(r) if self.map.zoomed_region() != Some(r) => self.zoom_to(r),
                Some(_) => {}
                None => {
                    say!("{}: it lies in no region of the map", view.sector);
                    return;
                }
            }
        }
        if self.map.zoomed_region().is_none() {
            if locate {
                say!("{}: the map has not loaded yet", view.sector);
            }
            return;
        }
        self.square = false;
        self.sector_systems.show(&view.systems, &view.sector, view.expected, view.listed);
        self.show_map_level();
        self.fit_tables();
        self.map.pick_sector(&view.sector, (view.sector_id < 0).then_some(view.cells));
    }

    fn kind_changed(&mut self) {
        let kind = send(self.combo, CB_GETCURSEL, 0, 0);
        if kind < 0 || kind as usize >= KINDS.len() {
            return;
        }
        self.map.set_kind(kind as usize);
        self.sectors.set_kind(kind as usize);
        self.ask_sectors(self.map.selected_region());
        if let Some(sector) = self.map.picked_sector() {
            self.ask_sector_view(sector, false);
        }
    }

    fn ask_sectors(&self, region_id: Option<i64>) {
        if let Some(region_id) = region_id {
            let column = KINDS[self.map.kind()].column;
            let catalogued = self.include_catalogued();
            push_ask(UiAsk::Sectors { region_id, catalogued, column, limit: SECTOR_ROWS as i64 });
        }
    }

    fn search_changed(&mut self) {
        let typed = window_text(self.sector_search);
        self.sector_matches = sector_matches(&self.sector_names, &typed);
        send(self.sector_search, CB_RESETCONTENT, 0, 0);
        for name in &self.sector_matches {
            let item = wide(name);
            send(self.sector_search, CB_ADDSTRING, 0, item.as_ptr() as isize);
        }
        send(self.sector_search, CB_SHOWDROPDOWN, usize::from(!self.sector_matches.is_empty()), 0);
        let text = wide(&typed);
        let end = typed.encode_utf16().count() as isize;
        unsafe {
            let _ = SetWindowTextW(self.sector_search, PCWSTR(text.as_ptr()));
            SetCursor(LoadCursorW(None, IDC_ARROW).ok());
        }
        send(self.sector_search, CB_SETEDITSEL, 0, end | end << 16);
    }

    fn search_picked(&mut self) {
        let selected = send(self.sector_search, CB_GETCURSEL, 0, 0);
        let typed = window_text(self.sector_search);
        let picked = usize::try_from(selected)
            .ok()
            .and_then(|i| self.sector_matches.get(i).cloned())
            .or_else(|| self.sector_names.iter().find(|n| n.eq_ignore_ascii_case(typed.trim())).cloned())
            .or_else(|| self.sector_matches.first().cloned());
        let Some(sector) = picked else { return };
        let text = wide(&sector);
        unsafe {
            let _ = SetWindowTextW(self.sector_search, PCWSTR(text.as_ptr()));
        }
        self.ask_sector_view(sector, true);
    }

    fn show_codex(&mut self, view: CodexView) {
        send(self.codex_region, CB_RESETCONTENT, 0, 0);
        for r in &view.regions {
            let item = wide(&format!("{}  \u{00B7}  {} of {} logged", r.region, r.logged, r.known));
            send(self.codex_region, CB_ADDSTRING, 0, item.as_ptr() as isize);
        }
        self.codex_regions = view.regions.iter().map(|r| r.region_id).collect();
        let at = view.region_id.and_then(|id| self.codex_regions.iter().position(|&r| r == id));
        send(self.codex_region, CB_SETCURSEL, at.unwrap_or(usize::MAX), 0);
        self.codex.show(&view.sections);
    }

    fn codex_region_changed(&mut self) {
        let picked = send(self.codex_region, CB_GETCURSEL, 0, 0);
        if let Some(&id) = usize::try_from(picked).ok().and_then(|i| self.codex_regions.get(i)) {
            self.codex_pick = Some(id);
            push_ask(UiAsk::Codex { region_id: Some(id) });
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
        if let Some(region_id) = self.map.zoomed_region() {
            push_ask(UiAsk::RegionSectors { region_id, catalogued });
        }
        if let Some(sector) = self.map.picked_sector() {
            self.ask_sector_view(sector, false);
        }
    }

    fn draw_route(&self, item: &DRAWITEMSTRUCT) {
        let pressed = item.itemState.0 & ODS_SELECTED.0 != 0 || self.route_flash == Some(item.hwndItem);
        let (back, text) = if item.itemState.0 & ODS_DISABLED.0 != 0 {
            (TABLE_ROW, BUTTON_OFF_TEXT)
        } else if pressed {
            (TABLE_FLASH, FLASH_TEXT)
        } else {
            (HEADER_BG, HEADER_TEXT)
        };
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
        let mut label: Vec<u16> = window_text(item.hwndItem).encode_utf16().collect();
        let mut area = r;
        unsafe {
            let old = SelectObject(item.hDC, HGDIOBJ(self.fonts.ui.0));
            SetBkMode(item.hDC, TRANSPARENT);
            SetTextColor(item.hDC, colorref(text));
            DrawTextW(item.hDC, &mut label, &mut area, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
            SelectObject(item.hDC, old);
        }
    }

    fn flash_route(&mut self, button: Option<HWND>) {
        let previous = std::mem::replace(&mut self.route_flash, button);
        unsafe {
            for route in previous.into_iter().chain(button) {
                let _ = InvalidateRect(Some(route), None, false);
            }
            if button.is_some() {
                SetTimer(Some(self.hwnd), ROUTE_FLASH_TIMER, FLASH_MS, None);
            } else {
                let _ = KillTimer(Some(self.hwnd), ROUTE_FLASH_TIMER);
            }
        }
    }

    fn plot_carrier(&mut self) {
        let name = window_text(self.carrier_name).trim().to_string();
        if name.is_empty() {
            say!("paste a system name into the box beside {PLOT_CARRIER} first");
            return;
        }
        self.flash_route(Some(self.carrier_plot));
        push_ask(UiAsk::CarrierRoute { destination: Some(name) });
    }

    fn colour_edit(&self, dc: HDC) -> LRESULT {
        unsafe {
            SetTextColor(dc, colorref(TABLE_TEXT));
            SetBkColor(dc, colorref(TABLE_ROW));
        }
        LRESULT(self.band.0 as isize)
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
            with_main(|m| m.flash_route(None));
            LRESULT(0)
        }
        WM_DRAWITEM => {
            let item = unsafe { &*(lparam.0 as *const DRAWITEMSTRUCT) };
            let drawn = MAIN.with(|cell| match cell.try_borrow() {
                Ok(guard) => guard
                    .as_ref()
                    .filter(|m| m.routes.contains(&item.hwndItem) || m.carrier_plot == item.hwndItem || m.zoom_out == item.hwndItem)
                    .map(|m| m.draw_route(item)),
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
            if code == CBN_EDITCHANGE || code == CBN_SELENDOK {
                with_main(|m| {
                    if m.sector_search.0 as isize == lparam.0 {
                        if code == CBN_EDITCHANGE {
                            m.search_changed();
                        } else {
                            m.search_picked();
                        }
                    }
                });
            }
            if code == CBN_SELCHANGE {
                with_main(|m| {
                    if m.combo.0 as isize == lparam.0 {
                        m.kind_changed();
                    }
                    if m.codex_region.0 as isize == lparam.0 {
                        m.codex_region_changed();
                    }
                    if m.pref_combos.iter().any(|c| c.0 as isize == lparam.0) {
                        push_ask(UiAsk::Prefs(m.chosen_prefs()));
                    }
                });
            }
            if code == BN_CLICKED {
                with_main(|m| {
                    if m.catalogued.0 as isize == lparam.0 {
                        m.catalogued_changed();
                    }
                    if m.pref_checks.iter().chain(&m.map_kind_checks).any(|c| c.0 as isize == lparam.0) {
                        push_ask(UiAsk::Prefs(m.chosen_prefs()));
                    }
                    if let Some(check) = m.keep_captures.filter(|c| c.0 as isize == lparam.0) {
                        push_ask(UiAsk::KeepFssCaptures(send(check, BM_GETCHECK, 0, 0) == 1));
                    }
                    if m.keys.clicked(lparam.0) {
                        unsafe {
                            let _ = SetFocus(Some(m.hwnd));
                        }
                    }
                    if m.carrier_plot.0 as isize == lparam.0 {
                        m.plot_carrier();
                    }
                    if m.zoom_out.0 as isize == lparam.0 {
                        m.zoom_out();
                    }
                    if let Some(i) = m.routes.iter().position(|r| r.0 as isize == lparam.0) {
                        m.flash_route(Some(m.routes[i]));
                        push_ask(UiAsk::CarrierRoute { destination: CARRIER_BUTTONS[i].1.map(String::from) });
                    }
                });
            }
            LRESULT(0)
        }
        WM_CTLCOLOREDIT => {
            let coloured = MAIN.with(|cell| match cell.try_borrow() {
                Ok(guard) => guard
                    .as_ref()
                    .filter(|m| m.carrier_name.0 as isize == lparam.0)
                    .map(|m| m.colour_edit(HDC(wparam.0 as *mut _))),
                Err(_) => None,
            });
            coloured.unwrap_or_else(|| unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) })
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
            if header.code == NM_DBLCLK {
                with_main(|m| {
                    if m.sectors.list == header.hwndFrom
                        && let Some(sector) = m.sectors.activated(lparam)
                    {
                        m.ask_sector_view(sector, true);
                    }
                });
                return LRESULT(0);
            }
            if header.code == NM_CUSTOMDRAW || header.code == LVN_ITEMCHANGING {
                return MAIN.with(|cell| match cell.try_borrow() {
                    Ok(guard) => match guard.as_ref() {
                        Some(m) if m.trade.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.trade.custom_draw(lparam)
                        }
                        Some(m) if m.trade.list == header.hwndFrom => m.trade.select(lparam),
                        Some(m) if m.codex.find(header.hwndFrom).is_some() => {
                            let table = m.codex.find(header.hwndFrom).expect("matched above");
                            if header.code == NM_CUSTOMDRAW { table.custom_draw(lparam) } else { table.select(lparam) }
                        }
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
                        Some(m) if m.sector_systems.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.sector_systems.custom_draw(lparam)
                        }
                        Some(m) if m.sector_systems.list == header.hwndFrom => m.sector_systems.select(lparam),
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
                        Some(m) if m.outcomes.list == header.hwndFrom && header.code == NM_CUSTOMDRAW => {
                            m.outcomes.custom_draw(lparam)
                        }
                        Some(m) if m.outcomes.list == header.hwndFrom => m.outcomes.refuse_selection(lparam),
                        Some(m) => match m.table(header.hwndFrom) {
                            Some(t) if header.code == NM_CUSTOMDRAW => t.custom_draw(lparam),
                            Some(t) => t.refuse_selection(lparam),
                            None => LRESULT(0),
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
